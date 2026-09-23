import os
import re
from curl_cffi import requests

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Sadece Hepsiburada resmi satıcılı dizüstü bilgisayarlar listesi
URL = "https://www.hepsiburada.com/laptop-notebook-dizustu-bilgisayarlar-c-98?filtreler=satici:Hepsiburada"

# Sayfadaki güncel ürün tabanı (21 ürün)
ESIK_URUN_SAYISI = 21

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
        print(f"Telegram hatası: {e}")

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

    # Toplam listelenen ürün sayısını yakala
    match = re.search(r'(\d+)\s+ürün', html)
    guncel_sayi = int(match.group(1)) if match else None

    # Ürün kartlarındaki başlıkları filtre menüsünden ayırarak tara
    # Ürün başlıklarında Omen geçişini denetler
    omen_var = bool(re.search(r'title=["\'][^"\']*omen[^"\']*["\']', html, re.IGNORECASE)) or \
               bool(re.search(r'>[^<]*hp\s+omen[^<]*<', html, re.IGNORECASE))

    print(f"Tespit Edilen Ürün: {guncel_sayi} | Eşik: {ESIK_URUN_SAYISI}")

    if omen_var:
        msg = f"🚨 <b>HP OMEN STOKTA OLABİLİR!</b>\n\nResmi Hepsiburada listesinde Omen tespit edildi.\n\nLink: {URL}"
        send_telegram_message(msg)
        print("Bildirim gönderildi: HP Omen tespit edildi!")
    elif guncel_sayi and guncel_sayi > ESIK_URUN_SAYISI:
        msg = f"🔔 <b>HEPSİBURADA YENİ STOK GİRİŞİ!</b>\n\nÜrün sayısı {guncel_sayi}'e yükseldi (Eşik: {ESIK_URUN_SAYISI}).\n\nLink: {URL}"
        send_telegram_message(msg)
        print("Bildirim gönderildi: Stok sayısı arttı!")
    else:
        print("Ne Omen ne de yeni stok artışı var. Nöbet sessizce devam ediyor.")

if __name__ == "__main__":
    check_stock()
