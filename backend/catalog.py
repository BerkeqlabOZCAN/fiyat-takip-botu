
from __future__ import annotations


from dataclasses import dataclass


@dataclass
class Option:
    k: str                          # anahtar
    l: str                          # etiket (butonda gorunur)
    req: tuple = ()                 # zorunlu kelımeler
    any: tuple = ()                 # en az biri gecmeli
    exc: tuple = ()                 # gecerse elenir
    site: str = ""                  # site aramasina eklenecek terim
    # urun sayfasinda gecerse elenecek ifadeler
    page_exc: tuple = ()


@dataclass
class Group:
    k: str
    l: str
    options: list
    multi: bool = True              # birden fazla secilebilir mi

@dataclass
class Category:
    k: str
    l: str
    base: str                       # site aramasinin govdesi ("ram")
    aliases: tuple                  # kullanicinin yazabilecegi kelimeler
    groups: list
    primary: str = ""               # site aramasina eklenecek grup (ram -> tur)


    # kategori korumasi her zaman uygulanir
    guard_any: tuple = ()           # bunlardan en az biri urun adinda gecmeli
    guard_exc: tuple = ()           # bunlardan biri gecerse urun elenir


    # alt fiyat siniri aksesuarlar en ucuz diye one cikmasin
    min_price: float = 0.0


def _opts(pairs) -> list:
    return [Option(k=k, l=l, req=(k,)) for k, l in pairs]

# RAM
RAM = Category(
    k="ram", l="RAM (Bellek)", base="ram",
    aliases=("ram", "bellek", "memory", "pc ram", "ddr"),
    primary="tur",
    # kok olarak belle yeterli
    guard_any=("ram", "belle", "memory", "dimm"),
    guard_exc=("anakart", "motherboard", "hazir sistem", "barebone",
               "ekran karti", "islemci", "sogutucu"),
    groups=[
        Group("tur", "Bellek Türü", [
            Option("ddr5", "DDR5", req=("ddr5",), site="ddr5"),
            Option("ddr4", "DDR4", req=("ddr4",), site="ddr4"),
            Option("ddr3", "DDR3", req=("ddr3",), site="ddr3"),
        ], multi=False),


        Group("kullanim", "Kullanım Tipi", [
            # saticilar dizustu ram'ini cok farkli yaziyor
            Option("masaustu", "Masaüstü (DIMM)",
                   exc=("notebook", "sodimm", "so dimm", "laptop",
                        "n book", "nbook", "dizustu"),
                   # amazon menusunde de geciyor
                   page_exc=("sodimm", "so dimm", "262 pin",
                             "pin sayisi 262", "uyumlu platform notebook",
                             "uyumlu sistemler notebook")),
            Option("notebook", "Notebook (SODIMM)",
                   any=("notebook", "sodimm", "so dimm", "laptop",
                        "n book", "nbook", "dizustu"),
                   page_exc=("udimm", "288 pin", "pin sayisi 288",
                             "uyumlu platform masaustu")),
        ], multi=False),
        Group("kapasite", "Kapasite", _opts([
            ("8gb", "8 GB"), ("16gb", "16 GB"), ("32gb", "32 GB"),
            ("48gb", "48 GB"), ("64gb", "64 GB"), ("96gb", "96 GB"),
            ("128gb", "128 GB"),
        ])),
        Group("kit", "Modül Yapısı", [
            # urun adlari "32GB (2x16GB)" seklinde yazıliyor
            Option("dual", "Dual kit (2x)", any=("2x", "dual kit", "dual")),
            Option("tek", "Tek modül (1x)", exc=("2x", "4x", "dual kit")),
        ], multi=False),

        Group("hiz", "Hız (MHz)", _opts([
            ("3200", "3200"), ("3600", "3600"), ("4800", "4800"),
            ("5200", "5200"), ("5600", "5600"), ("6000", "6000"),
            ("6400", "6400"), ("7200", "7200"), ("8000", "8000"),
        ])),

        Group("cl", "Gecikme (CL)", _opts([
            ("cl30", "CL30"), ("cl32", "CL32"), ("cl36", "CL36"),
            ("cl38", "CL38"), ("cl40", "CL40"), ("cl46", "CL46"),
        ])),
        Group("marka", "Marka", [
            Option("corsair", "Corsair", req=("corsair",)),
            Option("gskill", "G.Skill", req=("gskill",)),
            Option("kingston", "Kingston", any=("kingston", "fury")),
            Option("crucial", "Crucial", req=("crucial",)),
            Option("teamgroup", "TeamGroup", any=("teamgroup", "t force")),
            Option("xpg", "XPG / ADATA", any=("xpg", "adata")),
            Option("patriot", "Patriot", req=("patriot",)),
            Option("lexar", "Lexar", req=("lexar",)),
            Option("apacer", "Apacer", req=("apacer",)),
            Option("twinmos", "TwinMOS", req=("twinmos",)),
            Option("goodram", "GOODRAM", req=("goodram",)),
            Option("transcend", "Transcend", req=("transcend",)),
        ]),

        Group("ozellik", "Özellik", [
            Option("rgb", "RGB", req=("rgb",)),
            Option("nonrgb", "RGB'siz", exc=("rgb",)),
            Option("sogutuculu", "Soğutuculu", any=("sogutuculu", "heatsink")),
            Option("beyaz", "Beyaz", req=("beyaz",)),
            Option("siyah", "Siyah", req=("siyah",)),
        ]),
    ],
)


