# Tarama Derinliği ve Boyut Hesabı Düzeltmesi — Tasarım

Tarih: 2026-06-04
Durum: Onaylandı (implementasyon planı bekleniyor)

## Problem

`clean_mac.sh` tabanlı Apple Cleanup aracında iki doğrulanmış hata ve bir
geliştirme isteği var:

1. **Tarama toplamı şişiyor (Problem 1).** "Toplam temizlenebilir" rakamı
   diskte var olmayan bir değer gösteriyor (ör. 34 GB). Sebep: kategoriler
   birbirinin içine giriyor ve `print_scan_table` (`clean_mac.sh:449`) ile
   `do_scan_json` (`:1322`) tüm kategori boyutlarını körlemesine topluyor.
   - CAT `app_leftovers` tüm `~/Library/Application Support/*` klasörlerini
     sayar (`scan_app_leftovers:308`).
   - CAT `browser_full` ise `Application Support/Google/Chrome`, `Firefox`,
     `BraveSoftware` vb. yollarını sayar (`BROWSER_FULL_DIRS:54`) — bunlar
     zaten Application Support altında → **iki kez sayım**.
   - CAT `app_uninstaller` yüklü her uygulama için `Application Support/$app`
     + `Caches/$app` sayar (`scan_app_uninstaller:401`) — bunlar `user_cache`
     ve `app_leftovers`'ta zaten var → **üç kez sayım**.

2. **"Silinen 10 GB, gösterilen 30 GB" (Problem 2).** `TOTAL_FREED`, silmeden
   hemen önce `du -sk` ile ölçülüp toplanıyor (`safe_rm:148`,
   `safe_rm_contents:173`). `du` ile macOS/APFS'te gerçekte açılan disk alanı
   ciddi ayrışır:
   - `get_dir_size_bytes` (`:112`) her alt öğeye **ayrı** `du -sk` çalıştırıp
     topluyor → kardeş klasörler arası hardlink'ler iki kez sayılır.
   - APFS clone'ları: `du` her klonu tam boyutuyla sayar ama klonu silmek yer
     açmaz.
   - Binlerce küçük dosya blok boyutuna yuvarlanır → şişer.
   - Silinen veri yerel snapshot'a takılıp "purgeable" olabilir; `df` hemen
     artmaz.

3. **Tarama derinliği yetersiz.** Açık kaynak temizleyiciler (mac-cleanup,
   Pearcleaner, OnyX) çok daha fazla alan kapsar (geliştirici cache'leri,
   sistem/geçici, yerel snapshot'lar).

## Kararlar (kullanıcı onaylı)

- **Freed ölçümü:** `df` farkı = otoriter gerçek kazanç. `du` toplamı yalnızca
  "tahmini" olarak gösterilir.
- **Kapsam:** Bug düzeltmesi + tarama derinliği (geliştirici + sistem/geçici +
  purgeable/snapshot) + mevcut taramaların doğruluğu.
- **Güvenlik duruşu:** Her şeyi göster, kullanıcı seçsin. `node_modules`,
  `.gradle`/`.m2` bağımlılıkları dahil listelenir; riskli olanlar açıkça
  etiketlenir ve silme için açık onay ister.
- **Mimari:** Hafif registry refactor (bash 3.2 uyumlu).

## Kısıtlar

- **bash 3.2 uyumluluğu zorunlu** (`clean_mac.sh:65`). macOS stok bash'i
  `declare -A` (associative array) desteklemez. Registry bu yüzden tek bir
  dizi + pipe ile ayrılmış satırlar olarak kurulur.
- Mevcut JSON API sözleşmesi (`--scan-json`, `--clean-json`, `--status-json`)
  ve web/server.py per-kategori alt-seçim argümanları (`--app-leftovers`,
  `--browser-full-sub`, `--developer-sub`, `--ios-backups-sub`,
  `--app-uninstaller-sub`) korunur, genişletilir.
- Mevcut `tests/test_server_validation.py` davranışı kırılmaz.

## Tasarım

### 1. Kategori registry'si (bash 3.2 uyumlu)

`CAT_IDS / CAT_NAMES / CAT_SIZES / CAT_NEEDS_SUDO` paralel dizileri yerine tek
`CATEGORIES` dizisi. Her satır pipe ile ayrılmış kayıt:

```
id|ad|scan_fn|clean_fn|needs_sudo|risk|in_total
```

- `risk`: `safe` | `caution` | `danger`
- `in_total`: `1` → manşet TOPLAM'a girer; `0` → girmez (örtüşen/interaktif
  seçici, ör. `app_uninstaller`).
