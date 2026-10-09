# Dental AI — kalan güvenlik, Android ve realtime işleri

9 Ekim 2026. Uygulama/deploy onayı değildir. Main, production ve
`mobile/native-android-current` değiştirilmedi. Çalışma:
`work/security-privacy-recovery-20261009`.

## Kanıtlanan başlangıç durumu

Devir HEAD'i `0427ccf3ffaf9ba837cbb404d2c0fca7b21f749c`, PR #60.
Geçmiş Codex sohbet/snapshot dosyaları bulunamadı; bu çalışma onların
bulunduğunu iddia etmez. Repo commitleri, PR ve gerçek CI kayıtları kullanıldı.

| O HEAD üzerindeki CI | Sonuç | Run |
|---|---|---|
| Mobile Android CI | başarılı | 37817812960 |
| Academic V2 CI | başarılı | 37817812121 |
| vision48-ci application-regressions | 29 başarısız, 682 başarılı, 4 mevcut skip | 37817812062 / job 113450827770 |
| vision48-ci postgres-integration, ready-model-contract, contract-tests | başarılı | 37817812062 |

29 sayısı test hatasıdır; 29 ayrı güvenlik açığı sayısı değildir. Eski run'ın
başarılı olması yeni değişikliklerin başarılı olduğu anlamına gelmez.

Önceki kurtarma commit'i `0fec7094da5894ecaa9eaa4a7a79c39a4b0ffbd9`:
- Native token yalnız 401'de silinir; geçici hata için korunan oturumla tekrar deneme.
- Klinik router/provider payload'larında doğrudan tanımlayıcı minimizasyonu.
- Kayıt sonrası undefined değişken hatası ve HTTPException import'u.
- Tek kullanımlık doğrulama, tutarlı kilit sırası, socket doğrulama şartı.
- Güvenli doğrulama sonrası yönlendirme ve geçici upload temizliği.
- SDK uyumlu SecureStore, lockfile, Android/security CI ve davranış testleri.

## Bu paketin kök neden düzeltmeleri

1. **Dağıtık giriş kontrolü:** Bellek sözlükleri yerine aynı uygulama
   PostgreSQL'inde atomik `INSERT ... ON CONFLICT ... RETURNING` sayaçları.
   Web, native, admin ve yeniden kimlik doğrulama ortak principal kovasını;
   girişler ayrıca IP kovasını kullanır. Kayıt da ortak DB üzerinden sınırlanır.
   DB hatasında 503 ile kapalı kalır; kimlik metni yerine hash saklanır.
   Web/native aynı limit ve pencereyi kullanır; farklı legacy ayarlardan daha
   düşük limit/daha uzun pencere korunur, AUTH_LOGIN_RATE_* açıkça ortak ayardır.
   SQLite üzerinde iki engine ve eşzamanlı 24 denemede yalnız 8 kabul edilir.
   PostgreSQL gerçek concurrency testi CI'ye eklendi, yerelde PG çalıştırılmadı.
2. **İstenmeyen yeniden e-posta yok:** Süresi dolan/tükenen doğrulama kodu
   normal girişte yeniden gönderilmez. Doğru parola ve açık kullanıcı yenileme
   seçimi gerekir. Geçerli kod yenileme isteğinde de korunur. İlk kod gönderimi
   korunur. Testler web/native normal giriş, yanlış parola ve açık yenilemeyi ayırır.
3. **Vision servisi:** Önceki health düzenlemesi bütün analiz handler'larını
   kaldırmıştı. Analiz, model readiness ve viewer yolları geri getirildi;
   health yanıtı sade kaldı. Anahtar kontrolü, tek inference kapasitesi,
   boyut sınırı, gerçek görüntü/çözünürlük doğrulaması ve her sonuçta geçici
   dosya temizliği var. Provider hata metni istemciye aktarılmıyor.