# dıger kategoriler

GPU = Category(
    k="gpu", l="Ekran Kartı", base="ekran karti",
    aliases=("ekran karti", "ekran kartı", "gpu", "vga", "grafik karti"),
    primary="seri",
    guard_any=("ekran karti", "geforce", "radeon", "graphics", "arc"),
    guard_exc=("anakart", "hazir sistem", "laptop", "notebook",
               "monitor", "riser", "yukseltici"),
    groups=[
        Group("seri", "Seri", [
            Option("rtx5090", "RTX 5090", req=("5090",), site="rtx 5090"),
            Option("rtx5080", "RTX 5080", req=("5080",), site="rtx 5080"),
            Option("rtx5070", "RTX 5070", req=("5070",), site="rtx 5070"),
            Option("rtx5060", "RTX 5060", req=("5060",), site="rtx 5060"),
            Option("rtx4060", "RTX 4060", req=("4060",), site="rtx 4060"),
            Option("rx9070", "RX 9070", req=("9070",), site="rx 9070"),
            Option("rx7800", "RX 7800", req=("7800",), site="rx 7800"),
        ], multi=False),
        Group("vram", "Bellek", _opts([
            ("8gb", "8 GB"), ("12gb", "12 GB"), ("16gb", "16 GB"),
            ("24gb", "24 GB"), ("32gb", "32 GB"),
        ])),
        Group("marka", "Marka", [
            Option("asus", "ASUS", req=("asus",)),
            Option("msi", "MSI", req=("msi",)),
            Option("gigabyte", "Gigabyte", req=("gigabyte",)),
            Option("zotac", "Zotac", req=("zotac",)),
            Option("palit", "Palit", req=("palit",)),
            Option("gainward", "Gainward", req=("gainward",)),
            Option("inno3d", "Inno3D", req=("inno3d",)),
            Option("sapphire", "Sapphire", req=("sapphire",)),
        ]),
        Group("ozellik", "Özellik", [
            Option("oc", "OC", req=("oc",)),
            Option("ti", "Ti", req=("ti",)),
            Option("super", "Super", req=("super",)),
        ]),
    ],
)


CPU = Category(
    k="cpu", l="İşlemci", base="islemci",
    aliases=("islemci", "işlemci", "cpu", "prosesor"),
    primary="aile",
    guard_any=("islemci", "processor", "ryzen", "core i", "xeon"),
    guard_exc=("anakart", "hazir sistem", "laptop", "ekran karti",
               "sogutucu", "termal", "macun"),
    groups=[
        Group("aile", "Aile", [
            Option("ryzen9", "Ryzen 9", any=("ryzen 9",), site="ryzen 9"),
            Option("ryzen7", "Ryzen 7", any=("ryzen 7",), site="ryzen 7"),
            Option("ryzen5", "Ryzen 5", any=("ryzen 5",), site="ryzen 5"),
            Option("i9", "Core i9", any=("i9",), site="intel i9"),
            Option("i7", "Core i7", any=("i7",), site="intel i7"),
            Option("i5", "Core i5", any=("i5",), site="intel i5"),
        ], multi=False),
        Group("ozellik", "Özellik", [
            Option("x3d", "X3D", req=("x3d",)),
            Option("kutulu", "Kutulu (BOX)", any=("kutulu", "box")),
            Option("tray", "Tray", req=("tray",)),
            Option("nofan", "Fansız", exc=("fanli", "wraith")),
        ]),
    ],
)

SSD = Category(
    k="ssd", l="SSD", base="ssd",
    aliases=("ssd", "nvme", "m2", "m.2"),   # "disk" bilerek yok
    # harddisk ile karisiyordu
    primary="arayuz",
    guard_any=("ssd", "nvme"),
    guard_exc=("kutusu", "kizak", "adaptor", "dock", "hazir sistem",
               "laptop", "notebook", "sogutucu"),
    groups=[
        Group("arayuz", "Arayüz", [
            Option("nvme", "NVMe M.2", any=("nvme", "m 2"), site="nvme ssd"),
            Option("sata", "SATA 2.5\"", req=("sata",), site="sata ssd"),
        ], multi=False),
        Group("kapasite", "Kapasite", _opts([
            ("500gb", "500 GB"), ("1tb", "1 TB"), ("2tb", "2 TB"),
            ("4tb", "4 TB"), ("8tb", "8 TB"),
        ])),
        Group("nesil", "Nesil", _opts([
            ("gen3", "Gen3"), ("gen4", "Gen4"), ("gen5", "Gen5"),
        ])),
        Group("marka", "Marka", [
            Option("samsung", "Samsung", req=("samsung",)),
            Option("wd", "WD", any=("wd", "western digital")),
            Option("kingston", "Kingston", req=("kingston",)),
            Option("crucial", "Crucial", req=("crucial",)),
            Option("lexar", "Lexar", req=("lexar",)),
            Option("xpg", "XPG / ADATA", any=("xpg", "adata")),
        ]),
    ],
)

