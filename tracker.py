import os
import re
from curl_cffi import requests

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Hepsiburada resmi satıcılı dizüstü bilgisayarlar listesi
URL = "https://www.hepsiburada.com/laptop-notebook-dizustu-bilgisayarlar-c-98?filtreler=satici:Hepsiburada"

# Takip edilen referans ürün tabanı
REFERANS_SAYI = 21

def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram bilgileri eksik!")
        return
    send_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        requests.post(send_url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram gönderim hatası: {e}")

def get_product_count(html):
    # 1. Hepsiburada arka plan JSON verilerini tara
    patterns = [
        r'["\']totalProductCount["\']\s*:\s*(\d+)',
        r'["\']totalCount["\']\s*:\s*(\d+)',
        r'["\']totalItems["\']\s*:\s*(\d+)',
        r'(\d+)\s*ürün\s*bulundu',
        r'(\d+)\s*ürün'
    ]
    for p in patterns:
        m = re.search(p, html, re.IGNORECASE)
        if m and int(m.group(1)) > 0:
            return int(m.group(1))

    # 2. Yedek Plan: Sayfadaki gerçek ürün kartı linklerini (-p-HB...) say
    product_ids = set(re.findall(r'-p-(HB[A-Z0-9]+)', html))
    if product_ids:
        return len(product_ids)

    return None

def check_stock():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    try:
        response = requests.get(URL, headers=headers, impersonate="chrome124", timeout=20)
        print(f"Hepsiburada yanıt kodu: {response.status_code}")
    except Exception as e:
        print(f"İstek hatası: {e}")
        return

    if response.status_code != 200:
        print("Sayfaya erişilemedi.")
        return

    html = response.text

    # Ürün sayısını tespit et
    guncel_sayi = get_product_count(html)

    # SADECE gerçek ürün kartlarında HP Omen ara (menüdeki yazıları eler)
    omen_var = bool(re.search(r'href=["\'][^"\']*omen[^"\']*-p-HB', html, re.IGNORECASE))

    print(f"Tespit Edilen Ürün: {guncel_sayi} | Referans Taban: {REFERANS_SAYI} | Omen Kartı: {omen_var}")

    # 1. ÖNCELİK: HP Omen tespiti (sayıya bakılmaksızın en acil alarm)
    if omen_var:
        msg = (
            f"🚨 <b>HP OMEN GERÇEKTEN STOKTA!</b>\n\n"
            f"Resmi Hepsiburada listesinde HP Omen ürün kartı açıldı!\n\n"
            f"Toplam Ürün: {guncel_sayi}\n"
            f"Link: {URL}"
        )
        send_telegram_message(msg)
        print("Bildirim gönderildi: Gerçek HP Omen tespit edildi!")

    # 2. ÖNCELİK: Stok artışı (> 21) - Kaç ürün girerse girsin dinamik hesaplar
    elif guncel_sayi is not None and guncel_sayi > REFERANS_SAYI:
        fark = guncel_sayi - REFERANS_SAYI
        msg = (
            f"🔔 <b>HEPSİBURADA'YA YENİ STOK GİRDİ!</b>\n\n"
            f"Ürün sayısı <b>{REFERANS_SAYI}</b> iken <b>{guncel_sayi}</b> oldu (<b>+{fark}</b> yeni ürün eklendi).\n\n"
            f"Depoya yeni bilgisayar girişi yapıldı, hemen kontrol edin:\n"
            f"Link: {URL}"
        )
        send_telegram_message(msg)
        print(f"Bildirim gönderildi: Stok sayısı arttı ({guncel_sayi}).")

    # 3. ÖNCELİK: Stok düşüşü (< 21) - Kaç ürün biterse bitsin dinamik hesaplar
    elif guncel_sayi is not None and guncel_sayi < REFERANS_SAYI:
        fark = REFERANS_SAYI - guncel_sayi
        msg = (
            f"⚠️ <b>HEPSİBURADA'DA STOK DÜŞTÜ!</b>\n\n"
            f"Ürün sayısı <b>{REFERANS_SAYI}</b> iken <b>{guncel_sayi}</b> seviyesine indi (<b>-{fark}</b> ürün tükendi).\n\n"
            f"Link: {URL}"
        )
        send_telegram_message(msg)
        print(f"Bildirim gönderildi: Stok sayısı azaldı ({guncel_sayi}).")

    else:
        print(f"Durum stabil. Ürün sayısı {guncel_sayi} ve Omen yok. Nöbet sessizce devam ediyor.")

if __name__ == "__main__":
    check_stock()
