import os
import re
import json
import time
import html as html_lib
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from curl_cffi import requests


# ============================================================
# AYARLAR
# ============================================================

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Hepsiburada + HP Store Turkiye
# RTX 5060 + RTX 5070
# Artan fiyat siralamasi
URL = (
    "https://www.hepsiburada.com/"
    "laptop-notebook-dizustu-bilgisayarlar-c-98"
    "?filtreler=satici%3AHepsiburada%2CHP%E2%82%AC20Store%E2%82%AC20T%E2%82%ACC3%E2%82%ACBCrkiye"
    "%3Bekrankarti%3ANvidia%E2%82%AC20GeForce%E2%82%AC20RTX%E2%82%AC205060"
    "%2CNvidia%E2%82%AC20GeForce%E2%82%AC205070"
    "&siralama=artanfiyat"
)

REFERANS_SAYI = 28

# Birincil hedef:
# HP Omen 16-AP0010NT
# HP kodu: CE2B2EA
# Hepsiburada kodu: HBCV0000AEPTML
TARGET_IDENTIFIERS = (
    "ce2b2ea",
    "ap0010nt",
    "hbcv0000aeptml",
)

# Exact hedef icin fiyat etiketi.
# Fiyat alarmi ENGELLEMEZ; sadece mesaji siniflandirir.
TARGET_GOOD_PRICE = 69999
TARGET_HIGH_PRICE = 79999

STATE_FILE = Path("state.json")
DEBUG_FILE = Path("hepsiburada_debug.html")

BASE_URL = "https://www.hepsiburada.com"


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN veya TELEGRAM_CHAT_ID eksik."
        )

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

    print("Telegram bildirimi basariyla gonderildi.")


# ============================================================
# HTTP
# ============================================================

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
                f"Gecersiz yanit: HTTP {response.status_code}, "
                f"{len(response.text)} byte"
            )

        except Exception as exc:
            last_error = exc
            print(f"Istek hatasi: {exc}")

        if attempt < 3:
            time.sleep(4)

    raise RuntimeError(
        f"Hepsiburada sayfasi alinamadi: {last_error}"
    )


# ============================================================
# URUN SAYISI
# ============================================================

