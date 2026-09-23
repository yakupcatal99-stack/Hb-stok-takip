import os
import re
import json
import time
import html as html_lib
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs

from bs4 import BeautifulSoup
from curl_cffi import requests


TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

URL = (
    "https://www.hepsiburada.com/"
    "laptop-notebook-dizustu-bilgisayarlar-c-98"
    "?filtreler=satici%3AHepsiburada%2CHP%E2%82%AC20Store%E2%82%AC20T%E2%82%ACC3%E2%82%ACBCrkiye"
    "%3Bekrankarti%3ANvidia%E2%82%AC20GeForce%E2%82%AC20RTX%E2%82%AC205060"
    "%2CNvidia%E2%82%AC20GeForce%E2%82%AC20RTX%E2%82%AC205070"
    "&siralama=artanfiyat"
)

REFERANS_SAYI = 28

TARGET_IDENTIFIERS = (
    "ce2b2ea",
    "ap0010nt",
    "hbcv0000aeptml",
)

TARGET_GOOD_PRICE = 69999
TARGET_HIGH_PRICE = 79999

STATE_FILE = Path("state.json")
DEBUG_FILE = Path("hepsiburada_debug.html")

BASE_URL = "https://www.hepsiburada.com"

ALLOWED_SELLERS = {
    "hepsiburada",
    "hp store türkiye",
}


def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError("Telegram secret bilgileri eksik.")

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    response = requests.post(
        url,
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        },
        timeout=20,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"Telegram HTTP {response.status_code}: "
            f"{response.text[:500]}"
        )

    print("Telegram bildirimi gonderildi.")


def fetch_page():
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "no-cache",
    }

    last_error = None

    for attempt in range(1, 4):
        try:
            response = requests.get(
                URL,
                headers=headers,
                impersonate="chrome124",
                timeout=30,
            )

            print(
                f"Hepsiburada HTTP: {response.status_code} "
                f"(deneme {attempt}/3)"
            )

            if response.status_code == 200 and len(response.text) > 10000:
                return response.text

            last_error = RuntimeError(
                f"HTTP {response.status_code}"
            )

        except Exception as exc:
            last_error = exc

        if attempt < 3:
            time.sleep(3)

    raise RuntimeError(
        f"Hepsiburada sayfasi alinamadi: {last_error}"
    )


def get_product_count(html):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    match = re.search(
        r"Toplam\s+[\d.]+\s*/\s*([\d.]+)\s+ürün",
        text,
        re.IGNORECASE,
    )

    if match:
        return int(match.group(1).replace(".", ""))

    match = re.search(
        r'"totalProductCount"\s*:\s*(\d+)',
        html,
        re.IGNORECASE,
    )

    if match:
        return int(match.group(1))

    return None


def parse_tr_price(value):
    if not value:
        return None

    value = re.sub(r"[^\d.,]", "", value)

    if not value:
        return None

    try:
        if "," in value:
            value = value.replace(".", "")
            value = value.replace(",", ".")
        else:
            value = value.replace(".", "")

        return float(value)

    except ValueError:
        return None


def format_price(price):
    if price is None:
        return "Fiyat okunamadi"

    integer = int(round(price))

    return f"{integer:,}".replace(",", ".") + " TL"


def classify_target_price(price):
    if price is None:
        return "⚪ Fiyat siniflandirilamadi"

    if price <= TARGET_GOOD_PRICE:
        return "🔥 <b>TARIHSEL HEDEF / FIRSAT BANDINDA</b>"

    if price <= TARGET_HIGH_PRICE:
        return "🟡 <b>Tarihsel hedef bandinin ustunde</b>"

    return "🔴 <b>Tarihsel fiyat seviyesinin belirgin ustunde</b>"


def product_key_from_url(url):
    match = re.search(
        r"-(?:p|pm)-(HB[A-Z0-9]+)",
        url,
        re.IGNORECASE,
    )

    if match:
        return match.group(1).upper()

    return url.split("?")[0].lower()


def extract_products(html):
    soup = BeautifulSoup(html, "html.parser")

    products = []
    seen = set()

    cards = soup.select(
        'li[id^="i"][class*="productListContent"]'
    )

    print(f"Ana liste kart adayi: {len(cards)}")

    for card in cards:
        link = card.select_one(
            'h2[data-test-id^="title-"] a[href*="-p-HB"], '
            'h2[data-test-id^="title-"] a[href*="-pm-HB"]'
        )

        if link is None:
            continue

        title = (
            link.get("title")
            or link.get_text(" ", strip=True)
        )

        href = link.get("href", "").strip()

        if not title or not href:
            continue

        product_url = urljoin(BASE_URL, href)

        query = parse_qs(
            urlparse(product_url).query
        )

        seller = query.get(
            "magaza",
            [""],
        )[0].strip()

        if seller.casefold() not in {
            x.casefold() for x in ALLOWED_SELLERS
        }:
            continue

        key = product_key_from_url(product_url)

        if key in seen:
            continue

        seen.add(key)

        price_element = card.select_one(
            '[data-test-id^="final-price-"]'
        )

        price_text = (
            price_element.get_text(" ", strip=True)
            if price_element
            else None
        )

        price = parse_tr_price(price_text)

        searchable = (
            f"{title} {product_url}"
        ).casefold()

        is_omen = "omen" in searchable

        is_exact_target = any(
            identifier.casefold() in searchable
            for identifier in TARGET_IDENTIFIERS
        )

        products.append(
            {
                "key": key,
                "title": title,
                "url": product_url,
                "seller": seller,
                "price": price,
                "is_omen": is_omen,
                "is_exact_target": is_exact_target,
            }
        )

    return products