MONITOR = Category(
    k="monitor", l="Monitör", base="monitor",
    aliases=("monitor", "monitör", "ekran"),
    primary="boyut",
    guard_any=("monitor",),
    guard_exc=("stand", "ayak", "montaj", "koruyucu", "temizle",
               "kablo", "kol"),
    groups=[
        Group("boyut", "Boyut", [
            Option("24", "24\"", req=("24",), site="24 monitor"),
            Option("27", "27\"", req=("27",), site="27 monitor"),
            Option("32", "32\"", req=("32",), site="32 monitor"),
            Option("34", "34\" UW", req=("34",), site="34 monitor"),
        ], multi=False),
        Group("cozunurluk", "Çözünürlük", [
            Option("fhd", "Full HD", any=("1920", "fhd", "full hd")),
            Option("qhd", "QHD 2K", any=("2560", "qhd", "2k")),
            Option("uhd", "4K UHD", any=("3840", "4k", "uhd")),
        ]),
        Group("hz", "Yenileme", _opts([
            ("144hz", "144 Hz"), ("165hz", "165 Hz"),
            ("180hz", "180 Hz"), ("240hz", "240 Hz"),
        ])),
        Group("panel", "Panel", _opts([
            ("ips", "IPS"), ("va", "VA"), ("oled", "OLED"),
        ])),
    ],
)

# ek kategoriler


ANAKART = Category(
    k="anakart", l="Anakart", base="anakart",
    aliases=("anakart", "motherboard", "mainboard"),
    primary="soket",
    guard_any=("anakart", "motherboard", "mainboard"),
    guard_exc=("hazir sistem", "barebone", "ram", "ekran karti", "islemci",
               "sogutucu", "kasa"),
    groups=[
        Group("soket", "Soket", [
            Option("am5", "AMD AM5", req=("am5",), site="am5 anakart"),
            Option("am4", "AMD AM4", req=("am4",), site="am4 anakart"),
            Option("1700", "Intel 1700", req=("1700",), site="1700 anakart"),
            Option("1851", "Intel 1851", req=("1851",), site="1851 anakart"),
            Option("1200", "Intel 1200", req=("1200",), site="1200 anakart"),
        ], multi=False),
        Group("yonga", "Yonga Seti", _opts([
            ("b650", "B650"), ("x670", "X670"), ("b850", "B850"), ("x870", "X870"),
            ("a620", "A620"), ("b760", "B760"), ("z790", "Z790"),
            ("b860", "B860"), ("z890", "Z890"),
        ])),
        Group("boyut", "Form Faktör", [
            Option("atx", "ATX", req=("atx",), exc=("matx", "m atx", "mini itx")),
            Option("matx", "mATX", any=("matx", "m atx", "micro atx")),
            Option("itx", "Mini-ITX", any=("itx", "mini itx")),
        ], multi=False),
        Group("bellek", "Bellek", [
            Option("ddr5", "DDR5", req=("ddr5",)),
            Option("ddr4", "DDR4", req=("ddr4",)),
        ], multi=False),
        Group("marka", "Marka", [
            Option("asus", "ASUS", req=("asus",)),
            Option("msi", "MSI", req=("msi",)),
            Option("gigabyte", "Gigabyte", req=("gigabyte",)),
            Option("asrock", "ASRock", req=("asrock",)),
        ]),
    ],
)

PSU = Category(
    k="psu", l="Güç Kaynağı", base="power supply",
    aliases=("guc kaynagi", "güç kaynağı", "psu", "power supply", "besleme"),
    primary="guc",
    guard_any=("guc kaynagi", "power supply", "psu", "besleme"),
    guard_exc=("kesintisiz", "ups", "adaptor", "laptop", "notebook",
               "hazir sistem", "kablo"),
    groups=[
        Group("guc", "Güç", [
            Option("500w", "500W", req=("500w",), site="500w power supply"),
            Option("650w", "650W", req=("650w",), site="650w power supply"),
            Option("750w", "750W", req=("750w",), site="750w power supply"),
            Option("850w", "850W", req=("850w",), site="850w power supply"),
            Option("1000w", "1000W", req=("1000w",), site="1000w power supply"),
            Option("1200w", "1200W", req=("1200w",), site="1200w power supply"),
        ], multi=False),
        Group("sertifika", "Sertifika", [
            Option("bronze", "80+ Bronze", req=("bronze",)),
            Option("gold", "80+ Gold", req=("gold",)),
            Option("platinum", "80+ Platinum", req=("platinum",)),
            Option("titanium", "80+ Titanium", req=("titanium",)),
        ]),
        Group("modul", "Modülerlik", [
            Option("fullmodular", "Tam modüler", any=("full modular", "tam moduler")),
            Option("semimodular", "Yarı modüler", any=("semi modular", "yari moduler")),
        ], multi=False),
        Group("marka", "Marka", [
            Option("corsair", "Corsair", req=("corsair",)),
            Option("seasonic", "Seasonic", req=("seasonic",)),
            Option("thermaltake", "Thermaltake", req=("thermaltake",)),
            Option("cooler", "Cooler Master", any=("cooler master", "coolermaster")),
            Option("gamepower", "GamePower", any=("gamepower", "game power")),
            Option("asus", "ASUS", req=("asus",)),
        ]),
    ],
)

