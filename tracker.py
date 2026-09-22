import os
import re
import sys
import subprocess

# curl_cffi kütüphanesini otomatik kur (403 bot engelini aşmak için)
try:
    from curl_cffi import requests
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "curl_cffi"])
    from curl_cffi import requests

# Takip edilecek Hepsiburada filtreli URL'si (RTX 5060 + 5070 | Satıcı: Hepsiburada)
URL = "https://www.hepsiburada.com/laptop-notebook-dizustu-bilgisayarlar-c-98?filtreler=ekrankarti:Nvidia%E2%82%AC20GeForce%E2%82%AC20RTX%E2%82%AC205060,Nvidia%E2%82%AC20GeForce%E2%82%AC20RTX%E2%82%AC205070;satici:Hepsiburada"

# Sayfadaki güncel referans ürün sayısı
ESIK_URUN_SAYISI = 21

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

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
    print(f"Telegram API Yanıtı: {r.status_code}")

def kontrol_et():
    try:
        # Chrome tarayıcısının TLS parmak izini taklit ederek Hepsiburada'ya istek atıyoruz
        response = requests.get(URL, impersonate="chrome", timeout=25)
        print(f"Hepsiburada yanıt kodu: {response.status_code}")

        if response.status_code != 200:
            print("Sayfa güvenlik duvarı tarafından engellendi.")
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
                    f"🚨 <b>HEPSİBURADA'YA YENİ STOK DÜŞTÜ!</b>\n\n"
                    f"📦 Ürün Sayısı: <b>{guncel_sayi}</b>\n"
                    f"🔗 <a href='{URL}'>Hepsiburada Sayfasını Aç</a>"
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
