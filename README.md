# Fiyat Takip Botu

8 siteyi (vatan, itopya, incehesap, n11, hepsiburada, gaming.gen.tr, trendyol, amazon) tarayip ayni urunun en ucuz fiyatini buluyor, fiyat dusunce telegramdan haber veriyor.

## Nasil calisiyor

- sitelerde arama yapiyor (birden fazla sayfa, en ucuz urun genelde ilk sayfada olmuyor)
- sonuclari ada gore filtreliyor
- en ucuzdan baslayip urun sayfasini acarak dogruluyor
- fiyat gecmisini sqlite'a yaziyor
- dusus olursa telegrama mesaj atiyor

Hepsiburada, n11 ve incehesap normal requests'e 403 veriyor, onlar icin curl_cffi kullandim. Trendyol ve amazon icin playwright gerekiyor.

## Kurulum

```
cd backend
pip install -r requirements.txt
python -m playwright install chromium
```

`.env.example`'i `.env` olarak kopyalayip telegram bot token'ini ve chat id'ni yaz.

```
python run.py
```

## Telegram komutlari

`/yardim` yazinca hepsi listeleniyor. Kategori adini yazinca (ram, ekran karti, telefon...) filtre menusu aciliyor, `/ara ddr5 32gb -notebook` ile de direkt aranabiliyor.