KASA = Category(
    k="kasa", l="Bilgisayar Kasası", base="bilgisayar kasasi",
    aliases=("kasa", "case", "bilgisayar kasasi", "kasası"),
    primary="boyut",
    guard_any=("kasa", "case"),
    guard_exc=("hazir sistem", "klavye", "telefon kilifi", "kilif", "canta",
               "ssd kutusu", "harici"),
    groups=[
        Group("boyut", "Boyut", [
            Option("miditower", "Mid Tower", any=("mid tower", "midi tower")),
            Option("fulltower", "Full Tower", any=("full tower",)),
            Option("matx", "mATX", any=("matx", "micro atx")),
            Option("itx", "Mini-ITX", any=("itx", "mini itx")),
        ], multi=False),
        Group("ozellik", "Özellik", [
            Option("cam", "Temperli cam", any=("temperli cam", "tempered glass")),
            Option("mesh", "Mesh panel", req=("mesh",)),
            Option("rgb", "RGB fanlı", req=("rgb",)),
            Option("beyaz", "Beyaz", req=("beyaz",)),
            Option("siyah", "Siyah", req=("siyah",)),
        ]),
        Group("marka", "Marka", [
            Option("nzxt", "NZXT", req=("nzxt",)),
            Option("lianli", "Lian Li", any=("lian li", "lianli")),
            Option("corsair", "Corsair", req=("corsair",)),
            Option("bitfenix", "BitFenix", req=("bitfenix",)),
            Option("zalman", "Zalman", req=("zalman",)),
            Option("gamepower", "GamePower", any=("gamepower", "game power")),
        ]),
    ],
)

SOGUTUCU = Category(
    k="sogutucu", l="İşlemci Soğutucu", base="islemci sogutucu",
    aliases=("sogutucu", "soğutucu", "cpu sogutucu", "islemci sogutucu",
             "cooler", "fanli sogutucu"),
    primary="tip",
    guard_any=("sogutucu", "cooler", "aio"),
    guard_exc=("hazir sistem", "termal macun", "macun", "ram", "ssd",
               "ekran karti", "kasa fani"),
    groups=[
        Group("tip", "Tip", [
            Option("hava", "Hava soğutmalı",
                   any=("hava", "air"), exc=("sivi", "aio", "likit")),
            Option("sivi", "Sıvı (AIO)", any=("sivi", "aio", "likit", "liquid")),
        ], multi=False),
        Group("radyator", "Radyatör", _opts([
            ("120", "120 mm"), ("240", "240 mm"), ("280", "280 mm"),
            ("360", "360 mm"), ("420", "420 mm"),
        ])),
        Group("soket", "Soket", _opts([
            ("am5", "AM5"), ("am4", "AM4"), ("1700", "Intel 1700"),
            ("1851", "Intel 1851"),
        ])),
        Group("marka", "Marka", [
            Option("noctua", "Noctua", req=("noctua",)),
            Option("deepcool", "DeepCool", req=("deepcool",)),
            Option("arctic", "Arctic", req=("arctic",)),
            Option("nzxt", "NZXT", req=("nzxt",)),
            Option("corsair", "Corsair", req=("corsair",)),
            Option("thermalright", "Thermalright", req=("thermalright",)),
        ]),
    ],
)

KLAVYE = Category(
    k="klavye", l="Klavye", base="klavye",
    aliases=("klavye", "keyboard"),
    primary="tip",
    guard_any=("klavye", "keyboard"),
    guard_exc=("mouse", "fare", "kilif", "stand", "temizleyici", "kapak",
               "tablet", "laptop", "notebook",
               # yedek switch ve tus setleri
               "yedek tus", "yedek switch", "keycap", "tus seti",
               "switch seti", "switch kiti", "tus takimi",
               "makropad", "macro pad", "makro pad",
               # membran klavyeler
               "mekanik hisli", "mekanik his", "hisli membran"),
    groups=[
        Group("tip", "Tip", [
            Option("mekanik", "Mekanik", req=("mekanik",), site="mekanik klavye"),
            Option("membran", "Membran", any=("membran", "membrane")),
            Option("optik", "Optik", req=("optik",)),
        ], multi=False),
        Group("boyut", "Boyut", [
            Option("full", "Full boyut", any=("full size", "tam boyut", "104")),
            Option("tkl", "TKL (%80)", any=("tkl", "tenkeyless", "87")),
            Option("75", "%75", req=("75",)),
            Option("65", "%65", req=("65",)),
            Option("60", "%60", req=("60",)),
        ], multi=False),
        Group("switch", "Switch", [
            Option("mavi", "Mavi (tıklamalı)", any=("mavi", "blue")),
            Option("kirmizi", "Kırmızı (lineer)", any=("kirmizi", "red")),
            Option("kahve", "Kahverengi (taktil)", any=("kahve", "brown")),
        ]),
        Group("baglanti", "Bağlantı", [
            Option("kablosuz", "Kablosuz", any=("kablosuz", "wireless", "bluetooth")),
            Option("kablolu", "Kablolu", exc=("kablosuz", "wireless", "bluetooth")),
        ], multi=False),
        Group("marka", "Marka", [
            Option("logitech", "Logitech", req=("logitech",)),
            Option("razer", "Razer", req=("razer",)),
            Option("steelseries", "SteelSeries", req=("steelseries",)),
            Option("keychron", "Keychron", req=("keychron",)),
            Option("corsair", "Corsair", req=("corsair",)),
            Option("hyperx", "HyperX", req=("hyperx",)),
        ]),
    ],
)

