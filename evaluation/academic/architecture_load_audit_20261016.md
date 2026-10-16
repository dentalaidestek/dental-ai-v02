# Dental AI — akış ve kaynak yükü, 16 Ekim 2026

## Görev paylaşımı ve depolama

- Canlı izlerde soruyu Gemini yorumluyor. Yerel yönlendirme varsayılanı kapalı. Yerel kod erişim, kaynak seçimi, bütçe ve sözleşme doğrulamasını yapıyor. Standart dar sorularda komşu kavram grafiğine genişleme kapatıldı; ayrıntılı/tam başlık istekleri kapsamını koruyor.
- R2 etkin yapılandırmada özgün PDF/görsel Cloudflare R2'de tutulur; bu Anthropic Claude depolaması değildir. İndirme, özgün sayfa görüntüsü, OCR kontrolü ve yeniden indeksleme için korunur.
- PostgreSQL `studyindexpage.text_content` sayfa metni/checkpoint; `studyindexchunk` arama metni, başlık, sayfa ve isteğe bağlı embedding metadata'sını tutar. Her chunk özgün PDF'nin kopyası değildir. Sayfa metnini bugün silmek eski eksik chunkları tamamlayan native kanıt yolunu bozar.
- İhtiyaç olduğunda tek sayfalık PDF `visual_pdf_bytes` alanında saklanır. Ayrıca sınırlı RAM/disk önbellekleri vardır. Bu ilave depolama ayrıca ölçülmelidir; chunk metniyle aynı şey değildir.
- Web, kalıcı işi kaydettikten sonra Modal dispatch çağrısını arka planda yapar. İş/sürüm/checkpoint durumu PostgreSQL'dedir. Modal'ın canlı işçi kodu ve dağıtım ayarlarına bu oturumda erişilemedi. Repoda isteğe bağlı colocated worker da vardır; bütün indeksleme aşamalarının çalıştığı yer yeniden doğrulanmış sayılmamalıdır.
- Hazır indeksle normal cevapta Modal'dan chunk istenmez veya bütün dosyalar yeniden OCR yapılmaz. Kaynaklar PostgreSQL'den seçilir; görüntü gerekiyorsa özgün sayfa/önbellek kullanılır. R2 disk önbelleği isabetinde tekrar HEAD/GET yapılmaz.

## Yayına alınan değişiklikler

| PR | Değişiklik | Kanıt |
|---|---|---|
| 126 | Küçük ders kontrolünü en çok 129 kayıtla sınırla | SQL'de 128/129/2000 kaydın değerlendirilen gövde sayısı ölçüldü |
| 127 | Dar tanım/karşılaştırmada komşu kavramlara genişlemeyi sınırla; tam native sayfayı seçime baştan kat | Gonion canlı: 17 → 3 parça, taranmış sayfa 4 → 1 |
| 128 | Genel sözcükler yerine özgül kaynak adlarını aday frekansıyla ağırlıklandır | Bölünmüş ad, dengeli karşılaştırma, çekimli sorgu geri dönüş testleri; NA/NB canlı tablosu doğru |
| 129 | Değiştirmeden PDF aktarımını önceki tamamlanmış cevaptan yap; FTS-only derste gövde boyutu toplamından önce vektör metadata'sını kontrol et | 746 test geçti, 32 ortam testi atlandı, 576 alt test; PGlite SQL kontrolü; gerçek PDF indirildi ve render incelendi |

## Canlı ölçümler

- Gonion önce: trace `56f726546f2f4839a1073cc6ca6fe1e1`, 17 chunk, 4 taranmış sayfa, üretim girdisi 2.153.377 bayt, 11.230 giriş tokenı.
- Kaynak daraltma sonrası benzer istek: trace `3e1be4ce314b42d694f08a7a1c793f83`, 3 chunk, 1 taranmış sayfa, 976.357 bayt, 5.946 giriş tokenı. Tanım ve sayfa33 doğru. İstekler birebir aynı olmadığından kontrollü gecikme benchmarkı değildir.
- İkinci istekte yorumlama 16.656 ms, üretim 4.285 ms. Küçülen girdi aynı oranda toplam hızlanmayı kanıtlamaz.
- Frankfort çok adımlı soru: düzlem46, Porion18, Orbitale34 doğru; 9 chunk ve iki Gemini çağrısı. Fazladan sayfalar hâlâ seçilebiliyor.
- Değiştirmeden PDF: trace `e1f1d972069445bb9ddfd6f8e39d2099`, bir yorumlama çağrısı (7.354 ms), `previous_answer_pdf`, chunk/sayfa araması ve ikinci üretim çağrısı yok. Gerçek dosya 44.327 bayt/1 sayfa; üç atıf korunmuş, eski ret cümlesi yok.
- Normal dar soruda genellikle 1 yorumlama + 1 cevap çağrısı var. Uyumlu hazır vektör kullanılacaksa embedding eklenebilir. Çok bölümlü üretim/sıklık görevlerinde çağrı sayısı değişir.
- FTS-only, yabancı sahip, eski sürüm ve kısmi embedding kayıtlarıyla preflight SQL PGlite üzerinde çalıştırıldı. Native PostgreSQL yük/eşzamanlılık testi olduğu iddia edilmedi.

## Açık kalanlar

1. Orto3–4 soru14 devam şıkkı yanlış harfin altına yazıldı. Başarılı sayılmadı. Modal OCR işçisi güncellenmiş veya kaynak yeniden indekslenmiş değildir.
2. Orto22–24 sıklık tablosu üç satır ve numarasız kayıtlar üretti; özgün 15 numarası yine 5 okundu. Sayfa/sahip kontrolü soru metninin veya numaranın doğruluğunu kanıtlamaz. Tam ders soru frekansı doğrulanmış kabul edilmedi.
3. Sağlayıcı hataları hem yorumlamada hem üretimde tekrarlandı; HTTP503 örnekleri var. Bu, kota dolduğunu kanıtlamıyor. Başarısız çağrılar tamamlanmış yanıt sayılmadı. Erişilebilirlik sorunu sürüyor.
4. Render free planda; canlı ziyaret uyandırma ekranında bekledi. Plan, cron/keepalive veya ücretli sürekli işçi değiştirilmedi.
5. Eski chunklarda kopan adları kurtaran native-sayfa FTS yolu hâlâ ders sayfaları üzerinde arama yapıyor. Başlık bağlantısı önbelleği ilk yüklemede sınırlı metadata okuyor. Her ölçekte ucuz oldukları iddia edilmedi; özgün PDF'yi silmek bu sorgu yüklerini çözmez.
6. Canlı PostgreSQL/R2 boyut ölçümü yok. Saklanan chunklar boşta sürekli CPU tüketmez; yük sorgu, büyük bağlam, rasterizasyon ve model çağrısı sırasında oluşur.

Önceki 20 farklı öğrenci/profesör sorusu `live_audit_20261016.json` içindedir. Bu oturumun yeni denemeleri ve başarısız çağrılar `live_audit_20261016_session.json` kaydında tutulur. Bu denetim evrensel doğruluk veya bütün hataların kapandığı iddiası değildir.
