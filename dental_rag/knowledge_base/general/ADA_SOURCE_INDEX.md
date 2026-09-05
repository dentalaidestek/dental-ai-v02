# DENTAL-AI GÜVENİLİR KAYNAK İNDEKSİ

Bu dosya DENTAL-AI RAG sisteminin güvenilir kaynak önceliğini tanımlar.

## 1. ADA Clinical Practice Guidelines

Öncelik:
Çok yüksek

Kullanım:
Klinik karar desteğinde mümkün olduğunda ilk başvurulacak kaynak.

Ana kaynak:
American Dental Association - Clinical Practice Guidelines and Dental Evidence

Konular:
- Karies
- Antibiyotik
- Ağrı yönetimi
- Periodontal hastalık
- Oral kanser
- Radyografi ve radyasyon güvenliği
- Anestezi ve sedasyon

## 2. ADA Living Guidelines

Öncelik:
Çok yüksek

Kullanım:
Güncel önerilerin takip edilmesi gereken konular.

Özellikle:
- Oral kanser
- Akut dental ağrı

Not:
Living Guideline kaynakları yeni kanıtlar geldikçe güncellenebilir.

## 3. ADA Caries Guidelines

Konu:
Dental caries

Kaynaklar:
- Restorative caries treatments - 2023
- Nonrestorative caries treatments - 2018
- Caries prevention
- Caries detection and diagnosis

Kullanım:
Karies yönetimi, restoratif yaklaşım ve non-restoratif seçeneklerin değerlendirilmesi.

## 4. ADA Antibiotic Guideline

Konu:
Pulpal ve periapikal dental ağrı ve intraoral şişlik.

Kaynak:
ADA Antibiotics for Dental Pain and Swelling Guideline - 2019

Önem:
Antibiyotik gerekliliği değerlendirilirken yüksek öncelikli kaynak.

## 5. ADA Acute Dental Pain Guideline

Konu:
Akut dental ağrı.

Kaynak:
ADA Adult/Adolescent Acute Dental Pain Management Guideline

Not:
Living Guideline yaklaşımı nedeniyle güncel sürüm kontrol edilmelidir.

## 6. ADA Periodontitis Guideline

Konu:
Periodontal hastalık.

Kaynak:
ADA Nonsurgical Treatment of Chronic Periodontitis Clinical Practice Guideline

Temel konu:
Scaling and root planing ve yardımcı tedaviler.

## 7. ADA Oral Cancer Guideline

Konu:
Oral kanserin erken tespiti.

Özellikle:
- Cytology
- Vital staining
- Light-based adjuncts

Not:
Living Guideline olduğu için güncel öneriler kontrol edilmelidir.

## 8. ADA Radiography Resources

Konu:
Dental görüntüleme.

Özellikle:
- Hasta seçimi
- 2-D görüntüleme
- 3-D görüntüleme
- Radyasyon güvenliği

## RAG KURALI

Gemma klinik cevap üretirken:

1. Önce ilgili güvenilir klinik kaynağı bul.
2. Kaynaklar arasında güncel olanı tercih et.
3. Birden fazla güvenilir kaynak varsa karşılaştır.
4. Kaynaklar çelişiyorsa belirsizliği belirt.
5. Kaynakta bulunmayan bilgiyi kaynakta varmış gibi gösterme.
6. Kesin tanı veya tedavi kararı verme.
7. Hekimin klinik değerlendirmesini merkeze al.
8. Kritik bilgi eksikse hekime gerekli soruyu sor.
9. Rastgele blog, forum veya sosyal medya bilgisini klinik kanıt olarak kullanma.

