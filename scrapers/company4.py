import os
import time
import random
from urllib.parse import urljoin
from datetime import datetime

import pandas as pd
import requests
from lxml import html

BASE = "https://www.era.com.tr"
LIST_URL = BASE + "/danismanlar?pager_p={page}"

session = requests.Session()
session.headers.update(
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
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
        try:
            r = session.get(LIST_URL.format(page=page), timeout=30)
            r.raise_for_status()
            tree = html.fromstring(r.text)
        except Exception as exc:
            print(f"page {page} LIST error: {exc}")
            break

        cards = tree.xpath('//a[starts-with(@href,"/danismanlar/") and .//h2]')
        print(f"page {page}: cards={len(cards)}")
        if not cards:
            break

        for c in cards:
            href = c.get("href")
            name = c.xpath("string(.//h2)").strip()
            profile_url = urljoin(BASE, href)

            try:
                pr = session.get(profile_url, timeout=30)
                pr.raise_for_status()
                p_tree = html.fromstring(pr.text)
            except Exception as exc:
                print(f"detail error {profile_url}: {exc}")
                continue

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
    out_path = os.path.join(output_dir, f"era_{date_str}.csv")
    df.to_csv(out_path, index=False, encoding="utf-8")

    return f"TOTAL: {len(df)} satır, dosya: {os.path.basename(out_path)}"