4. **Realtime:** Sunucunun `event_id` alanı okunur. Replay tekrarları deduplicate
   edilir, düşük ID'li fakat görülmemiş event kabul edilir. Sayfalama imleci
   live event imlecinden ayrıdır. Yeniden bağlantıda son 500 ID aralığı yeniden
   istenir; bu sınırlı örtüşme sonsuz gecikmeli commit için garanti değildir.
   Storage yazımları sıraya alınır. Oturum/hesap değişiminden kalan socket ve
   gecikmiş restore yeniden bağlanamaz. Token URL'ye eklenmez.
5. **Native sözleşmeler:** Üst üste kayıtlı aynı method/path operation'ları
   kaldırıldı, ilk/otoritatif API korunur. Academic JSON isteği ve framework
   tarafından çalıştırılan BackgroundTasks; bildirim/vaka alan adaptörleri;
   galeride ortak image upload fonksiyonu ve tek native dosya URL'si.
6. **Atomik veri/event:** Native hasta+profil+durable event, program+event,
   medya kaydı+event tek DB transaction'ında. Event kaydı hata verdiğinde
   yeni hasta/profil kalmadığı davranış testiyle doğrulandı. Dış obje depolama
   ile DB arasında global atomiklik sağlanmış değildir.
7. **Android akışları:** Ders değişiminden kalan mesaj/yanıt başka derse
   yazılmaz. Sohbette çift dokunma kilidi, beklerken durum/hata ve aynı içerik
   tekrarında korunan `client_message_id`; ack/realtime mesaj deduplication.
   Android composer height keyboard avoidance kullanır; fiziksel cihazdaki
   bütün klavye/geri tuşu kombinasyonları henüz doğrulanmadı.
8. **Web yanıt eki:** Görüntü düzenleyici mevcut reply seçimini korur;
   seçilen yanıt metni tek satır/ellipsis olur. Başarılı ek gönderimindeki
   temizleme korunur.
9. **Hesap silme:** Ortak koordinatör aktif E2EE public cihaz anahtarlarını
   da iptal eder. Bu, bütün klinik kayıtların silindiği anlamına gelmez.
10. **Akademik hata gizliliği:** Web/native ortak soru akışındaki sağlayıcı
    exception metni kullanıcı cevabı ve trace içeriğinden kaldırıldı; streaming
    hata cevabı da genel metin kullanır. Bu bütün logların audit edildiği
    anlamına gelmez. Sentetik token/hasta bilgisi içeren hatalarla test edildi.
11. **Test kök nedenleri:** Auth pozitif fixture'ları e-posta doğrulanmış
    kullanıcıyı temsil eder; secure cookie testi HTTPS; cookie socket testi
    Origin gönderir. Bildirim GET'i okunan aktif bildirimi silmez. Yayın testi
    gerçek AnyIO worker-thread sınırını kullanır. Koruma assertion'ları,
    eşikler veya skip listesi gevşetilmedi. Support/consultation lifecycle test fixtures,
    background worker ile tek StaticPool bağlantısını paylaşmak yerine dosya
    SQLite ve ayrı transaction bağlantıları kullanır.

## Açıklar ve öncelik

| Öncelik | Kalan iş | Kabul kanıtı |
|---|---|---|
| P0 | Bütün web/API/R2/admin operasyonları için sahiplik ve rol matrisi; genel CSRF/Origin, stored XSS, SSRF/path traversal kapsamı | Negatif çapraz kullanıcı/rol/cihaz endpoint testleri ve bağımsız inceleme |
| P0 | Hasta, analiz, klinik görsel, danışmanlık ve yedek saklama/silme politikası | Tek hesap silme sonrası DB+R2+AI sağlayıcı+backup envanteri, durable erasure tekrar denemeleri |
| P0 | Production PostgreSQL migration/concurrency ve proxy IP güven sınırı | Disposable PG'de migration iki kez, mevcut veri korunması, farklı instance limit testleri; trusted proxy ayarı |
| P1 | Her ekranda bütün realtime burst event'lerinin işlenmesi, tam refetch'in azaltılması, sınırsız commit-gecikmesi kurtarma | Web/native iki cihaz, disconnect/replay/reorder/duplikasyon/load ölçümü |
| P1 | Klinik/akademik sağlayıcıya gönderilen metin, görsel metadata ve log minimizasyonu | Payload/log kayıtları üzerinde sentetik tanımlayıcı sızıntı testleri |
| P1 | Native web işlev eşitliği: not/dosya ekleme, silme/düzenleme, destek, ses/dosya/reply, cihaz yönetimi | Özellik matrisi ve gerçek backend'e bağlı cihaz E2E senaryoları |
| P1 | APK, gerçek Android keyboard/composer, lifecycle/background, deep link, erişilebilirlik | Emulator + en az bir fiziksel cihaz sonucu |
| Mimari | Denetlenmiş gerçek E2EE ve break-glass | Aşağıdaki ayrı kabul aşamaları |

