import os
import re
import sys
import subprocess

try:
    from curl_cffi import requests
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "curl_cffi"])
    from curl_cffi import requests

URL = "https://www.hepsiburada.com/laptop-notebook-dizustu-bilgisayarlar-c-98?filtreler=ekrankarti:Nvidia%E2%82%AC20GeForce%E2%82%AC20RTX%E2%82%AC205060,Nvidia%E2%82%AC20GeForce%E2%82%AC20RTX%E2%82%AC205070;satici:Hepsiburada"

# Mevcut ürün sayısı eşiği
ESIK_URUN_SAYISI = 22

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

def urun_basliklarini_ayikla(html):
    """
    Filtre menüsünü hariç tutarak yalnızca gerçek ürün başlıklarını toplar.
    """
    basliklar = []
    
    # 1. Hepsiburada ürün kartı başlık etiketleri
    bulunanlar = re.findall(r'<h3[^>]*data-test-id="product-card-name"[^>]*>(.*?)</h3>', html, re.IGNORECASE | re.DOTALL)
    if not bulunanlar:
        bulunanlar = re.findall(r'<h3[^>]*class="[^"]*product-name[^"]*"[^>]*>(.*?)</h3>', html, re.IGNORECASE | re.DOTALL)
    basliklar.extend(bulunanlar)

    # 2. Sayfa içi JSON ürün isimleri
    json_isimler = re.findall(r'"name":\s*"([^"]*(?:laptop|bilgisayar|notebook|omen)[^"]*)"', html, re.IGNORECASE)
    basliklar.extend(json_isimler)

    # HTML artıklarını temizle
    temiz_liste = []
    for b in basliklar:
        temiz = re.sub(r'<[^>]+>', '', b).strip()
        if temiz and len(temiz) > 5:
            temiz_liste.append(temiz)
            
    return list(set(temiz_liste))

def kontrol_et():
    try:
        response = requests.get(URL, impersonate="chrome", timeout=25)
        print(f"Hepsiburada yanıt kodu: {response.status_code}")

        if response.status_code != 200:
            print("Sayfa güvenlik duvarı tarafından engellendi.")
            return

        html = response.text
        
        # Sayfadaki güncel ürün sayısını bul
        eslesme = re.search(r'\((\d+)\s*ürün\)', html, re.IGNORECASE)
        if not eslesme:
            eslesme = re.search(r'"totalProductCount":\s*(\d+)', html)
        if not eslesme:
            eslesme = re.search(r'(\d+)\s*ürün', html, re.IGNORECASE)

        guncel_sayi = int(eslesme.group(1)) if eslesme else None
        if guncel_sayi is not None:
            print(f"Tespit Edilen Ürün: {guncel_sayi} | Eşik: {ESIK_URUN_SAYISI}")

        # Başlıklarda Omen ara
        urunler = urun_basliklarini_ayikla(html)
        bulunan_omenler = [u for u in urunler if "omen" in u.lower()]

        # 1. ÖNCELİK: Başlıkta doğrudan Omen tespit edilirse
        if bulunan_omenler:
            print(f"OMEN YAKALANDI: {bulunan_omenler[0]}")
            mesaj = (
                f"🎯 <b>HP OMEN SATIŞA ÇIKTI!</b>\n\n"
                f"💻 <b>Model:</b> {bulunan_omenler[0]}\n"
                f"📦 Toplam Ürün: <b>{guncel_sayi or 22}</b>\n\n"
                f"🔗 <a href='{URL}'>Hemen Satın Al / İncele</a>"
            )
            telegram_bildirim_gonder(mesaj)
            
        # 2. ÖNCELİK: Omen ismi bulunamasa bile toplam stok arttıysa (23 ve üzeri)
        elif guncel_sayi and guncel_sayi > ESIK_URUN_SAYISI:
            print(f"Yeni ürün eklendi ({guncel_sayi} > {ESIK_URUN_SAYISI})")
            mesaj = (
                f"🚨 <b>HEPSİBURADA'YA YENİ LAPTOP GİRDİ!</b>\n\n"
                f"📦 Ürün Sayısı: <b>{guncel_sayi}</b> (Önceki: {ESIK_URUN_SAYISI})\n"
                f"ℹ️ Yeni bir model stoğa girdi, kontrol etmenizde fayda var.\n\n"
                f"🔗 <a href='{URL}'>Hepsiburada Sayfasını Aç</a>"
            )
            telegram_bildirim_gonder(mesaj)
        else:
            print("Ne Omen ne de yeni stok artışı var. Nöbet sessizce devam ediyor.")

    except Exception as e:
        print(f"Bağlantı hatası: {e}")

if __name__ == "__main__":
    kontrol_et()
