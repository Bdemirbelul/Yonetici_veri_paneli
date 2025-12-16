import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin
from datetime import datetime

import pandas as pd
import requests
from lxml import html
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

BASE = "https://www.turyap.com.tr"
LIST_URL = BASE + "/Danismanlar.aspx"

X_NAME = "/html/body/form/section/div/div/div/section[2]/div/div[2]/div[1]/div/aside/div[1]/h3"
X_PHONE = "/html/body/form/section/div/div/div/section[2]/div/div[2]/div[1]/div/aside/div[1]/ul/li[2]/a/span"
X_MAIL = "/html/body/form/section/div/div/div/section[2]/div/div[2]/div[1]/div/aside/div[1]/ul/li[3]/a"

HEADERS = {"User-Agent": "Mozilla/5.0"}


def setup_driver(headless: bool = True):
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1400,900")
    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.managed_default_content_settings.stylesheets": 2,
        "profile.managed_default_content_settings.fonts": 2,
    }
    options.add_experimental_option("prefs", prefs)
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)


def wait_listing_loaded(driver, timeout=12):
    WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "img.img-fluidDanismanListe"))
    )


def get_listing_profile_links(driver):
    links = []

    # 1) img içeren tüm <a>lar
    anchors = driver.find_elements(
        By.XPATH, '//a[.//img[contains(@class,"img-fluidDanismanListe")]]'
    )
    for a in anchors:
        href = (a.get_attribute("href") or "").strip()
        if href:
            links.append(href)

    # 2) Fallback
    if not links:
        anchors = driver.find_elements(
            By.XPATH,
            '//div[contains(@class,"Danisman") or contains(@class,"danisman")]/descendant::a[1]',
        )
        for a in anchors:
            href = (a.get_attribute("href") or "").strip()
            if href:
                links.append(href)

    out, seen = [], set()
    for h in links:
        full = urljoin(BASE, h)
        if full not in seen:
            seen.add(full)
            out.append(full)
    return out


def click_next_page(driver, timeout=8):
    try:
        old = driver.find_element(By.CSS_SELECTOR, "img.img-fluidDanismanListe")
    except Exception:
        old = None

    try:
        btn = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable(
                (
                    By.XPATH,
                    '(//i[contains(@class,"icon-arrow-right-1")]/ancestor::*[self::a or self::button][1])[1]',
                )
            )
        )
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
        driver.execute_script("arguments[0].click();", btn)

        if old is not None:
            WebDriverWait(driver, timeout).until(EC.staleness_of(old))

        wait_listing_loaded(driver, timeout=timeout)
        return True
    except Exception:
        return False


def collect_all_profile_urls(max_pages=10_000):
    driver = setup_driver(headless=True)
    try:
        driver.get(LIST_URL)
        wait_listing_loaded(driver)

        all_urls = []
        seen = set()
        page = 1

        while page <= max_pages:
            urls = get_listing_profile_links(driver)
            new_count = 0

            for u in urls:
                if u not in seen:
                    seen.add(u)
                    all_urls.append((page, u))
                    new_count += 1

            print(
                f"[PAGE {page}] found {len(urls)} urls | collected {new_count} new (total {len(all_urls)})"
            )

            if not click_next_page(driver):
                break
            page += 1

        return all_urls
    finally:
        driver.quit()


def parse_detail(page_num: int, url: str):
    r = requests.get(url, headers=HEADERS, timeout=25)
    r.raise_for_status()
    tree = html.fromstring(r.text)

    def xtext(xp: str) -> str:
        return (tree.xpath(f"string({xp})") or "").strip()

    name = xtext(X_NAME)
    if not name:
        name = (tree.xpath("string(//aside//h3[1])") or "").strip()

    phone = xtext(X_PHONE)
    if not phone:
        phone = (
            tree.xpath(
                "string(//aside//a[starts-with(@href,'tel:')][1]//span)"
            )
            or ""
        ).strip()
    if not phone:
        phone = (
            tree.xpath(
                "string(//aside//ul//li//span[contains(.,'0')][1])"
            )
            or ""
        ).strip()

    if not phone:
        m = re.search(
            r"(?:\\+?90\\s*)?0?\\s*5\\d{2}\\s*\\d{3}\\s*\\d{2}\\s*\\d{2}|\\b0\\d{10}\\b",
            r.text.replace("&nbsp;", " "),
        )
        if m:
            phone = (
                re.sub(r"\\s+", "", m.group(0))
                .replace("+90", "0")
                .replace("90", "0", 1)
            )

    email = ""
    nodes = tree.xpath(X_MAIL)
    if nodes:
        href = (nodes[0].get("href") or "").strip()
        txt = (nodes[0].text_content() or "").strip()
        if href.lower().startswith("mailto:"):
            email = href.replace("mailto:", "").strip()
        else:
            email = txt

    if not email:
        m = re.search(r"[\\w\\.-]+@[\\w\\.-]+\\.\\w+", r.text)
        if m:
            email = m.group(0)

    return {
        "page": page_num,
        "name": name,
        "phone": phone,
        "email": email,
        "profile_url": url,
    }


def scrape_details_fast(profile_list, workers=20):
    rows = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(parse_detail, p, u) for (p, u) in profile_list]
        for f in as_completed(futs):
            row = f.result()
            rows.append(row)
            print(
                f'[{row["page"]}] {row["name"] or "-"} | {row["phone"] or "-"} | {row["email"] or "-"} | {row["profile_url"]}'
            )
    return pd.DataFrame(rows)


def run(output_dir: str) -> str:
    """
    Scraper çalışır, output_dir içine csv/json kaydeder.
    Geriye özet bir mesaj döndürür.
    """
    profiles = collect_all_profile_urls()
    print("TOTAL PROFILES:", len(profiles))

    df = scrape_details_fast(profiles, workers=20)
    df = df.drop_duplicates(subset=["profile_url"]).sort_values(
        ["page", "name"], na_position="last"
    )

    os.makedirs(output_dir, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    out_path = os.path.join(output_dir, f"turyap_{date_str}.csv")
    df.to_csv(out_path, index=False, encoding="utf-8-sig")

    return f"TOTAL: {len(df)} satır, dosya: {os.path.basename(out_path)}"