**Hiçbir tam E2EE veya e-Devlet eşdeğerliği iddiası yoktur.** Mevcut mesaj
bildirimi içeriği ve mevcut yönetici davranışı sessizce değiştirilmedi.

## E2EE değerlendirmesi ve güvenli aşamalar

Mevcut `mobile/src/e2ee.ts` tek cihaz secret key, ephemeral X25519 ve AEAD
primitifleri içeriyor; chat gönderiminde tam, kimlik doğrulamalı ratchet protokolü
entegrasyonu yok. Sender identity binding, signed/one-time prekey, replay-safe
ratchet state, çok cihaz fanout ve ileri gizlilik kanıtı yok. Global SecureStore
secret-key adı hesaplar arasında ayrışmıyor. Bu legacy altyapıyı yeni bir özel
protokol ekleyerek genişletmek yerine sürümlü bir geçiş gerekir.

Resmi kaynaklar (9 Ekim 2026 kontrolü):
- [Signal Double Ratchet](https://signal.org/docs/specifications/doubleratchet/)
- [Signal Sesame / çok cihaz oturumları](https://signal.org/docs/specifications/sesame/)
- [Signal PQXDH](https://signal.org/docs/specifications/pqxdh/)
- [libsignal README](https://github.com/signalapp/libsignal/blob/main/README.md)

libsignal Java/Swift/TypeScript bağları sunar; Signal dışı kullanım için destek
vermez ve bridge/API değişimleri mümkündür. TypeScript binding'i tarayıcı veya
Expo uyumluluğunun kanıtı değildir. Android native bridge ve web çalışma zamanı
ayrı prototiple doğrulanmalıdır; lisans ve bakım sorumluluğu değerlendirilmelidir.

1. Kütüphane/runtime seçimi ve tehdit modeli; sürüm sabitleme; test vektörleri
   ve bağımsız inceleme. Üretim chat davranışı değiştirilmeden prototip.
2. Hesap ve cihaz başına ayrı kimlik, güvenli yerel state, signed/one-time
   prekey dağıtımı, atomik prekey tüketimi, doğrulanabilir kimlik değişimi.
3. Sürüm alanıyla eski plaintext/legacy şifreli mesajları açıkça ayıran migration;
   eski mesajları geriye dönük ileri-gizli olarak etiketlememe. Eski veri için
   açık saklama/export/silme kararı.
4. Atomik ratchet-state güncellemesi; sırasız/tekrar/çok cihaz testleri; cihaz
   iptali sonrası yeni şifreli gönderimden çıkarma; durum kaybında güvenli reset.
   Kayıp cihazdan bütün eski mesajları kurtarma ileri gizlilikle otomatik gelmez.
5. Web/native gerçek cihaz entegrasyonu ve bağımsız kripto incelemesi sonrası
   açık ürün politikasıyla kademeli aktivasyon.

**Bildirim:** Server/push sağlayıcısı plaintext mesaj içeriğini biliyorsa sıkı
server-blind E2EE değildir. Kilit ekranı içerik önizlemesi de yerel gizlilik riski
olmaya devam eder. Kullanıcının içerik önizleme tercihi korunmuştur; seçenekler
ve açık tercih alınmadan gizlilik vaadi veya bildirim değişikliği yapılmamalıdır.

**Break-glass:** Normal admin oturumu plaintext çözememeli. Önerilen güvenli
ayrım: kullanıcı katılımıyla yalnız seçilmiş mesajın incelemeye sunulması; ayrı
reviewer kimliği/yetkisi, güçlü MFA/ayrı secret, süre ve kapsam sınırı, gerekçe,
çift onay ve uygulama DB'sinden bağımsız append-only/WORM audit. Bu bir tasarımdır,
uygulanmış özellik değildir. Server'ın tüm mesajları açabildiği escrow anahtarı
sıkı E2EE modelini değiştirir; bu çelişki ayrı parola eklenerek giderilemez.

## Deploy öncesi gereksinimler

- Bu branch'in tam CI sonuçlarını kontrol et; eski HEAD'in yeşil işlerini yeni
  commit'e aitmiş gibi kullanma.
- Schema revision 9: izole PostgreSQL'de `python -m app.migrate` doğrulaması,
  sonra yetkili release migration'ı; revision kontrolü öncesinde yeni servis
  başlatma. Auth bucket tablosu additive; mevcut hasta verisi dönüştürülmez.
- Trusted reverse proxy/IP ayarı, ortak DB pool/latency, limit değerleri ve
  DB outage 503 davranışını çok instance staging ortamında doğrula.
- Gerçek e-posta teslimi, explicit expired-code yenileme, eski kod replay ve
  farklı cihazdan oturum iptali testleri.
- Vision modelleri/readiness ve doğrulanan gerçek image formatları; native API
  contract/keyboard testleri. Export APK veya klinik model doğruluğu testi değildir.
- CI dışındaki P0 açıkları kapatmadan tam hasta gizliliği/silme/E2EE vaadi verme.

## Yerel doğrulama sonuçları

- İlk hedefli auth/UI/realtime/vision seti: 142 başarılı.
- Geniş tüm-repo çalışması: 676 başarılı, 604 subtest başarılı, 4 mevcut PG skip;
  5 hata sonrası durdu (585 saniye). Bu koşu yeşil olarak raporlanmaz.
  İki vision testinde süreçte önceden yüklenmiş sentetik-geçersiz image fixture
  ile sonradan eklenen gerçek image doğrulaması çakıştı. Son fixture gerçek PNG
  kullanır, concurrency/boyut/cleanup assertionları korunur.
  Üç OCR hatası eksik yerel tesserocr bağımlılığıydı; lock sürümü 2.11.0 kuruldu.
- Başarısız/durulan alanlar ve kalan test dosyaları: 102 başarılı, bir support
  fixture hatası; ayrı DB bağlantılarıyla support dahil güncel hedef set 54 başarılı.
- Son auth/security/account/UI/realtime/vision setinde 178 başarılı, bir consultation
  StaticPool fixture hatası. Consultation fixture da ayrı bağlantılara taşındı;
  yalnız ilgili 15 lifecycle/regression testi yeniden çalıştırılıp başarılı oldu.
  Böylece hedefli 179 testin tamamı artımlı olarak doğrulandı; tek bir son tam-repo
  yeşil koşu iddiası yoktur. Son commit CI'si release gate olmaya devam eder.
- Ortak rate limiter için 24 paralel deneme, iki DB engine, expiry, DB outage,
  web/native ortak kova, revision 8 -> 9 migration ve tekrar migration davranışı
  test edildi. SQLite migration eski kullanıcı kimliğini/hash'ini korudu.
- Native TypeScript başarılı; 13 session/API/cursor ve 2 socket yaşam döngüsü testi
  başarılı (15 toplam). Android Metro/Hermes export başarılı: 843 modül.
- Yeni PostgreSQL concurrency testi mevcut PG CI job'una eklendi. Yerelde PG yok;
  gerçek PostgreSQL, Render/Brevo/R2, emulator/APK ve fiziksel cihaz doğrulaması
  yapılmış sayılmaz. Hiçbir yeni skip veya zayıflatılmış assertion eklenmedi.