MOUSE = Category(
    k="mouse", l="Mouse", base="mouse",
    aliases=("mouse", "fare", "oyuncu mouse"),
    primary="baglanti",
    guard_any=("mouse", "fare"),
    guard_exc=("mousepad", "pad", "klavye", "kilif", "stand", "temizleyici"),
    groups=[
        Group("baglanti", "Bağlantı", [
            Option("kablosuz", "Kablosuz", any=("kablosuz", "wireless"),
                   site="kablosuz mouse"),
            Option("kablolu", "Kablolu", exc=("kablosuz", "wireless"),
                   site="kablolu mouse"),
        ], multi=False),
        Group("ozellik", "Özellik", [
            Option("hafif", "Hafif", any=("hafif", "lightweight")),
            Option("rgb", "RGB", req=("rgb",)),
            Option("beyaz", "Beyaz", req=("beyaz",)),
            Option("siyah", "Siyah", req=("siyah",)),
        ]),
        Group("marka", "Marka", [
            Option("logitech", "Logitech", req=("logitech",)),
            Option("razer", "Razer", req=("razer",)),
            Option("steelseries", "SteelSeries", req=("steelseries",)),
            Option("pulsar", "Pulsar", req=("pulsar",)),
            Option("glorious", "Glorious", req=("glorious",)),
            Option("hyperx", "HyperX", req=("hyperx",)),
        ]),
    ],
)
KULAKLIK = Category(
    k="kulaklik", l="Kulaklık", base="kulaklik",
    aliases=("kulaklik", "kulaklık", "headset", "headphone"),
    primary="tip",
    guard_any=("kulaklik", "headset", "headphone", "kulak"),
    guard_exc=("stand", "kilif", "kablo", "adaptor", "yedek", "kulak pedi"),
    groups=[
        Group("tip", "Tip", [
            Option("ustu", "Kulak üstü", any=("kulak ustu", "over ear", "on ear"),
                   site="kulak ustu kulaklik"),
            Option("ici", "Kulak içi", any=("kulak ici", "in ear", "tws"),
                   site="kulak ici kulaklik"),
        ], multi=False),
        Group("baglanti", "Bağlantı", [
            Option("kablosuz", "Kablosuz", any=("kablosuz", "wireless", "bluetooth")),
            Option("kablolu", "Kablolu", exc=("kablosuz", "wireless", "bluetooth")),
        ], multi=False),
        Group("ozellik", "Özellik", [
            Option("anc", "Gürültü engelleme", any=("anc", "gurultu engelleme",
                                                    "noise cancel")),
            Option("mikrofon", "Mikrofonlu", any=("mikrofon", "mic")),
        ]),
        Group("marka", "Marka", [
            Option("sony", "Sony", req=("sony",)),
            Option("logitech", "Logitech", req=("logitech",)),
            Option("razer", "Razer", req=("razer",)),
            Option("hyperx", "HyperX", req=("hyperx",)),
            Option("steelseries", "SteelSeries", req=("steelseries",)),
            Option("jbl", "JBL", req=("jbl",)),
        ]),
    ],
)

