# Dental AI — hız, maliyet, yük ve devir eksikleri

9 Ekim 2026. Başlangıç commit: 2504a6e9752c33b3995aef4e8a381a36a2e7a584.
Branch: work/security-privacy-recovery-20261009. Main/production/mobile branch,
Render ayarları, bildirim tercihi ve deploy değiştirilmedi.

Bu kontrol önceki güvenlik raporundan devam eder; tamamlanan güvenlik işleri
baştan incelenmedi. Bulgular repo koduna dayanır. Canlı Render/Brevo/R2/AI
faturası, aktif production env, trafik veya p95 ölçümü alınmadı. Dolayısıyla
TL tasarrufu, gerçek RAM tüketimi veya üretimdeki servis sayısı iddiası yoktur.

## Bu oturumda kapatılan gereksiz yük

| Bulgu | Etki | Düzeltme / kanıt |
|---|---|---|
| NativeDentalAI effect, analysis nesnesine bağımlıydı | Event sonrası getAnalysis -> yeni nesne -> effect -> tekrar getAnalysis; sürekli GET/DB ve render riski | Bağımlılık sabit analysis ID; geç kalan effect sonucu iptal edilir. Bir event/sonuç nesnesi değişimi tek istek; yeni event yeni istek; ilgisiz analiz event'i sıfır istek testi |
| Native vaka listesi döngü içinde kullanıcı ve son mesaj sorguluyordu | 50 vaka için teorik en çok 101 SELECT; her realtime refetch bunu tekrarlar | Tek vaka sorgusu, toplu kullanıcılar, partition/window ile son mesajlar: sabit 3 SELECT. Aynı timestamp'te son ID belirleyici; sahibi olmayan vaka dışarıda |
| Native ders listesi her ders için count yapıyordu | 50 ders için 51 SELECT | Sahibe ve görünen ders ID'lerine bağlı GROUP BY: sabit 2 SELECT; diğer kullanıcı materyali sayılmaz |
| StudyMaterial native API'de import edilmemişti | Dolu ders listesi NameError; ekranın hata yutmasıyla eksik işlev görünmezdi | Import düzeltildi; gerçek dolu ders/veri kapsamı testi eklendi |

Boş vaka/ders listeleri yalnız bir SELECT kullanır. Ölçümler handler içi gerçek
SQLAlchemy SELECT sayısıdır; HTTP authentication/middleware sorguları dahil
olmadığından toplam endpoint sorgusu diye sunulmaz. GET döngüsü ücretli AI
analizini doğrudan tekrar başlatmıyordu; DB/ağ/CPU/batarya yükü yaratıyordu.
Bu değişiklikler yeni servis veya migration gerektirmez.

## Kalan pahalı veya gereksiz olabilen işler

| Öncelik | Kodda görülen durum | Maliyet/yük | Güvenli sonraki adım |
|---|---|---|---|
| Yüksek | ConsultationChat her MESSAGE_CREATED için getConsultation; handler bütün mesajları all() ile döndürür | Uzun konuşmalarda her yeni mesajla tüm geçmiş tekrar taşınır; toplam veri hacmi büyür | Cursor ile eski mesaj sayfalama, after_id ile yeni mesaj delta, ID dedup; katılımcı yetkisi her istekte korunmalı |
| Yüksek | Home, PatientDetail, Program, AnalysisHistory, Consultations event'te tam ilgili listeyi yeniden çeker; açık kalan ekranlar da event dinler | Aynı değişiklik birden fazla istek ve veri sorgusu doğurabilir | Entity bazlı state patch, görünür ekran önceliği, eşzamanlı aynı isteği birleştirme; burst event kaybını çözmeden event'leri rastgele düşürme |
| Yüksek | Academic ask yalnız React busy state ile düğmeyi kapatır; sunucu idempotency sözleşmesi görünmüyor | Ağ belirsizliği/tekrar/double tap aynı ücretli soruyu tekrar başlatabilir | Aynı kullanıcı+ders+istek kimliği için DB unique admission; içerik/resource-version uyumu ve tamamlanan cevabı yeniden kullanma |
| Orta | Uygulama kuyruğu ve index worker boşken varsayılan 2 saniye aralıkla DB kontrol eder | Sürekli boşta çalışan bir döngü teorik 43.200 tur/gün; tur birden çok DB sorgusu olabilir. AI isteği sayısı değildir | Mevcut PostgreSQL NOTIFY/wakeup ile hızlı uyandırma ve yavaş recovery; ayrı ücretli Redis/worker eklemeden ölçerek aşamalandırma |
| Orta | render.yaml web ile colocated index subprocess ve embedded uygulama worker'ını aynı servis kaynaklarında çalıştırıyor | OCR/PDF/index/vision koordinasyonu web gecikmesini ve bellek baskısını artırabilir | Önce queue age, p95 ve RSS ölçümü; admission/mini batch/reuse. Ek ücretli servis açmak ilk adım olmamalı |
| Orta | Native uzman listeleri her profil için User sorgular; listeler 50 ile sınırlı | Görünür uzman sayısına göre ek SELECT | Toplu kullanıcı/PROFILE JOIN; onay/kimlik/specialty filtrelerini aynen koruma |
| Orta | Academic V2 output üst sınırı 7000 token | Uzun çıktıların gecikme/ücreti artar; bu her cevapta 7000 tüketildiği anlamına gelmez | Soru türüne göre ölçülmüş sınır; kapsamlı ders yanıtı/klinik kaliteyi bozacak kör azaltma yapma |
| Orta | Request bütçesi isteğe bağlı STUDY_ROUTER_REQUEST_BUDGETS_JSON; repo Render template'inde tanımlı değil | Concurrency sınırı toplam aylık harcamaya üst sınır değildir | Canlı env doğrulandıktan sonra gerçek plan bazlı gün/ay request ve token/para ölçümü; kullanıcı/kurum admission. Canlı ayarın yok olduğu iddia edilmez |