def load_state():
    if not STATE_FILE.exists():
        return {
            "count": None,
            "omen_keys": [],
            "target_keys": [],
        }

    try:
        with STATE_FILE.open(
            "r",
            encoding="utf-8",
        ) as file:
            return json.load(file)

    except Exception:
        return {
            "count": None,
            "omen_keys": [],
            "target_keys": [],
        }


def save_state(count, omen_keys, target_keys):
    state = {
        "count": count,
        "omen_keys": sorted(omen_keys),
        "target_keys": sorted(target_keys),
    }

    with STATE_FILE.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            state,
            file,
            ensure_ascii=False,
            indent=2,
        )


def target_message(product):
    title = html_lib.escape(product["title"])
    url = html_lib.escape(
        product["url"],
        quote=True,
    )

    seller = html_lib.escape(product["seller"])

    return (
        "🚨🚨 <b>HEDEF OMEN 16 STOKTA!</b> 🚨🚨\n\n"
        f"<b>{title}</b>\n\n"
        "🎯 CE2B2EA / AP0010NT hedef modeli\n"
        f"💰 <b>{format_price(product['price'])}</b>\n"
        f"{classify_target_price(product['price'])}\n"
        f"🏪 Satıcı: <b>{seller}</b>\n\n"
        f'⚡ <a href="{url}">URUNU HEMEN AC</a>'
    )


def omen_message(product):
    title = html_lib.escape(product["title"])
    url = html_lib.escape(
        product["url"],
        quote=True,
    )

    seller = html_lib.escape(product["seller"])

    return (
        "🚨 <b>HP OMEN STOKTA!</b>\n\n"
        f"<b>{title}</b>\n\n"
        f"💰 <b>{format_price(product['price'])}</b>\n"
        f"🏪 Satıcı: <b>{seller}</b>\n\n"
        f'🔗 <a href="{url}">OMEN URUNUNU AC</a>'
    )


def count_message(count):
    if count > REFERANS_SAYI:
        diff = count - REFERANS_SAYI

        return (
            "🔔 <b>YENI STOK GIRDI</b>\n\n"
            f"Referans: <b>{REFERANS_SAYI}</b>\n"
            f"Guncel: <b>{count}</b>\n"
            f"Degisim: <b>+{diff}</b>"
        )

    diff = REFERANS_SAYI - count

    return (
        "⚠️ <b>STOK AZALDI</b>\n\n"
        f"Referans: <b>{REFERANS_SAYI}</b>\n"
        f"Guncel: <b>{count}</b>\n"
        f"Degisim: <b>-{diff}</b>"
    )


def check_stock():
    print("=" * 50)
    print("HP OMEN TRACKER BASLADI")
    print(f"Referans: {REFERANS_SAYI}")

    html = fetch_page()

    current_count = get_product_count(html)

    if current_count is None:
        DEBUG_FILE.write_text(
            html,
            encoding="utf-8",
        )

        raise RuntimeError(
            "Urun sayisi okunamadi."
        )

    products = extract_products(html)

    if not products:
        DEBUG_FILE.write_text(
            html,
            encoding="utf-8",
        )

        raise RuntimeError(
            "Urun kartlari parse edilemedi."
        )

    omens = [
        p for p in products
        if p["is_omen"]
    ]

    targets = [
        p for p in products
        if p["is_exact_target"]
    ]

    print(
        f"Toplam: {current_count} | "
        f"Parse edilen kart: {len(products)} | "
        f"Omen: {len(omens)} | "
        f"Exact target: {len(targets)}"
    )

    state = load_state()

    previous_count = state.get("count")

    old_omen_keys = set(
        state.get("omen_keys", [])
    )

    old_target_keys = set(
        state.get("target_keys", [])
    )

    current_omen_keys = {
        p["key"] for p in omens
    }

    current_target_keys = {
        p["key"] for p in targets
    }

    for product in targets:
        if product["key"] not in old_target_keys:
            print(
                f"EXACT TARGET: {product['title']}"
            )

            send_telegram_message(
                target_message(product)
            )

    for product in omens:
        if (
            product["key"] not in old_omen_keys
            and not product["is_exact_target"]
        ):
            print(
                f"YENI OMEN: {product['title']}"
            )

            send_telegram_message(
                omen_message(product)
            )

    if (
        current_count != REFERANS_SAYI
        and current_count != previous_count
    ):
        send_telegram_message(
            count_message(current_count)
        )

    elif current_count == REFERANS_SAYI:
        print(
            f"Stok stabil: {current_count}"
        )

    else:
        print(
            f"Stok daha once bildirildi: {current_count}"
        )

    save_state(
        current_count,
        current_omen_keys,
        current_target_keys,
    )

    print("Kontrol tamamlandi.")
    print("=" * 50)


if __name__ == "__main__":
    try:
        check_stock()

    except Exception as exc:
        print(f"KRITIK HATA: {exc}")
        raise
