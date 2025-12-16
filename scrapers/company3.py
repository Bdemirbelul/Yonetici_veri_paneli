import os
import time
import random
from urllib.parse import urljoin
from datetime import datetime

import pandas as pd
import requests
from lxml import html

BASE = "https://www.century21.com.tr"
LIST_URL = BASE + "/danismanlar?pager_p={page}"

session = requests.Session()
session.headers.update(
    {
        "User-Agent": "Mozilla/5.0",
    }
)


def pick_real_email(tree):
    hrefs = tree.xpath('//a[starts-with(@href,"mailto:")]/@href')
    for h in hrefs:
        v = h.replace("mailto:", "").strip()
        if "@" in v and not v.startswith("?"):
            return v
    return None


def pick_phone(tree):
    hrefs = tree.xpath('//a[starts-with(@href,"tel:")]/@href')
    for h in hrefs:
        v = h.replace("tel:", "").strip()
        if v:
            return v
    return None


def run(output_dir: str) -> str:
    """
    Scraper çalışır, output_dir içine csv/json kaydeder.
    Geriye özet bir mesaj döndürür.
    """
    rows = []

    for page in range(1, 328):
        r = session.get(LIST_URL.format(page=page), timeout=20)
        r.raise_for_status()
        tree = html.fromstring(r.text)

        cards = tree.xpath('//a[starts-with(@href,"/danismanlar/") and .//h2]')
        if not cards:
            break

        for c in cards:
            href = c.get("href")
            name = c.xpath("string(.//h2)").strip()
            profile_url = urljoin(BASE, href)

            pr = session.get(profile_url, timeout=20)
            pr.raise_for_status()
            p_tree = html.fromstring(pr.text)

            email = pick_real_email(p_tree)
            phone = pick_phone(p_tree)

            rows.append(
                {
                    "page": page,
                    "name": name,
                    "email": email,
                    "phone": phone,
                    "profile_url": profile_url,
                }
            )

        # Çok agresif olmamak için ufak bekleme
        time.sleep(random.uniform(0.5, 1.5))

    df = pd.DataFrame(rows).drop_duplicates(subset=["profile_url"])

    os.makedirs(output_dir, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    out_path = os.path.join(output_dir, f"century21_{date_str}.csv")
    df.to_csv(out_path, index=False, encoding="utf-8")

    return f"TOTAL: {len(df)} satır, dosya: {os.path.basename(out_path)}"


