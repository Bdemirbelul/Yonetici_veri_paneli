import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin
from datetime import datetime

import pandas as pd
import requests
from lxml import html

BASE = "https://rookz.com.tr"
LIST_BASE = BASE + "/tr-TR/ekibimiz"


def _list_url(page: int) -> str:
    return LIST_BASE if page == 1 else f"{LIST_BASE}/{page}"


HEADERS = {"User-Agent": "Mozilla/5.0"}

X_NAME = "/html/body/div[2]/div[2]/div[2]/div/div[1]/h2"
X_PHONE = "/html/body/div[2]/div[2]/div[2]/div/div[3]/a[1]"
X_MAIL = "/html/body/div[2]/div[2]/div[2]/div/div[3]/a[2]"


def get_tree(url: str) -> html.HtmlElement:
    r = requests.get(url, headers=HEADERS, timeout=25)
    r.raise_for_status()
    return html.fromstring(r.text)


def xtext(tree, xp: str) -> str:
    return (tree.xpath(f"string({xp})") or "").strip()


def collect_profile_links(max_pages=500):
    links = []
    seen = set()

    for page in range(1, max_pages + 1):
        url = _list_url(page)
        tree = get_tree(url)

        anchors = tree.xpath('//a[.//img[contains(@class,"w-50")]]/@href')
        anchors = [urljoin(BASE, a) for a in anchors if a]

        new = 0
        for a in anchors:
            if a not in seen:
                seen.add(a)
                links.append((page, a))
                new += 1

        print(f"[PAGE {page}] found {len(anchors)} | new {new} | total {len(links)}")

        if len(anchors) == 0:
            break

    return links


def parse_profile(page_num: int, url: str):
    tree = get_tree(url)

    name = xtext(tree, X_NAME)

    phone_node = tree.xpath(X_PHONE)
    phone = ""
    if phone_node:
        href = (phone_node[0].get("href") or "").strip()
        txt = (phone_node[0].text_content() or "").strip()
        phone = (
            href.replace("tel:", "").strip()
            if href.lower().startswith("tel:")
            else txt
        )

    mail_node = tree.xpath(X_MAIL)
    email = ""
    if mail_node:
        href = (mail_node[0].get("href") or "").strip()
        txt = (mail_node[0].text_content() or "").strip()
        email = (
            href.replace("mailto:", "").strip()
            if href.lower().startswith("mailto:")
            else txt
        )

    if not email:
        m = re.search(
            r"[\\w\\.-]+@[\\w\\.-]+\\.\\w+",
            html.tostring(tree, encoding="unicode"),
        )
        if m:
            email = m.group(0)

    return {
        "page": page_num,
        "name": name,
        "phone": phone,
        "email": email,
        "profile_url": url,
    }


def scrape_profiles_fast(profiles, workers=20):
    rows = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(parse_profile, p, u) for (p, u) in profiles]
        for f in as_completed(futs):
            row = f.result()
            rows.append(row)
            print(
                f'[{row["page"]}] {row["name"] or "-"} | {row["phone"] or "-"} | {row["email"] or "-"}'
            )
    return pd.DataFrame(rows)


def run(output_dir: str) -> str:
    """
    Scraper çalışır, output_dir içine csv/json kaydeder.
    Geriye özet bir mesaj döndürür.
    """
    profiles = collect_profile_links(max_pages=500)
    print("TOTAL PROFILE LINKS:", len(profiles))

    df = scrape_profiles_fast(profiles, workers=20)
    df = df.drop_duplicates(subset=["profile_url"]).sort_values(
        ["page", "name"], na_position="last"
    )

    os.makedirs(output_dir, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    out_path = os.path.join(output_dir, f"rookz_{date_str}.csv")
    df.to_csv(out_path, index=False, encoding="utf-8-sig")

    return f"TOTAL: {len(df)} satır, dosya: {os.path.basename(out_path)}"