LAPTOP = Category(
    k="laptop", l="Dizüstü Bilgisayar", base="laptop",
    aliases=("laptop", "dizustu", "dizüstü", "notebook", "dizustu bilgisayar"),
    min_price=8000,
    # marka secilince sitelerde de aransin
    primary="marka",
    # sadece laptop serileri
    guard_any=("laptop", "notebook", "dizustu", "macbook", "thinkpad",
               "ideapad", "vivobook", "zenbook", "chromebook", "matebook",
               "galaxy_book", "victus", "pavilion", "probook", "elitebook",
               "aspire", "swift", "inspiron", "latitude", "katana",
               "cyborg", "abra", "tulpar", "excalibur", "nirvana"),
    # aksesuarlar
    guard_exc=("kilif", "canta", "stand", "sogutucu", "adaptor", "sarj",
               "sodimm", "klavye", "batarya", "ekran karti",
               # monitorler
               "monitor", "adaptive_sync", "freesync", "g_sync", "curved",
               "hdmi_dp", "ips_panel",
               "uyumlu", "lcd ekran", "dokunmatik ekran", "arka kapak",
               "sleeve", "koruyucu", "yedek ekran", "tetik", "aparat",
               # kitaplar
               "guide", "kitap", "manual", "rehber", "el kitabi"),
    groups=[
        Group("durum", "Ürün Durumu", [
            Option("sifir", "Sıfır",
                   exc=("yenilenmis", "refurbished", "ikinci el", "outlet",
                        "teshir", "kutusu acik")),
            Option("yenilenmis", "Yenilenmiş",
                   any=("yenilenmis", "refurbished")),
        ], multi=False),
        Group("ekran", "Ekran", [
            Option("14", "14\"", req=("14",), site="14 inc laptop"),
            Option("15", "15.6\"", req=("15",), site="15 inc laptop"),
            Option("16", "16\"", req=("16",), site="16 inc laptop"),
            Option("17", "17\"", req=("17",), site="17 inc laptop"),
        ], multi=False),
        Group("islemci", "İşlemci", [
            Option("ryzen7", "Ryzen 7", any=("ryzen 7",)),
            Option("ryzen5", "Ryzen 5", any=("ryzen 5",)),
            Option("i7", "Core i7", any=("i7",)),
            Option("i5", "Core i5", any=("i5",)),
        ]),
        Group("ram", "RAM", _opts([
            ("8gb", "8 GB"), ("16gb", "16 GB"), ("32gb", "32 GB"),
        ])),
        Group("gpu", "Ekran Kartı", _opts([
            ("rtx4050", "RTX 4050"), ("rtx4060", "RTX 4060"),
            ("rtx5060", "RTX 5060"), ("rtx5070", "RTX 5070"),
        ])),
        # razer yok cunku erazer ile karisiyor
        Group("marka", "Marka", [
            Option("asus", "ASUS", any=("asus", "vivobook", "zenbook"),
                   site="asus laptop"),
            Option("lenovo", "Lenovo", any=("lenovo", "thinkpad", "ideapad",
                                            "legion"), site="lenovo laptop"),
            Option("hp", "HP", any=("hp", "victus", "omen", "pavilion",
                                    "probook", "elitebook"), site="hp laptop"),
            Option("msi", "MSI", any=("msi", "katana", "cyborg"),
                   site="msi laptop"),
            Option("monster", "Monster", any=("monster", "abra", "tulpar"),
                   site="monster laptop"),
            Option("casper", "Casper", any=("casper", "excalibur", "nirvana"),
                   site="casper laptop"),
            Option("apple", "Apple MacBook", any=("macbook",), site="macbook"),
            Option("acer", "Acer", any=("acer", "aspire", "nitro", "predator",
                                        "swift"), site="acer laptop"),
            Option("dell", "Dell", any=("dell", "inspiron", "latitude",
                                        "alienware"), site="dell laptop"),
            Option("gigabyte", "Gigabyte", any=("gigabyte", "aorus"),
                   site="gigabyte laptop"),
            Option("huawei", "Huawei", any=("huawei", "matebook"),
                   site="huawei matebook"),
        ], multi=False),
    ],
)

HDD = Category(
    k="hdd", l="Harddisk", base="harddisk",
    aliases=("hdd", "harddisk", "hard disk", "sabit disk"),
    primary="kapasite",
    guard_any=("hdd", "harddisk", "hard disk", "sabit disk"),
    guard_exc=("ssd", "nvme", "kutusu", "kizak", "kablo", "harici kutu"),
    groups=[
        Group("kapasite", "Kapasite", [
            Option("1tb", "1 TB", req=("1tb",), site="1tb harddisk"),
            Option("2tb", "2 TB", req=("2tb",), site="2tb harddisk"),
            Option("4tb", "4 TB", req=("4tb",), site="4tb harddisk"),
            Option("8tb", "8 TB", req=("8tb",), site="8tb harddisk"),
        ], multi=False),
        Group("tip", "Tip", [
            Option("35", "3.5\" (masaüstü)", any=("3 5", "35 inc"),
                   exc=("2 5", "harici", "tasinabilir")),
            Option("harici", "Harici", any=("harici", "tasinabilir", "portable")),
        ], multi=False),
        Group("marka", "Marka", [
            Option("seagate", "Seagate", req=("seagate",)),
            Option("wd", "WD", any=("wd", "western digital")),
            Option("toshiba", "Toshiba", req=("toshiba",)),
        ]),
    ],
)

