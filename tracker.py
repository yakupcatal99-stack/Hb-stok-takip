import os
import re
import requests

# Takip edilecek filtreli link
URL = "https://www.hepsiburada.com/laptop-notebook-dizustu-bilgisayarlar-c-98?filtreler=ekrankarti:Nvidia%E2%82%AC20GeForce%E2%82%AC20RTX%E2%82%AC205060,Nvidia%E2%82%AC20GeForce%E2%82%AC20RTX%E2%82%AC205070;satici:Hepsiburada"

# Sayfadaki mevcut referans ürün sayısı (12)
ESIK_URUN_SAYISI = 12

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8",
}

def telegram_bildirim_gonder(mesaj):
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram kimlik bilgileri eksik!")
        return
    api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": mesaj,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    r = requests.post(api_url, json=payload, timeout=10)
    print(f"Telegram Yanıt Kodu: {r.status_code}")

def kontrol_et():
    try:
        response = requests.get(URL, headers=HEADERS, timeout=20)
        if response.status_code != 200:
            print(f"Hepsiburada yanıt kodu: {response.status_code}")
            return

        html = response.text
        eslesme = re.search(r'\((\d+)\s*ürün\)', html, re.IGNORECASE)
        if not eslesme:
            eslesme = re.search(r'"totalProductCount":\s*(\d+)', html)
        if not eslesme:
            eslesme = re.search(r'(\d+)\s*ürün', html, re.IGNORECASE)

        if eslesme:
            guncel_sayi = int(eslesme.group(1))
            print(f"Tespit Edilen Ürün: {guncel_sayi} | Eşik: {ESIK_URUN_SAYISI}")

            omen_var_mi = "omen" in html.lower()

            if guncel_sayi > ESIK_URUN_SAYISI or omen_var_mi:
                mesaj = (
                    f"🚨 <b>HEPSİBURADA'YA YENİ STOK GİRDİ!</b>\n\n"
                    f"📦 Ürün Sayısı: <b>{guncel_sayi}</b>\n"
                    f"🔗 <a href='{URL}'>Hemen Ürünleri İncele</a>"
                )
                telegram_bildirim_gonder(mesaj)
                print("Bildirim Telegram'a iletildi.")
            else:
                print("Stok artışı yok, nöbet devam ediyor.")
        else:
            print("Ürün sayısı HTML içinde bulunamadı.")
    except Exception as e:
        print(f"Bağlantı hatası: {e}")

if __name__ == "__main__":
    kontrol_et()
