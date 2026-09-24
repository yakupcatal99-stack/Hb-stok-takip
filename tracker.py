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

ALLOWED_SELLERS = {
    "hepsiburada",
    "hp store türkiye",
}

BASE_URL = "https://www.hepsiburada.com"
STATE_FILE = Path("state.json")
DEBUG_FILE = Path("hepsiburada_debug.html")


def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError("Telegram secret bilgileri eksik.")

    send_url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    response = requests.post(
        send_url,
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
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
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
                f"HTTP {response.status_code}, "
                f"{len(response.text)} byte"
            )

        except Exception as exc:
            last_error = exc
            print(f"Istek hatasi: {exc}")

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
        count = int(match.group(1).replace(".", ""))

        if 0 < count < 1000:
            return count

    match = re.search(
        r'"totalProductCount"\s*:\s*(\d+)',
        html,
        re.IGNORECASE,
    )

    if match:
        count = int(match.group(1))

        if 0 < count < 1000:
            return count

    return None


def parse_tr_price(value):
    if not value:
        return None

    cleaned = re.sub(r"[^\d.,]", "", value)

    if not cleaned:
        return None

    try:
        if "," in cleaned:
            cleaned = cleaned.replace(".", "")
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(".", "")

        price = float(cleaned)

        if price <= 0:
            return None

        return price

    except ValueError:
        return None


def format_price(price):
    if price is None:
        return "Fiyat okunamadi"

    value = int(round(price))

    return f"{value:,}".replace(",", ".") + " TL"


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

    allowed_sellers = {
        seller.casefold()
        for seller in ALLOWED_SELLERS
    }

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

        if seller.casefold() not in allowed_sellers:
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
            "initialized": False,
            "count": None,
            "omen_keys": [],
            "target_keys": [],
        }

    try:
        with STATE_FILE.open(
            "r",
            encoding="utf-8",
        ) as file:
            state = json.load(file)

        if not isinstance(state, dict):
            raise ValueError("State formati gecersiz.")

        return state

    except Exception as exc:
        print(f"State okunamadi: {exc}")

        return {
            "initialized": False,
            "count": None,
            "omen_keys": [],
            "target_keys": [],
        }


def save_state(count, omen_keys, target_keys):
    state = {
        "initialized": True,
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
    seller = html_lib.escape(product["seller"])
    product_url = html_lib.escape(
        product["url"],
        quote=True,
    )

    return (
        "🚨🚨 <b>HEDEF OMEN 16 STOKTA!</b> 🚨🚨\n\n"
        f"<b>{title}</b>\n\n"
        "🎯 CE2B2EA / AP0010NT hedef modeli\n"
        f"💰 <b>{format_price(product['price'])}</b>\n"
        f"{classify_target_price(product['price'])}\n"
        f"🏪 Satici: <b>{seller}</b>\n\n"
        f'⚡ <a href="{product_url}">URUNU HEMEN AC</a>'
    )


def omen_message(product):
    title = html_lib.escape(product["title"])
    seller = html_lib.escape(product["seller"])
    product_url = html_lib.escape(
        product["url"],
        quote=True,
    )

    return (
        "🚨 <b>YENI HP OMEN STOKTA!</b>\n\n"
        f"<b>{title}</b>\n\n"
        f"💰 <b>{format_price(product['price'])}</b>\n"
        f"🏪 Satici: <b>{seller}</b>\n\n"
        f'🔗 <a href="{product_url}">OMEN URUNUNU AC</a>'
    )


def count_change_message(previous_count, current_count):
    difference = current_count - previous_count

    if difference > 0:
        return (
            "🔔 <b>STOK ARTTI</b>\n\n"
            f"Onceki: <b>{previous_count}</b>\n"
            f"Guncel: <b>{current_count}</b>\n"
            f"Degisim: <b>+{difference}</b>"
        )

    return (
        "⚠️ <b>STOK AZALDI</b>\n\n"
        f"Onceki: <b>{previous_count}</b>\n"
        f"Guncel: <b>{current_count}</b>\n"
        f"Degisim: <b>{difference}</b>"
    )


def check_stock():
    print("=" * 60)
    print("HP OMEN TRACKER BASLADI")
    print(f"Referans urun sayisi: {REFERANS_SAYI}")

    html = fetch_page()

    current_count = get_product_count(html)

    if current_count is None:
        DEBUG_FILE.write_text(
            html,
            encoding="utf-8",
        )

        raise RuntimeError(
            "Urun sayisi okunamadi. "
            "Telegram bildirimi uretilmedi."
        )

    products = extract_products(html)

    if not products:
        DEBUG_FILE.write_text(
            html,
            encoding="utf-8",
        )

        raise RuntimeError(
            "Urun kartlari parse edilemedi. "
            "Telegram bildirimi uretilmedi."
        )

    omens = [
        product
        for product in products
        if product["is_omen"]
    ]

    targets = [
        product
        for product in products
        if product["is_exact_target"]
    ]

    print(
        f"Toplam: {current_count} | "
        f"Parse edilen kart: {len(products)} | "
        f"Omen: {len(omens)} | "
        f"Exact target: {len(targets)}"
    )

    state = load_state()

    previous_count = state.get("count")

    initialized = bool(
        state.get("initialized")
        or previous_count is not None
    )

    old_omen_keys = set(
        state.get("omen_keys", [])
    )

    old_target_keys = set(
        state.get("target_keys", [])
    )

    current_omen_keys = {
        product["key"]
        for product in omens
    }

    current_target_keys = {
        product["key"]
        for product in targets
    }

    # CE2B2EA her zaman oncelikli.
    for product in targets:
        if product["key"] not in old_target_keys:
            print(
                f"EXACT TARGET: {product['title']}"
            )

            send_telegram_message(
                target_message(product)
            )

    # Yalnizca YENI Omen bildir.
    # State ilk kez kuruluyorsa mevcut Omen'leri spamleme.
    if initialized:
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

    else:
        print(
            "Ilk baseline: mevcut Omen'ler "
            "sessizce state'e kaydediliyor."
        )

    # STOK SAYISI TAKIBI
    #
    # 28 -> 27 = -1 bildirim
    # 27 -> 28 = +1 bildirim
    # 28 -> 29 = +1 bildirim
    # 29 -> 28 = -1 bildirim
    # ayni sayi = sessiz

    if previous_count is None:

        if current_count != REFERANS_SAYI:
            send_telegram_message(
                count_change_message(
                    REFERANS_SAYI,
                    current_count,
                )
            )

        else:
            print(
                f"Ilk stok baseline'i: {current_count}"
            )

    elif current_count != previous_count:

        print(
            f"Stok degisti: "
            f"{previous_count} -> {current_count}"
        )

        send_telegram_message(
            count_change_message(
                previous_count,
                current_count,
            )
        )

    else:
        print(
            f"Stok degismedi: {current_count}"
        )

    save_state(
        current_count,
        current_omen_keys,
        current_target_keys,
    )

    print("Kontrol tamamlandi.")
    print("=" * 60)


if __name__ == "__main__":
    try:
        check_stock()

    except Exception as exc:
        print(f"KRITIK HATA: {exc}")
        raise