TELEFON = Category(
    k="telefon", l="Cep Telefonu", base="cep telefonu",
    aliases=("telefon", "cep telefonu", "akilli telefon", "smartphone",
             "iphone", "samsung", "xiaomi", "redmi", "galaxy"),
    # tuslu telefonlar 1500 cıvarinda
    min_price=1500,
    primary="marka",
    guard_any=("telefon", "phone", "iphone", "galaxy", "redmi", "xiaomi",
               "poco", "huawei", "honor", "oppo", "realme", "vivo", "tecno",
               "infinix", "nokia", "reeder", "general mobile", "tcl",
               "alcatel", "motorola", "zte", "nubia", "omix"),
    # aksesuarlar
    guard_exc=("kilif", "kilifi", "cam", "ekran koruyucu", "sarj", "kablo",
               "stand", "tutucu", "batarya", "yedek parca", "kulaklik",
               "uyumlu", "lcd ekran", "dokunmatik ekran", "arka kapak",
               "sleeve", "koruyucu", "yedek ekran", "tetik", "aparat",
               # onarim kasalarini ele
               "dolu kasa", "bos kasa", "kasa",
               # kitaplar
               "guide", "kitap", "manual", "rehber", "el kitabi",
               # ayni markanin telefon olmayan urunleri
               "tablet", "matepad", "watch", "band", "buds", "notebook",
               "laptop", "vivobook", "zenbook", "chromebook",
               # marka aramasinda cikan alakasiz seyler
               "dect", "telsiz", "citali", "ekran dokunmatik",
               "saati", "akilli saat"),
    groups=[
        Group("durum", "Ürün Durumu", [
            Option("sifir", "Sıfır",
                   exc=("yenilenmis", "refurbished", "ikinci el", "outlet",
                        "teshir", "kutusu acik")),
            Option("yenilenmis", "Yenilenmiş",
                   any=("yenilenmis", "refurbished")),
        ], multi=False),
        Group("marka", "Marka", [
            Option("iphone", "iPhone", req=("iphone",), site="iphone"),
            Option("samsung", "Samsung", any=("samsung", "galaxy"), site="samsung"),
            # poco ve redmi ayri kimse xiaomi diye aramiyor
            Option("xiaomi", "Xiaomi", any=("xiaomi",), site="xiaomi"),
            Option("redmi", "Redmi", any=("redmi",), site="redmi"),
            Option("poco", "POCO", any=("poco",), site="poco"),
            Option("huawei", "Huawei", any=("huawei",), site="huawei"),
            Option("honor", "Honor", any=("honor",), site="honor"),
            Option("oppo", "Oppo", any=("oppo",), site="oppo"),
            Option("realme", "Realme", any=("realme",), site="realme"),
            # vivobook ile karisiyor
            Option("vivo", "Vivo", any=("vivo",),
                   exc=("vivobook",), site="vivo"),
            Option("tecno", "Tecno", any=("tecno",), site="tecno"),
            Option("infinix", "Infinix", any=("infinix",), site="infinix"),
            Option("nokia", "Nokia", any=("nokia",), site="nokia"),
            Option("reeder", "Reeder", any=("reeder",), site="reeder"),
            Option("gm", "General Mobile", any=("general_mobile",),
                   site="general mobile"),
            Option("tcl", "TCL", any=("tcl",), site="tcl"),
            Option("alcatel", "Alcatel", any=("alcatel",), site="alcatel"),
            Option("motorola", "Motorola", any=("motorola",), site="motorola"),
            Option("zte", "ZTE", any=("zte", "nubia"), site="zte"),
            Option("omix", "Omix", any=("omix",), site="omix"),
        ], multi=False),
        Group("depolama", "Depolama", _opts([
            ("128gb", "128 GB"), ("256gb", "256 GB"), ("512gb", "512 GB"),
        ])),
        Group("ram", "RAM", _opts([
            ("8gb", "8 GB"), ("12gb", "12 GB"), ("16gb", "16 GB"),
        ])),
    ],
)


TABLET = Category(
    k="tablet", l="Tablet", base="tablet",
    aliases=("tablet", "ipad", "tablet bilgisayar"),
    min_price=2500,
    primary="marka",
    # adinda tablet gecmeyen seriler
    guard_any=("tablet", "ipad", "galaxy_tab", "honor_pad", "matepad",
               "xiaomi_pad", "redmi_pad", "poco_pad", "idea_tab",
               "lenovo_tab", "blackview_tab", "tcl_tab", "casper_pad",
               "surface", "hometech", "vorcom"),
    # aksesuarlar
    guard_exc=("kilif", "kilifi", "kalem", "ekran koruyucu", "cam",
               "stand", "tutucu", "canta", "sarj", "kablo", "adaptor",
               "klavyeli kilif", "yedek parca", "dokunmatik",
               "uyumlu", "lcd ekran", "dokunmatik ekran", "arka kapak",
               "sleeve", "koruyucu", "yedek ekran", "tetik", "aparat",
               # ipad icin seklindeki aksesuarlar
               "icin", "folio", "yuva", "tutacak",
               # kitaplar
               "guide", "kitap", "manual", "rehber", "el kitabi"),
    groups=[
        Group("durum", "Ürün Durumu", [
            Option("sifir", "Sıfır",
                   exc=("yenilenmis", "refurbished", "ikinci el", "outlet",
                        "teshir", "kutusu acik")),
            Option("yenilenmis", "Yenilenmiş",
                   any=("yenilenmis", "refurbished")),
        ], multi=False),
        Group("marka", "Marka", [
            Option("ipad", "Apple iPad", any=("ipad",), site="ipad"),
            Option("samsung", "Samsung", any=("samsung", "galaxy tab"),
                   site="samsung tablet"),
            Option("xiaomi", "Xiaomi", any=("xiaomi", "redmi pad", "poco pad"),
                   site="xiaomi tablet"),
            Option("lenovo", "Lenovo", req=("lenovo",), site="lenovo tablet"),
            # asus yok asus tablet aramasi klavye getiriyor
            Option("redmi", "Redmi", any=("redmi",), site="redmi pad"),
            Option("honor", "Honor", any=("honor",), site="honor pad"),
            Option("huawei", "Huawei", any=("huawei", "matepad"),
                   site="huawei matepad"),
            Option("casper", "Casper", any=("casper",), site="casper tablet"),
            Option("blackview", "Blackview", any=("blackview",),
                   site="blackview tablet"),
            Option("tcl", "TCL", any=("tcl",), site="tcl tablet"),
            Option("hometech", "Hometech", any=("hometech",),
                   site="hometech tablet"),
            Option("vorcom", "Vorcom", any=("vorcom",), site="vorcom tablet"),
        ], multi=False),
        Group("ekran", "Ekran", _opts([
            ("8", "8\""), ("10", "10\""), ("11", "11\""), ("13", "13\""),
        ])),
        Group("depolama", "Depolama", _opts([
            ("64gb", "64 GB"), ("128gb", "128 GB"), ("256gb", "256 GB"),
            ("512gb", "512 GB"),
        ])),
        Group("baglanti", "Bağlantı", [
            Option("wifi", "Sadece Wi-Fi", exc=("cellular", "lte", "5g", "sim")),
            Option("cellular", "Cellular / SIM", any=("cellular", "lte", "5g", "sim")),
        ], multi=False),
    ],
)