- `CAT_SIZES`, `CATEGORIES` ile aynı indeksli sayısal dizi olarak kalır
  (runtime'da mutasyona uğrar).
- Erişim yardımcısı: `cat_field <index> <field_name>` (satırı `IFS='|'` ile
  ayrıştırır).

Registry, indeks-hizalama hatasını ortadan kaldırır: yeni kategori = tek satır.

### 2. Problem 1 düzeltmesi (tarama toplamı çift sayımı)

- `scan_app_leftovers`, tarayıcı profil üst dizinlerini (Google, Firefox,
  BraveSoftware, Microsoft Edge, com.operasoftware.Opera, Arc) hariç tutar
  (CAT `browser_full` bunların sahibidir).
- `app_uninstaller` kategorisi `in_total=0` ile işaretlenir.
- Manşet TOPLAM = yalnızca `in_total=1` kategorilerin toplamı. UI/CLI'de
  "tahmini temizlenebilir" olarak etiketlenir.

### 3. Problem 2 düzeltmesi (freed = df farkı)

`do_clean_json` ve interaktif özet:

- Temizlik öncesi: `df_before=$(df -k / | awk 'NR==2{print $4}')` (KB cinsi
  available).
- Tüm temizlik sonrası: `df_after`; `real_freed=$(( (df_after - df_before) * 1024 ))`.
- JSON çıktısı:
  - `freed_bytes` = **df-farkı (otoriter)**.
  - `estimated_bytes` = eski `du` toplamı (şeffaflık için).
  - `freed_human` = df-farkının insan-okunur hali.
- `real_freed < 0` (başka süreçler veri yazmış olabilir) → `0`'a kıstır ve
  JSON'a `freed_note` flag'i ekle.
- Per-kategori `freed` `du` tahmini kalır (df kategori başına güvenilir değil),
  öyle etiketlenir.
- df parse edilemezse → `du` tahminine düş ve `freed_source: "estimated"`
  flag'i koy.

Web (`web/script.js:711`) büyük rakamda `freed_bytes`'ı (df-farkı) gösterir;
tahmini ikincil olarak gösterilebilir.

### 4. `get_dir_size_bytes` doğruluğu

Alt-öğe başına ayrı `du -sk` döngüsü yerine tek `du -sck <items>` çağrısı
(hardlink'ler çağrı içinde tekilleşir). Manşet artık df'ten geldiği için bu
ikincil bir iyileştirmedir ama tahmini gerçeğe yaklaştırır.

### 5. Yeni kategoriler

Her biri registry satırı + `scan_<id>` / `clean_<id>` fonksiyonu.

**Geliştirici** (mevcut `developer` kategorisini alt-öğelere genişlet;
`developer_selected` / `--developer-sub` mekanizmasını yeniden kullan). Alt
öğeler ve risk etiketleri:

| Alt öğe | Yol / komut | Risk |
|---|---|---|
| Xcode DerivedData | `~/Library/Developer/Xcode/DerivedData` | safe |
| iOS DeviceSupport | `~/Library/Developer/Xcode/iOS DeviceSupport` | safe |
| CoreSimulator Caches | `~/Library/Developer/CoreSimulator/Caches` | safe |
| Xcode Archives | `~/Library/Developer/Xcode/Archives` | caution |
| Erişilmez simülatörler | `xcrun simctl delete unavailable` | safe |
| Homebrew cache | `brew --cache` | safe |
| npm/yarn/pnpm cache | `npm config get cache`, `~/Library/pnpm`, yarn cache | safe |
| pip cache | `~/Library/Caches/pip` | safe |
| CocoaPods cache | `~/Library/Caches/CocoaPods` | safe |
| Gradle cache | `~/.gradle/caches` | caution |
| Maven repo | `~/.m2/repository` | caution |
| Docker | `docker system df` (yalnızca rapor) | caution |
| node_modules bulucu | belirtilen kök altında `find -name node_modules` | danger |

**Sistem & geçici** (her biri kategori veya alt-öğe):

- DiagnosticReports / crash logları (`~/Library/Logs/DiagnosticReports`,
  sudo ile `/Library/Logs/DiagnosticReports`)
- QuickLook thumbnail cache
- Font cache
- Saved Application State (`~/Library/Saved Application State`)
- Diğer ciltlerin çöpü (`/Volumes/*/.Trashes`)
- Eski indirilenler (yalnızca rapor; silme değil)

**Purgeable / snapshot** — silme kategorisi değil, **maintenance action**:

- `tmutil listlocalsnapshots /` ile yerel Time Machine snapshot'larını listele.
- "Snapshot inceltme" eylemi: `tmutil thinLocalSnapshots / <bytes> <urgency>`.
  Bu, purgeable alanı gerçek boş alana çeviren tek mekanizmadır.
- Mevcut flush-dns / purge-ram maintenance kartları desenini izleyen yeni
  `/api/thin-snapshots` endpoint'i + UI kartı.

### 6. Risk etiketlerinin UI'a akışı

- Registry `risk` alanı scan JSON'a kategori ve alt-öğe başına yansır.
- Web rozet gösterir (safe / caution / danger).
- `danger` öğeler clean payload'a girmeden önce açık checkbox/onay ister.
- `web/server.py` doğrulama whitelist'leri yeni alt-öğe anahtarları
  (`_validate_developer_item` genişletmesi) ve yeni kategori id'leri için
  güncellenir.

### 7. Bileşen sınırları

- **Registry + accessor**: kategori meta verisinin tek kaynağı. Diğer kod
  yalnızca `cat_field` üzerinden okur.
- **scan_* / clean_* fonksiyonları**: her biri tek kategoriden sorumlu; girdi
  yok, `CAT_SIZES[i]` veya `TOTAL_FREED` mutasyonu üzerinden konuşur.
- **Boyut yardımcıları** (`get_size_bytes`, `get_dir_size_bytes`,
  `format_bytes`): saf ölçüm, yan etkisiz.
- **df-delta ölçer**: temizlik orkestrasyonunda (`do_clean_json`) izole; gerçek
  kazancın tek kaynağı.
- **Snapshot maintenance**: silme akışından tamamen ayrı endpoint/fonksiyon.

## Hata yönetimi

- Araç yoksa (brew/npm/docker kurulu değil) → ilgili scan `0` döner / atlar,
  hata üretmez.
- sudo gerektiren yollar mevcut davranışı korur (sudo yoksa atlanır).
- df parse hatası → `du` tahminine düş + JSON flag.
- `tmutil` hatası → kullanıcıya bilgi mesajı, çökme yok.

## Test stratejisi

- **Bash harness**: geçici `HOME` + fixture dizinlerle `--scan-json` çağırıp
  (a) çift sayım olmadığını, (b) TOPLAM'ın `in_total=0` kategorileri
  dışladığını doğrula.
- **Registry bütünlüğü**: her satırın 7 alanı var, `scan_fn`/`clean_fn`
  tanımlı.
- **df-delta**: `df` mock'lanarak `real_freed` hesabı (negatif kıstırma dahil).
- **Server validation**: yeni alt-öğe anahtarları ve kategori id'leri için
  whitelist testleri; mevcut testler yeşil kalır.

## Kapsam dışı (YAGNI)

- Tarama motorunun Python'a taşınması.
- Eski indirilenlerin otomatik silinmesi (yalnızca rapor).
- node_modules dışındaki proje-içi dosyaların otomatik taranması.