Kullanıcı akışı kontrolünde Academic history endpoint'inin ilk 100 mesajı
getirerek yeni cevapları görünmez bıraktığı doğrulandı ve düzeltildi. Artık en
yeni 100 mesaj ekrana kronolojik sırayla verilir; depolanmış eski mesajlar
silinmez. Daha eski geçmiş için tam cursor/sayfalama işlevi hâlâ açıktır.
Native hasta listesi yalnız ilk 30 kaydı alıyor; devam sayfalaması yok. Analiz
hasta seçiminde gelen listenin ilk 12'si gösteriliyor. Büyük klinikte görünmeyen
hastaları arama/cursor olmadan seçmek mümkün olmayabilir.

## Zaten maliyeti sınırlayan parçalar — koru

- render.yaml tek web servisi ve tek Uvicorn worker tanımlıyor; otomatik deploy
  ve preview kapalı. Gerçek production topolojisi bu dosyadan kanıtlanamaz.
- Shadow academic V1 index kapalı; aynı dosya için V1+V2 işi template'te açılmıyor.
- Academic V2 final generation tek provider/model çağrısıyla sınırlı; zor
  retrieval için ayrıca sınırlı planning çağrısı mümkün. Genel sınırsız fallback yok.
- Klinik provider 1800 output üst sınırı, ortak provider reservation; clinical
  router successful-result cache; durable iş/idempotency ve backlog sınırları var.
- Veri tabanı pool, upload/concurrency, R2 local-cache ve küçük OCR/embed batch
  sınırları tanımlı. Bunları kapasite/latency ölçmeden büyütmek maliyeti artırabilir.
- Klinik medya private/no-store, sahiplik/oturum kontrolü korunmalı. Hasta verisini
  public CDN veya kullanıcılar arası ortak cevap cache'iyle ucuzlatma.
- Event ve veri aynı transaction'da; maliyet için veri bütünlüğü/audit kaldırılmamalı.

## Devir mesajıyla kalan iş eşlemesi

| Alan | Durum |
|---|---|
| Web/native login, token restore, explicit e-posta kodu kurtarma | Önceki commitlerde düzeltildi; bu oturum tekrarlanmadı |
| Native profil düzenleme, parola/hesap silme, cihaz yönetimi | Profile component görüntüleme/çıkış ve navigation sunuyor; bu yerel eylemler yok. Backend ve güvenli parola onayıyla eklenmeli |
| Native hasta/program düzenleme-silme, klinik notlar | Mevcut oluşturma/görüntüleme bunların tamamlandığını kanıtlamaz; feature matrix ve ortak web backend entegrasyonu açık |
| Academic not yükleme/index durumu | Academic ekranında ders seçimi+soru/cevap var; tam upload/index kontrol akışı açık |
| Native mesaj reply, foto/dosya/ses, destek, değerlendirme | Web ile tam eşitlik açık; yalnız text chat tamamlandı sayılmaz |
| Realtime her ekran / cursor / burst | Önceki imleç düzeltmesi korundu; bu oturum analiz döngüsü kapandı. Delta/cursor, burst dağıtımı ve görünür ekran yönetimi açık |
| Tüm endpoint yetki/CSRF/XSS/SSRF, tam erasure, gerçek E2EE/break-glass | Önceki açıklar kapanmış sayılmaz; kapsamlı güvenlik doğrulaması ayrı aşama |
| PostgreSQL/Render/R2/Brevo ve fiziksel Android | Canlı/staging entegrasyon doğrulaması açık; JS export fiziksel cihaz testi değil |