def get_product_count(html):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    # En guvenilir gorunen yapi:
    # "Toplam 28 / 28 urun"
    # veya
    # "Toplam 36 / 87 urun"
    patterns = [
        r"Toplam\s+[\d.]+\s*/\s*([\d.]+)\s+ürün",
        r"Toplam\s+[\d.]+\s*/\s*([\d.]+)\s+urun",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = int(match.group(1).replace(".", ""))
            if 0 < value < 1000:
                return value

    # Ikinci guvenli fallback:
    # "Laptop Modelleri (28 urun)"
    patterns = [
        r"Laptop\s+Modelleri\s*\(\s*([\d.]+)\s+ürün\s*\)",
        r"Laptop\s+Modelleri\s*\(\s*([\d.]+)\s+urun\s*\)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = int(match.group(1).replace(".", ""))
            if 0 < value < 1000:
                return value

    # HTML / JSON icindeki spesifik toplam alanlari
    json_patterns = [
        r'"totalProductCount"\s*:\s*(\d+)',
        r'"totalProducts"\s*:\s*(\d+)',
    ]

    for pattern in json_patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            value = int(match.group(1))
            if 0 < value < 1000:
                return value

    return None


# ============================================================
# FIYAT
# ============================================================

def parse_tr_price(value):
    """
    Ornekler:
      67.999,00 TL -> 67999.00
      67.999 TL    -> 67999.00
      67999 TL     -> 67999.00
    """

    if not value:
        return None

    cleaned = re.sub(r"[^\d.,]", "", value)

    if not cleaned:
        return None

    try:
        if "," in cleaned:
            # Turkce:
            # 67.999,00 -> 67999.00
            cleaned = cleaned.replace(".", "")
            cleaned = cleaned.replace(",", ".")
        else:
            # 67.999 -> 67999
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
        return "⚪ Fiyat etiketi belirlenemedi"

    if price <= TARGET_GOOD_PRICE:
        return "🔥 <b>TARIHSEL HEDEF / FIRSAT BANDINDA</b>"

    if price <= TARGET_HIGH_PRICE:
        return "🟡 <b>Tarihsel hedef bandinin ustunde</b>"

    return "🔴 <b>Tarihsel fiyat seviyesinin belirgin ustunde</b>"


# ============================================================
# ANA URUN KARTLARI
# ============================================================

def product_key_from_url(url):
    match = re.search(
        r"-(?:p|pm)-(HB[A-Z0-9]+)",
        url,
        re.IGNORECASE,
    )

    if match:
        return match.group(1).upper()

    return url.lower().split("?")[0]


def extract_products(html):
    soup = BeautifulSoup(html, "html.parser")
    products = []
    seen = set()

    # Hepsiburada ana liste kartlari.
    # Carousel / filtre menusu yerine ana productListContent alani.
    cards = soup.select('li[class*="productListContent"]')

    print(f"Ana liste kart adayi: {len(cards)}")

    for card in cards:
        title_element = card.select_one(
            'h3[data-test-id="product-card-name"]'
        )

        if not title_element:
            continue

        title = title_element.get_text(" ", strip=True)

        if not title:
            continue

        link_element = title_element.find_parent("a", href=True)

        if link_element is None:
            link_element = card.select_one(
                'a[href*="-p-HB"], a[href*="-pm-HB"]'
            )

        if link_element is None:
            continue

        href = link_element.get("href", "").strip()

        if not href:
            continue

        url = urljoin(BASE_URL, href)
        key = product_key_from_url(url)

        if key in seen:
            continue

        seen.add(key)

        price_element = (
            card.select_one(
                '[data-test-id="price-current-price"]'
            )
            or card.select_one(
                '[data-test-id="default-price"]'
            )
        )

        price_text = (
            price_element.get_text(" ", strip=True)
            if price_element
            else None
        )

        price = parse_tr_price(price_text)

        searchable = f"{title} {url}".lower()

        is_omen = "omen" in searchable

        is_exact_target = any(
            identifier in searchable
            for identifier in TARGET_IDENTIFIERS
        )

        products.append(
            {
                "key": key,
                "title": title,
                "url": url,
                "price": price,
                "price_text": price_text,
                "is_omen": is_omen,
                "is_exact_target": is_exact_target,
            }
        )

    return products


# ============================================================
# STATE / TEKRAR ALARM ENGELI
# ============================================================

def load_state():
    if not STATE_FILE.exists():
        return {
            "count": None,
            "omen_keys": [],
        }

    try:
        with STATE_FILE.open(
            "r",
            encoding="utf-8",
        ) as file:
            state = json.load(file)

        if not isinstance(state, dict):
            raise ValueError("State dict degil.")

        return state

    except Exception as exc:
        print(f"State okunamadi, sifirlanacak: {exc}")
        return {
            "count": None,
            "omen_keys": [],
        }


def save_state(count, omen_keys):
    state = {
        "count": count,
        "omen_keys": sorted(omen_keys),
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


# ============================================================
# MESAJLAR
# ============================================================

def target_message(product):
    title = html_lib.escape(product["title"])
    url = html_lib.escape(product["url"], quote=True)

    price_text = format_price(product["price"])
    price_label = classify_target_price(product["price"])

    return (
        "🚨🚨 <b>HEDEF OMEN 16 STOKTA!</b> 🚨🚨\n\n"
        f"<b>{title}</b>\n\n"
        "🎯 CE2B2EA / AP0010NT hedef modeli eslesti.\n"
        f"💰 <b>{price_text}</b>\n"
        f"{price_label}\n\n"
        "✅ Filtre: Hepsiburada / HP Store Turkiye\n"
        "✅ GPU havuzu: RTX 5060 / RTX 5070\n\n"
        f'⚡ <a href="{url}">URUNU HEMEN AC</a>'
    )


def omen_message(product):
    title = html_lib.escape(product["title"])
    url = html_lib.escape(product["url"], quote=True)

    price_text = format_price(product["price"])

    return (
        "🚨 <b>YENI HP OMEN TESPIT EDILDI!</b>\n\n"
        f"<b>{title}</b>\n\n"
        f"💰 <b>{price_text}</b>\n\n"
        "✅ Hepsiburada / HP Store Turkiye filtreli "
        "gercek urun listesinde gorundu.\n\n"
        f'🔗 <a href="{url}">OMEN URUNUNU AC</a>'
    )


def count_message(current_count):
    if current_count > REFERANS_SAYI:
        diff = current_count - REFERANS_SAYI

        return (
            "🔔 <b>YENI LAPTOP STOKU GIRDI</b>\n\n"
            f"Referans: <b>{REFERANS_SAYI}</b>\n"
            f"Guncel: <b>{current_count}</b>\n"
            f"Degisim: <b>+{diff}</b>\n\n"
            "Hepsiburada / HP Store Turkiye\n"
            "RTX 5060 / RTX 5070 havuzu degisti."
        )

    diff = REFERANS_SAYI - current_count

    return (
        "⚠️ <b>LAPTOP STOKU AZALDI</b>\n\n"
        f"Referans: <b>{REFERANS_SAYI}</b>\n"
        f"Guncel: <b>{current_count}</b>\n"
        f"Degisim: <b>-{diff}</b>\n\n"
        "Hepsiburada / HP Store Turkiye\n"
        "RTX 5060 / RTX 5070 havuzu degisti."
    )


# ============================================================
# ANA KONTROL
# ============================================================

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
            "Ana urun sayisi guvenilir sekilde okunamadi. "
            f"HTML {DEBUG_FILE} dosyasina kaydedildi. "
            "Telegram alarmi uretilmedi."
        )

    products = extract_products(html)

    if not products:
        DEBUG_FILE.write_text(
            html,
            encoding="utf-8",
        )

        raise RuntimeError(
            "Ana urun kartlari parse edilemedi. "
            f"HTML {DEBUG_FILE} dosyasina kaydedildi. "
            "Sahte Telegram alarmi uretilmedi."
        )

    omens = [
        product
        for product in products
        if product["is_omen"]
    ]

    targets = [
        product
        for product in omens
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
    previous_omen_keys = set(
        state.get("omen_keys", [])
    )

    current_omen_keys = {
        product["key"]
        for product in omens
    }

    new_omen_keys = (
        current_omen_keys - previous_omen_keys
    )

    # --------------------------------------------------------
    # 1. EN YUKSEK ONCELIK:
    # CE2B2EA / AP0010NT / HBCV0000AEPTML
    # --------------------------------------------------------

    new_targets = [
        product
        for product in targets
        if product["key"] in new_omen_keys
    ]

    for product in new_targets:
        print(
            "EXACT TARGET YENI STOK: "
            f'{product["title"]}'
        )

        send_telegram_message(
            target_message(product)
        )

    # --------------------------------------------------------
    # 2. DIGER YENI OMENLER
    # Exact target burada tekrar mesaj almasin.
    # --------------------------------------------------------

    new_generic_omens = [
        product
        for product in omens
        if (
            product["key"] in new_omen_keys
            and not product["is_exact_target"]
        )
    ]

    for product in new_generic_omens:
        print(
            "YENI OMEN: "
            f'{product["title"]}'
        )

        send_telegram_message(
            omen_message(product)
        )

    # --------------------------------------------------------
    # 3. HAVUZ SAYISI DEGISIMI
    #
    # 28 -> alarm yok
    # 29 -> +1 alarm
    # 29 -> 29 -> tekrar alarm yok
    # 29 -> 30 -> yeni alarm
    # 30 -> 28 -> normale dondu, sessiz
    # 28 -> 27 -> -1 alarm
    # --------------------------------------------------------

    if (
        current_count != REFERANS_SAYI
        and current_count != previous_count
    ):
        print(
            f"Stok sayisi degisti: "
            f"{previous_count} -> {current_count}"
        )

        send_telegram_message(
            count_message(current_count)
        )

    elif current_count == REFERANS_SAYI:
        print(
            f"Stok referansta stabil: {current_count}"
        )

    else:
        print(
            f"Stok farkli ama daha once bildirildi: "
            f"{current_count}"
        )

    # --------------------------------------------------------
    # State her basarili kontrolden sonra guncellenir.
    # Omen kaybolursa listeden silinir.
    # Tekrar gelirse yeniden alarm verir.
    # --------------------------------------------------------

    save_state(
        current_count,
        current_omen_keys,
    )

    print("Kontrol tamamlandi.")
    print("=" * 60)


if __name__ == "__main__":
    try:
        check_stock()

    except Exception as exc:
        print(f"KRITIK HATA: {exc}")
        raise
