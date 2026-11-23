# Dental Akış yönetim kuyruğu — MFA sınırı ve web yarış düzeltmesi (2026-11-18)

## Web akışı önce incelendi

Kaynaklar:
- `app/templates/admin_social.html`
- `app/static/expert-social-admin.js`
- `app/static/expert-social.js`
- `app/expert_social_api.py`
- `app/main.py` içindeki `_admin_only`, yönetici giriş ve e-posta OTP doğrulama akışı

Web yönetim ekranı üç içerik türünü (POST, COMMENT, PUBLICATION), üç durum filtresini, şikâyet listesini, karar gerekçesini, içerik sürümünü ve karar/operasyon geçmişini sunuyor. Kararlar mevcut `POST /moderation/{kind}/{id}` endpoint'ine, sürüm kontrolüyle gidiyor.

## Bulunan somut UI hatası

Web kuyruğunda tek bir `loading` bayrağı vardı. Bir yönetici istek sürerken içerik türünü/durumunu değiştirdiğinde veya Şikâyetleri Gör'e bastığında yeni `load()` çağrısı sessizce atlanıyordu. İlk isteğin yanıtı daha sonra yeni seçilmiş filtreye aitmiş gibi ekranda kalabiliyordu. Bu, özellikle yavaş bağlantıda filtre ile görünen kuyruğun ayrışmasına neden oluyordu.

Düzeltme:
- Her liste isteğine artan bir generation numarası verilir.
- İstek başlangıcında mode, kind, status ve cursor sabitlenir.
- Yeni bir reset isteği, devam eden isteği geçersiz kılar ve beklemeden başlayabilir.
- Eski yanıtlar listeyi, yaşlandırma sayaçlarını, cursor'u veya loading durumunu değiştiremez.
- Pagination hâlâ tek uçuşlu kalır; reset dışındaki ikinci pagination isteği başlatılmaz.
- Yanıtın item listesi en fazla 30 kayıtla sınırlandırılır.

## Native yönetici kuyruğu neden bu turda açılmadı?

Bu, eksik bir UI butonundan ibaret değil; mevcut yetki sözleşmesidir:

1. `app/expert_social_api.py:actor()` Bearer token ile gelen native isteği ayrı tanır.
2. Native Bearer kimliği normal, iptal edilebilir `SessionToken` kaydından doğrulanır.
3. `request.state.social_admin`, yalnızca cookie tabanlı isteklerde `main._admin_only(request)` ile doldurulur.
4. `admin(request)` bu MFA doğrulanmış nesne yoksa 403 döndürür.
5. `main._admin_only`, sabit yönetici e-postası, aktif/doğrulanmış ADMIN rolü ve `AdminVerifiedSession` cookie kaydını birlikte ister.
6. `AdminVerifiedSession` kaydı, yönetici girişindeki e-posta OTP doğrulamasından sonra oluşturulur.

Dolayısıyla yalnızca `user.role == ADMIN` kontrolüyle native kuyruk eklemek, mevcut ikinci faktör sınırını atlatır. Mevcut native bearer token, geçerli bir web MFA cookie'siyle aynı anda gönderilse bile yönetim yetkisi kazanmamalıdır.

Bu nedenle bu değişiklik native admin endpoint'i veya sahte native yönetim butonu eklemez. Önce ayrı, kısa ömürlü, iptal edilebilir ve yalnızca sosyal moderasyon kapsamlı bir native step-up/MFA sözleşmesi tasarlanmalı; OTP deneme sınırı, replay, cihaz/oturum iptali, süre aşımı ve audit kayıtlarıyla test edilmelidir. Bu iş tamamlanmadan yönetici kuyruğu native'e taşınmış sayılmaz. Web yönetim paneli mevcut MFA akışıyla çalışmaya devam eder.

## Eklenen regresyonlar

- `tests/expert_social_admin_queue.cjs`: filtre değişimi veya şikâyet görünümüne geçiş sırasında eski ağ yanıtının yeni listeyi ezmediğini test eder.
- `tests/expert_social/test_native_auth.py`: native ADMIN Bearer token'ın kuyruk, şikâyet listesi, detay ve karar endpoint'lerine erişemediğini; doğrulanmış web MFA cookie'sinin Bearer isteğine yetki aktarmadığını; web cookie akışının MFA olmadan reddedilip MFA kaydıyla kabul edildiğini kontrol eder.
- Node testi `admin-security-tests.yml` içine, Python regresyonu hem Admin Security hem Security Recovery workflow'una bağlandı.

## Doğrulama ve açık sınırlar

Bu connector çalışma ortamında GitHub dosya okuma/yazma işlemleri ve kaynak sözleşmesi kontrolü yapılabildi. Node test dosyası ve pytest dosyası commit edildi; **bu turda Node test, pytest, tam Android typecheck veya Gradle çalıştırılmadı**. Workflow'lar önceki kullanıcı isteği doğrultusunda `workflow_dispatch` only kaldı; yeni e-posta/CI yükü oluşturmamak için dispatch edilmedi.

PR #257 açık/Draft kalır. Main merge, canlı deploy, migration, mağaza paketi veya gerçek yönetici kararı yapılmadı.
