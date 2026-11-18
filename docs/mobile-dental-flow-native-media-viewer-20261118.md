# Dental Akış native medya görüntüleyicisi — 2026-11-18

## Web-first inceleme

Önce aynı dalın web akışı incelendi:

- `app/templates/expert_following.html`: Dental Akış gönderi galerisi.
- `app/templates/_expert_social.html`: uzman profilindeki gönderi/medya yüzeyi.
- `app/static/expert-social.js`: galeri tıklama ve medya listesi.
- `app/static/expert-media-viewer.js`: canonical tam ekran medya görüntüleyicisi.
- `app/static/expert-social.css`: `#dentalMediaViewer` ve `.ds-media-stage` görünümü.

Web viewer davranışı: aynı gönderide en fazla dört güvenli medya URL'si, 1x–5x yakınlaştırma, iki pointer ile pinch, yakınlaştırılmış görseli pan etme, fit/reset, yatay swipe ile önceki/sonraki görsel, konum sayacı, yükleme/yeniden deneme, klavye kontrolleri ve modal kapatıldığında sayfa/odak durumunu geri yükleme. Web URL doğrulaması yalnızca aynı origin üzerindeki `/api/expert-social/media/` yolunu kabul ediyor.

## Native farkı

`mobile/src/SocialScreens.tsx` içindeki önceki görüntüleyici yalnızca tek bir `Image` bileşenini bir `Sheet` içinde gösteriyordu. Pinch/pan, galeri içinde gezinme, zoom seviyesi, fit, yükleme hatası/yeniden deneme ve swipe davranışları yoktu. Kullanıcı bir gönderinin ikinci görselini açsa bile aynı gönderideki diğer görsellere geçemiyordu.

## Değişiklik

- `mobile/src/NativeSocialMediaViewer.tsx` eklendi.
- `mobile/src/socialMediaViewer.ts` saf doğrulama ve gesture sınır yardımcıları olarak eklendi.
- `SocialScreens.tsx` artık tek URL yerine gönderinin galeri listesini ve seçilen index'i görüntüleyiciye iletiyor.
- Aynı gönderinin galeri sırası korunuyor; link cover medya öğesi webdeki gibi normal galeriden hariç kalıyor.
- Her görüntü ilk taraf `socialImageSource` ile açılıyor; bearer token harici host'a aktarılmıyor.
- Media kimliği ve URL birebir eşleşmiyorsa, yinelenen kimlik varsa veya dört öğe sınırı aşılırsa görüntüleyici boş güvenli duruma geçiyor.
- İki dokunuşla 1x–5x pinch, yakınlaştırılmış görüntüde sınırlandırılmış pan, 1x'te yatay swipe ve butonlarla zoom/fit/prev/next eklendi.
- Görsel yükleme hatasında ayrı hata durumu ve tekrar deneme var; eski görselin geç gelen load/error olayı yeni görselin durumunu ezemiyor.
- Hesap/token değiştiğinde açık medya modalı kapatılıyor.
- Tüm kontroller erişilebilir etiket ve en az 44px dokunma alanı kullanıyor.

Yeni bağımlılık, backend endpoint, polling, veritabanı şeması, medya kopyası veya AI çağrısı eklenmedi.

## Regresyonlar

`mobile/tests/socialMediaViewer.cjs` eklendi ve hem `npm run test:beta` hem Security Recovery `native-social-security` job'una kaydedildi.

Kapsam:
- yalnızca birinci taraf ve kimliğiyle eşleşen medya URL'si;
- en fazla dört benzersiz medya öğesi;
- zoom alt/üst sınırı ve geçersiz sayılar;
- pinch oranı;
- portre/yatay görsel için pan sınırları;
- zoom açıkken swipe ile görsel değiştirmeme;
- yatay/dikey gesture ayrımı;
- listenin başında/sonunda sarma yapmayan gezinme;
- native bileşenin authenticated source, pinch/pan/swipe/retry ve account-scope wiring'i.

## Doğrulama ve açık kapılar

Bu connector-only çalışmada GitHub kaynak dosyaları okunup değiştirildi; test dosyası ve workflow komutu kaynakta kaydedildi. Burada `npm ci`, `npm run typecheck`, `node --test`, Expo export, Android Gradle build veya fiziksel cihaz testi çalıştırılmadı. Bu nedenle testler yeşil olarak raporlanmıyor.

GitHub Actions, önceki istekteki bildirim gürültüsünü artırmamak için `workflow_dispatch` only durumda bırakıldı. Son PR code head'inde otomatik workflow run veya combined status yok. Önceki Android typecheck/Security job kayıtları runner tahsisi öncesi `runner_id=0`, boş step listesi ve `BlobNotFound 404` log sonucu vermişti; tsc/Node/Gradle/pytest başlamadı. Bu kayıtlar kaynak kodu hatasını kanıtlamıyor ve hosted runner/billing alt nedenini belirlemiyor.

Fiziksel Android ve iOS'ta pinch hassasiyeti, VoiceOver/TalkBack, ekran döndürme, arka plana alma, zayıf ağ ve büyük görüntü kabulü açık kalıyor. 60.000 kullanıcı kapasitesi bu iş kapsamında ölçülmedi.

PR #257 açık/Draft kalır. Main merge, canlı deploy, production migration, APK/IPA yayını veya hasta verisi işlemi yapılmadı.

## Isolated verification follow-up

- An isolated Node harness copied the committed pan/zoom/swipe/index helper logic and passed 8 assertions, including the portrait/landscape pan bounds and exact zero normalization.
- The helper and native viewer component passed an isolated strict TypeScript compile with minimal React Native declarations. This checks the component's TS syntax and local types, not the complete app's installed Expo/React Native type graph.
- The committed `socialMediaViewer.cjs` is registered in both package and manual Security Recovery scripts, but the actual repository test file was not run with `npm ci` or the full mobile workspace. No full-app typecheck, Expo export, Android build or device result is claimed.
- A strict equality edge case was found during the isolated pan check: clamping could return negative zero on a centered axis. The helper now canonicalizes both zero offsets to positive zero, making pan results deterministic.

Final branch HEAD after this follow-up: `38a7540682717fc895972c8e6899ad9e44ee086e`.