## En kritik sonraki kilometre taşı

**Ücretli Academic isteğine sunucu idempotency admission + mesaj geçmişine
cursor/delta + realtime istek birleştirme.** Aynı backend ve PostgreSQL üzerinden,
yeni ücretli servis eklemeden ilerlenmeli. Önce tek işlemin tek AI isteği ve tek
relevant fetch ürettiği; sonra çapraz kullanıcı/cihaz ve disconnect senaryoları
ölçülmeli. P0 güvenlik/erasure kapsamı ve önceki schema revision 9 release
kontrolleri deploy gate olmaya devam eder.

## Bu paketin testleri

- 31 backend testi başarılı: yeni query-count/sahiplik testleri, consultation
  lifecycle ve realtime regressions. İlk yeni course testi missing import'u
  yakaladı; import düzeltildikten sonra set yeşil.
- TypeScript ve 16 native davranış testi başarılı; yeni test gerçek NativeDentalAI
  effect'ini çalıştırır ve state replacement sonrası request loop olmadığını kontrol eder.
- Android Metro/Hermes export başarılı: 843 modül. Fiziksel cihaz / APK / üretim p95
  ve gerçek fatura tasarrufu bu testlerin kapsamı değildir.

## Kullanıcı etkisi ve ana site regresyon kontrolü

Son maliyet düzeltmeleri kullanıcı akışı açısından yeniden kontrol edildi.
Native analiz effect cleanup'ının ilgisiz event geldiğinde bekleyen sonucu
iptal ettiği bulundu ve request-generation kontrolüne taşındı. Yeni ilgili
istek eski yanıtı geçersiz kılar; ilgisiz event doğru sonucu kaybettirmez.
Analiz/token değişimi ve unmount hâlâ eski sonucu reddeder. İstek döngüsü geri
getirilmedi. Academic son 100 mesaj düzeltmesi 105 mesaj ve başka kullanıcı
mesajıyla test edildi; tüm 105 kullanıcı mesajı DB'de kaldı.

58 backend testi başarılı: query-count/sahiplik, vaka lifecycle, realtime,
account/login, profil/hasta işlemleri, destek ve partial-navigation regresyonları.
TypeScript ve 19 mobil davranış testi başarılı. Bu kapsamda web regresyonu
bulunmadı; bütün site/production/cihaz için sıfır hata garantisi değildir.
Kullanıcı akışını etkilemeyen worker interval, model/output sınırları, altyapı ve
bütçe ayarları değiştirilmedi. Main ve production'a müdahale/deploy yapılmadı.

## Kayıt erişimi tamamlandı — kullanıcı etkisi

Önceki bölümlerde açık olarak belirtilen akademik geçmiş ve 50 kayıt üstü ders/vaka erişimi bu değişiklikle tamamlandı. Native API cevapları mevcut `items` alanını koruyup isteğe bağlı `before` ve `next_before` ekler. Ders ve vaka sırası tarih + ID ile kararlıdır; mesajlar ID cursor ile sayfalanır. Her sayfa en fazla 50 ders/vaka veya 100 mesajdır; toplam kayıt erişimine sınır konulmaz. Veriler silinmez, migration gerekmez.

Android'de daha fazla ders/vaka ve önceki mesajlar düğmeleri vardır. Akademik ekranda yüklenen mesajların son 20 dışındakileri gizlenmez. Realtime yenileme açılmış eski sayfaları korur; büyük reconnect boşluğu olursa cursor yeniden açılır. Ağ hatasında içerik/cursor korunur, görünür hata ve tekrar deneme sunulur. Ders/hesap değişimi ve unmount sonrası eski yanıtlar uygulanmaz. Yeni akademik cevap, geçmiş isteği gecikse veya başarısız olsa bile görünür kalır.

Doğrulama: 48 backend testi (sayfalama, aynı tarihli 205 kayıt, sahiplik, sorgu sınırları, hesap/hasta/destek/vaka/web realtime regresyonları). Mobil: 13 oturum ve 10 realtime/sayfalama davranış testi; TypeScript kontrolü ve Android Hermes export. Export gerçek cihaz/klavye/scroll testi yerine geçmez.

Bu aşama tüm devir listesinin tamamlandığı anlamına gelmez: vaka sohbetinin full-history refetch maliyeti, worker boş sorguları, Academic sunucu idempotency ve önceki güvenlik/mobil parity açıkları ayrı doğrulanabilir iş olarak devam eder. Bildirim içeriği, AI çıktı limitleri, worker sıklığı ve production ayarları değiştirilmedi. Main/production deploy yapılmadı.