CATEGORIES = {c.k: c for c in (RAM, GPU, CPU, ANAKART, SOGUTUCU, PSU, KASA,
                                SSD, HDD, MONITOR, KLAVYE, MOUSE, KULAKLIK,
                                LAPTOP, TABLET, TELEFON)}

# cozumleme

def resolve(text: str):
    from match import normalize
    t = normalize(text)
    if not t:
        return None
    for cat in CATEGORIES.values():
        for a in cat.aliases:
            na = normalize(a)
            if t == na or na in t.split() or (len(na) > 3 and na in t):
                return cat
    return None



def groups_meta(cat: Category) -> list:
    return [{"k": g.k, "l": g.l, "n": len(g.options), "m": int(g.multi)}
            for g in cat.groups]



def options_meta(cat: Category, group_key: str) -> list:
    for g in cat.groups:
        if g.k == group_key:
            return [{"k": o.k, "l": o.l} for o in g.options]
    return []


def _find(cat: Category, key: str):
    for g in cat.groups:
        for o in g.options:
            if o.k == key:
                return g, o
    return None, None


def page_rules(cat: Category, selected: list) -> tuple:
    out: list = []
    for key in selected or []:
        _, o = _find(cat, key)
        if o and o.page_exc:
            out.extend(o.page_exc)
    return tuple(dict.fromkeys(out))


# sorguyu bozan karakterler
_MODEL_TEMIZ = str.maketrans({c: " " for c in '"()|-+*?[]{}'})


def model_kelimeleri(model: str) -> list:
    return [w for w in (model or "").translate(_MODEL_TEMIZ).lower().split() if w]

def build(cat: Category, selected: list, model: str = "") -> dict:
    sel = [s for s in selected if s]
    mkel = model_kelimeleri(model)
    by_group: dict = {}
    for key in sel:
        g, o = _find(cat, key)
        if g:
            by_group.setdefault(g.k, []).append(o)

    parts: list = []
    excludes: list = []
    labels: list = []
    site_extra = ""

    for g in cat.groups:
        chosen = by_group.get(g.k)
        if not chosen:
            continue
        labels.append(" / ".join(o.l for o in chosen))

        if g.k == cat.primary and chosen[0].site:
            site_extra = chosen[0].site

        if len(chosen) == 1:
            o = chosen[0]
            parts.extend(o.req)
            if o.any:
                parts.append("(" + "|".join(o.any) + ")")
            excludes.extend(o.exc)
        else:
            # ayni grupta coklu secim -> OR grubu
            alts: list = []
            for o in chosen:
                alts.extend(o.req or o.any)
            if alts:
                parts.append("(" + "|".join(alts) + ")")
            # coklu secimde dislama yok

    # Model kelimeleri zorunlu "poco x8 pro" -> x8 VE pro gecmeli
    parts.extend(mkel)

    # Kategori korumasi secimlerden bagimsiz her sorguya eklenir
    if cat.guard_any:
        parts.append("(" + "|".join(cat.guard_any) + ")")
    excludes.extend(cat.guard_exc)

    # tekrar kategori ekleme
    if site_extra:
        site_query = (site_extra if cat.base in site_extra
                      else site_extra + " " + cat.base).strip()
    else:
        site_query = cat.base

    # model varsa kategoriyi cikar
    if mkel:
        site_query = ((site_extra + " ") if site_extra else "") + " ".join(mkel)

    query = '"%s" %s' % (site_query, " ".join(parts))
    if excludes:
        seen: set = set()
        # bosluk yerine alt cizgi yoksa iki kelimeye bolunuyor
        uniq = [e for e in (x.replace(" ", "_") for x in excludes)
                if not (e in seen or seen.add(e))]
        query += " " + " ".join("-" + e for e in uniq)

    if mkel:
        labels.append(" ".join(mkel).upper())
    label = cat.l + (" · " + " · ".join(labels) if labels else "")
    return {"query": query.strip(), "label": label[:120],
            "site": site_query, "min_price": cat.min_price}
