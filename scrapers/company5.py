import os
import re
from datetime import datetime

import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

URL = "https://www.dialogturkiye.com/danismanlarimiz"

# Profile page XPaths
XPATH_TOP = '//*[@id="app"]/div[3]/div[1]/div[1]/div[2]'
XPATH_A1 = '//*[@id="app"]/div[3]/div[1]/div[2]/div/a[1]/div'
XPATH_A2 = '//*[@id="app"]/div[3]/div[1]/div[2]/div/a[2]/div'
XPATH_A3 = '//*[@id="app"]/div[3]/div[1]/div[2]/div/a[3]/div'


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


def wait_cards_loaded(driver, timeout=12):
    WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'img[src*="/data/user/"]'))
    )


def click_page_number(driver, n, timeout=7):
    xpath_btn = f'//button[contains(@class,"paginate-buttons") and contains(@class,"number-buttons") and normalize-space()="{n}"]'
    try:
        btn = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((By.XPATH, xpath_btn))
        )
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
        driver.execute_script("arguments[0].click();", btn)
        return True
    except Exception:
        return False


def safe_text(driver, xpath, timeout=4):
    try:
        el = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, xpath))
        )
        return (el.text or "").strip()
    except Exception:
        return ""


def pick_email(driver):
    # 1) try mailto:
    try:
        a = driver.find_element(By.CSS_SELECTOR, 'a[href^="mailto:"]')
        v = (a.get_attribute("href") or "").replace("mailto:", "").strip()
        if "@" in v and not v.startswith("?"):
            return v
    except Exception:
        pass

    # 2) fallback: find any email-like text on page
    text = driver.page_source
    m = re.search(r"[\\w\\.-]+@[\\w\\.-]+\\.\\w+", text)
    return m.group(0) if m else None


def normalize_tr_phone(raw: str) -> str:
    if not raw:
        return ""
    digits = re.sub(r"\\D+", "", raw.strip())

    # drop country code 90...
    if digits.startswith("90") and len(digits) >= 12:
        digits = digits[2:]  # remove '90'

    # 5xxxxxxxxx -> 05xxxxxxxxx
    if len(digits) == 10 and digits.startswith("5"):
        digits = "0" + digits

    return digits


def is_mobile_tr(d: str) -> bool:
    return len(d) == 11 and d.startswith("05")


def is_landline_tr(d: str) -> bool:
    return len(d) == 11 and d.startswith("0") and not d.startswith("05")


def extract_phones_from_text(text: str):
    """
    Extracts possible phone numbers from plain text.
    Handles: 0505..., +90 505..., 90505..., 0212...
    """
    if not text:
        return []

    # phone-like chunks (keep it permissive)
    candidates = re.findall(
        r'(\\+?90\\s*)?\\(?0?\\d{3}\\)?[\\s\\-]?\\d{3}[\\s\\-]?\\d{2}[\\s\\-]?\\d{2}|\\b0\\d{10}\\b|\\b5\\d{9}\\b',
        text,
    )
    # re.findall returns tuples when groups exist; normalize:
    flat = []
    for c in candidates:
        if isinstance(c, tuple):
            c = "".join(c)
        flat.append(c)

    # also catch fully contiguous digits in the text
    digit_runs = re.findall(r"\\d{10,13}", re.sub(r"\\s+", "", text))
    flat.extend(digit_runs)

    phones = []
    for c in flat:
        d = normalize_tr_phone(c)
        # keep only plausible TR numbers (11 digits starting with 0) or 10-digit mobile
        if len(d) == 11 and d.startswith("0"):
            phones.append(d)

    # unique preserve order
    seen = set()
    out = []
    for p in phones:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def pick_best_phone_from_texts(*texts):
    """
    personal: first mobile (05...)
    else work: prefer 0212..., else any landline
    """
    all_phones = []
    for t in texts:
        all_phones.extend(extract_phones_from_text(t))

    # unique preserve order
    seen = set()
    uniq = []
    for p in all_phones:
        if p not in seen:
            seen.add(p)
            uniq.append(p)

    mobiles = [p for p in uniq if is_mobile_tr(p)]
    if mobiles:
        return mobiles[0], None

    landlines = [p for p in uniq if is_landline_tr(p)]
    if not landlines:
        return None, None

    land_0212 = [p for p in landlines if p.startswith("0212")]
    if land_0212:
        return None, land_0212[0]

    return None, landlines[0]


def collect_profile_links(driver):
    driver.get(URL)
    wait_cards_loaded(driver)

    profiles = []
    seen = set()
    page = 1

    while True:
        wait_cards_loaded(driver)
        imgs = driver.find_elements(By.CSS_SELECTOR, 'img[src*="/data/user/"]')

        for img in imgs:
            try:
                name = (img.get_attribute("alt") or "").strip()
                img_src = (img.get_attribute("src") or "").strip()

                a = img.find_element(By.XPATH, "./ancestor::a[1]")
                href = (a.get_attribute("href") or "").strip()

                if href and href not in seen:
                    seen.add(href)
                    profiles.append(
                        {
                            "page": page,
                            "name_alt": name,
                            "img_src": img_src,
                            "profile_url": href,
                        }
                    )
            except Exception:
                continue

        if click_page_number(driver, page + 1):
            page += 1
            continue
        break

    return profiles


def scrape_profiles(driver, profiles):
    rows = []
    for p in profiles:
        driver.get(p["profile_url"])

        v_top = safe_text(driver, XPATH_TOP)
        v_a1 = safe_text(driver, XPATH_A1)
        v_a2 = safe_text(driver, XPATH_A2)
        v_a3 = safe_text(driver, XPATH_A3)

        email = pick_email(driver)

        # phones from text blocks
        personal_phone, work_phone = pick_best_phone_from_texts(v_top, v_a1, v_a2, v_a3)

        row = {
            **p,
            "xpath_top": v_top,
            "xpath_a1": v_a1,
            "xpath_a2": v_a2,
            "xpath_a3": v_a3,
            "email": email,
            "personal_phone": personal_phone,
            "work_phone": work_phone,
        }
        rows.append(row)

        print(
            f'[{p["page"]}] {p["name_alt"]} | {email or "-"} | personal={personal_phone or "-"} | work={work_phone or "-"}'
        )

    return pd.DataFrame(rows).drop_duplicates(subset=["profile_url"])


def run(output_dir: str) -> str:
    """
    Scraper çalışır, output_dir içine csv/json kaydeder.
    Geriye özet bir mesaj döndürür.
    """
    os.makedirs(output_dir, exist_ok=True)
    driver = setup_driver(headless=True)
    try:
        profiles = collect_profile_links(driver)
        df = scrape_profiles(driver, profiles)
    finally:
        driver.quit()

    date_str = datetime.now().strftime("%Y-%m-%d")
    out_path = os.path.join(output_dir, f"dialog_{date_str}.csv")
    df.to_csv(out_path, index=False, encoding="utf-8-sig")

    return f"TOTAL: {len(df)} satır, dosya: {os.path.basename(out_path)}"


