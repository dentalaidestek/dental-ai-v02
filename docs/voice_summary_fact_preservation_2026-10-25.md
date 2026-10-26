# Muayene özetinde alanların korunması — 25 Ekim 2026

## Yeniden üretilen hatalar

1. Son değerlendirme üreticisi her özet maddesinde `field`, `text` ve `quote` döndürüyor. Arayüzün tekrar anahtarı yalnız metin ve alıntıyı içeriyordu. İlaç ve alerji beyanlarının ikisi de “Yok” olduğunda tek madde kalıyordu. Regresyon testi beklenen iki madde yerine bir maddeyle başarısız oldu.
2. Aynı `text` ve `quote`, iki ayrı satırda “Dayanak” ve “Bilgi” olarak yazılıyordu. Bu üretici tarafından sık oluşturulan normal bir durumdur. Test iki alan için iki görünüm beklerken dört görünümle başarısız oldu.
3. Özet maddeleri alan etiketi olmadan gösteriliyordu; ilaç ve alerji beyanı ayırt edilemiyordu. Alan etiketi beklentisi de düzeltme öncesinde başarısız oldu.

## Düzeltme

- Tekrar anahtarına varsa alan adı eklendi. Aynı alanın aynı maddesi temizlenir; farklı alanlar aynı değeri taşısa da korunur.
- Özet mevcut Türkçe alan etiketlerini kullanır. Alanı bulunmayan eski maddeler “Bilgi” etiketiyle çalışmaya devam eder.
- Birbirinin aynısı olan alıntı ve değer bir kez gösterilir. Farklı bir dayanak alıntısı korunur.
- Bölüm adı “Muayene bilgileri” yapıldı; ilaç ve alerji beyanları fiziksel klinik bulgu olarak adlandırılmaz.
- Klinik yorum, kaynak doğrulaması ve hasta dosyasına kayıt davranışı değiştirilmedi. Ek sağlayıcı çağrısı yok.

## Doğrulama

- Her regresyon önce mevcut kodda başarısız oldu, ardından düzeltmeyle geçti.
- Mevcut yerel Python testlerinin tamamı: **210 geçti**, 40 bağımlılık deprecation uyarısı.
- Mevcut 10 Node test dosyası geçti: kısmi PDF hazırlığı, randevu, ses içe aktarma, cihaz kontrolü, kayıt/temizlik, metin kurtarma, son değerlendirme, canlı dinleme, PCM ve özet yerleşimi.
- JavaScript sözdizimi kontrolü geçti.
- Bağımsız salt okunur kod incelemesinde kritik veya önemli bulgu yok.
- İlk geniş Python denemesinde yerel test ortamında eksik `urllib3` nedeniyle 31 test başarısız oldu. Üretim gereksinimindeki `urllib3==2.8.0` test ortamına kuruldu; sonraki tam çalıştırmada 210 test geçti. Bu durum için üretim bağımlılığı değiştirilmedi.

## Sınırlar

Bu sonuçlar yerel otomatik kontrollerdir. Gerçek mikrofon, mobil tarayıcı görünümü, modelin klinik doğruluğu ve 60.000 kullanıcı yükü için kanıt sayılmaz. Değişiklikler PR #215 üzerindedir; bu çalışma sırasında merge veya canlı dağıtım başlatılmadı.

Test panoları: [Figma](https://www.figma.com/design/kvN5w5f1AFaSYEQC0OHUQN), [PostHog](https://eu.posthog.com/project/318683/dashboard/1052412).
