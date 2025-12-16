import os
import time
import random
from urllib.parse import urljoin
from datetime import datetime

import pandas as pd
import requests
from lxml import html

BASE = "https://remax.com.tr"
LIST_URL = BASE + "/tr/danismanlar?page={page}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}

# Kartların listesi (senin xpath'inden genelleştirildi)
CARD_XPATH = "/html/body/main/div/div/div[5]/div/div/a"

# Xpath'ler kart içinde relative hale getirildi
NAME_XPATH = ".//div[2]/div[2]/div[1]/div[1]"
ROLE_XPATH = ".//div[2]/div[2]/div[1]/div[2]"
PHONE_XPATH = ".//div[2]/div[2]/div[3]/div[2]/div[1]/span"
MAIL_XPATH = ".//div[2]/div[2]/div[3]/div[2]/div[2]/span"


def clean_first(node, xp: str):
    res = node.xpath(xp)
    if not res:
        return None
    # res[0] element de olabilir string de
    if hasattr(res[0], "text_content"):
        return res[0].text_content().strip()
    return str(res[0]).strip()


def scrape_pages(start_page=1, end_page=267, stop_when_empty=True):
    rows = []
    s = requests.Session()

    for page in range(start_page, end_page + 1):
        url = LIST_URL.format(page=page)
        r = s.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()

        tree = html.fromstring(r.text)
        cards = tree.xpath(CARD_XPATH)

        print(f"page={page} | cards={len(cards)}")

        if stop_when_empty and len(cards) == 0:
            break

        for c in cards:
            name = clean_first(c, NAME_XPATH)
            role = clean_first(c, ROLE_XPATH)
            phone = clean_first(c, PHONE_XPATH)
            mail = clean_first(c, MAIL_XPATH)

            href = c.get("href")
            profile_url = urljoin(BASE, href) if href else None

            rows.append(
                {
                    "page": page,
                    "name": name,
                    "role": role,
                    "phone": phone,
                    "email": mail,
                    "profile_url": profile_url,
                }
            )

        time.sleep(random.uniform(1.0, 2.0))  # nazik bekleme

    return pd.DataFrame(rows).drop_duplicates()


def run(output_dir: str) -> str:
    """
    Scraper çalışır, output_dir içine csv/json kaydeder.
    Geriye özet bir mesaj döndürür.
    """
    df = scrape_pages(start_page=1, end_page=267, stop_when_empty=True)

    os.makedirs(output_dir, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    out_path = os.path.join(output_dir, f"remax_{date_str}.csv")
    df.to_csv(out_path, index=False, encoding="utf-8-sig")

    return f"TOTAL: {len(df)} satır, dosya: {os.path.basename(out_path)}"


