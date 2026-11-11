# Dental AI — Web kaynaklarını native mobile taşıma envanteri

Kaynak: GitHub `main` dalındaki mevcut web uygulaması. Bu belge tamamlanmış uçtan uca audit değildir; doğrulanmış dosyaları ve eksik karşılaştırmaları gösterir. Canlı ortamın deploy SHA'sı ayrıca doğrulanmalıdır.

## Ana ilke
Web davranışını yeniden icat etme. Önce gerçek şablon + CSS + JavaScript + FastAPI + veri modeli + varlıkları incele, sonra React Native ekranına eşle. WebView kullanma. Kullanıcı onayı olmadan main'e merge/deploy yapma.

## Kaynak haritası
| Alan | Web kaynakları | Native kaynakları | Doğrulanacak |
| --- | --- | --- | --- |
| Diş şeması | `app/templates/tooth_chart.html`, `app/templates/tooth_chart_browser.html`, `app/static/tooth-chart/` | `mobile/src/NativeToothChart.tsx`, `mobile/src/api.ts` | Anatomi görselleri, yüzey pinleri, bilgi/tedavi/not sekmeleri, FDI, süt/kalıcı |
| Ana sayfa | `app/templates/dashboard.html`, `app/templates/base.html`, `app/static/dashboard/mobile/` | `mobile/App.tsx` | Fotoğraf kartları, alt gezinme, arama, uzman profili |
| Ortak stil | `app/static/style.css`, `app/static/design-system.css`, şablon içi CSS | Native ekran stilleri | Tipografi, navy/blue tokenları, boşluklar, mobil kırılımlar |
| FastAPI/veri | `app/main.py`, `app/mobile_api.py`, `app/mobile_modern_api_v3.py` | `mobile/src/api.ts`, `mobile/src/modernApi.ts` | Yetki, hata sözleşmesi, klinik kayıtların kalıcılığı |
| Analiz | `app/mobile_analysis_api.py`, `app/main.py` | `mobile/src/analysisApi.ts` | Yükleme, job devamlılığı, sonuç, geçmiş |
| Sesli muayene | `app/templates/voice_exam_session.html`, `app/voice_exam_*.py` | Native ses akışı | Başlat/duraklat/bitir, tam metin, kaynaklar, izinler |
| Uzman/Dental Akış | `app/expert_social_api.py`, `app/static/expert-social.js`, `app/templates/expert_public_profile.html` | Native uzman/akış ekranları | Takip, yorum, gönderi, moderasyon, görsel görüntüleyici |

## Diş şeması kaynak doğrulamaları
- Web şablonu `app/templates/tooth_chart.html` CSS içinde `--navy:#08294f`, `--blue:#0878f9` ve klinik durum renklerini tanımlıyor.
- Anatomik atlas: `/static/tooth-chart/enamel-atlas-v2.webp`. CSS'de `background-size:400% 100%` ile molar/premolar/canine/incisor konumları kullanılıyor; alt çene 180 derece döndürülüyor.
- Diş tiplerine ait SVG'ler: `incisor.svg`, `canine.svg`, `premolar.svg`, `molar.svg`, `primary-incisor.svg`, `primary-canine.svg`, `primary-molar.svg`, `implant.svg`.
- Detay görünümü `preview-svg` ve konumlandırılmış `surface-pin` öğelerini kullanıyor; yüzey konumları mevcut CSS'den birebir alınmalı.
- Native uygulamadaki mevcut renkli numara kutuları anatomik atlasın yerine geçmiyor. Anatomik varlıkları native'de uygun yerel asset/SVG bileşenleriyle kullanmadan görsel eşleşme tamamlandı denmemeli.

## Bloklayıcı doğrulamalar
1. Gerçek deploy commit SHA'sını `main` ile karşılaştır; aynı olduklarını varsayma.
2. Tüm web şablonları, JS, CSS, route ve statik varlıklar için eksiksiz dosya ağacı çıkar.
3. Diş atlasının sprite kırpma/ölçekleme ve alt çene yönünü Android/iOS'ta test et.
4. Webde tedavi kaydı akışını kontrol et; otomatik tedavi oluşturma kaldırıldıysa kullanıcı için açık kayıt akışı bulunmalı.
5. TypeScript typecheck, testler, Android/iOS cihaz ekran görüntüleri ve API entegrasyon testlerini çalıştır.

## Değişiklik politikası
Bu envanter doğrulanmadan yeni native tasarım uydurulmaz; her modülde mevcut web kaynakları esas alınır. Klinik geçmişe yanlış kayıt eklenmemesi ve hasta yetkileri önceliklidir.
