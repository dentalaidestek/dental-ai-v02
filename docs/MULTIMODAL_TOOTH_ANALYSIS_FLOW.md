# Dental AI — Multimodal Diş Analizi Ana Akışı

Bu belge panoramik, periapikal ve ağız içi fotoğraf analizlerinin ortak ve kalıcı ürün mantığını tanımlar. Yeni geliştirmeler bu akışı bozmamalıdır.

## 1. Modaliteye göre motor yönlendirme

Her görüntü yalnız kendi görüntü motor ailesine gönderilir:

- **Panoramik** → panoramik Vision48 / FDI ve ilgili panoramik motorlar.
- **Periapikal** → periapikal / PAI ve ilgili periapikal motorlar.
- **Ağız içi RGB fotoğraf** → AlphaDent, Daath, ResNet/Grad-CAM ve ilgili ağız içi motorlar.

Tek bir görüntü yüklendiğinde diğer modalitelerin motorları gereksiz yere çalıştırılmaz.

## 2. Görüntü motorlarının görevi

Görüntü motorları klinik AI/LLM değildir. Görevleri görüntüden bulgu çıkarmak ve mümkün olduğunda bulguyu ilgili FDI diş numarası/anatomik alan ile ilişkilendirmektir.

Görüntü motorlarının bulguları klinik AI çalıştırılmadan önce **Bulgular** bölümünde gösterilebilir. Kullanıcıya güven yüzdesi gösterilmez ve ürünün kabul edilen eşik değerinin altındaki bulgular gösterilmez.

## 3. Ortak arayüz mantığı

Panoramik, periapikal ve ağız içi görüntüler aynı temel arayüz mantığını kullanır:

**Bulgular | Tedavi | Görünüm**

- **Bulgular:** ilgili görüntü motorlarının ürettiği bulgular.
- **Tedavi:** hekim ilgili diş numarasını seçer ve `Analiz Et` ile klinik AI analizini başlatır.
- **Görünüm:** modaliteye uygun görüntüleme/işaretleme seçenekleri.

`Analiz Et` görüntü motorlarını bütün modaliteler için yeniden çalıştıran genel bir düğme değildir. Tedavi aşamasında seçilen diş için hazırlanmış klinik vaka paketini mevcut normal analiz akışına gönderir.

## 4. Birden fazla görüntünün birleştirilmesi

Aynı hastaya ait panoramik + periapikal + ağız içi fotoğraf gibi birden fazla modalite mevcutsa:

1. Her görüntü kendi ilgili motor ailesinde işlenir.
2. Sonuçlar mümkün olduğunda FDI diş numarası üzerinden eşleştirilir.
3. Aynı dişi destekleyen bulgular tek diş bağlamında bir araya getirilir.
4. Bir modalitenin sonucu diğer modalitenin motoruna gönderilmez.

Amaç birbirini destekleyen bağımsız görüntü bulgularını aynı klinik değerlendirmede kullanmaktır.

## 5. `Analiz Et` öncesi diş vaka paketi

Hekim örneğin **46 numaralı dişi** seçip `Analiz Et` dediğinde mevcut normal klinik AI analiz ekranına tek bir vaka paketi gönderilir. Paket mümkün olan tüm ilgili bilgileri içerir:

- 46 ile ilişkili panoramik motor bulguları,
- 46 ile ilişkili periapikal motor bulguları,
- 46 ile ilişkili ağız içi fotoğraf motor bulguları,
- diş şemasında 46 için kayıtlı mevcut durum,
- ilgili tedavi/geçmiş bilgileri mevcutsa bunlar,
- hekimin 46 için manuel girdiği bulgular ve klinik bilgiler.

Eksik modalite zorunlu değildir; yalnız mevcut kanıtlar pakete girer.

## 6. Klinik AI aşaması

Birleştirilmiş diş vaka paketi **mevcut normal Dental AI analiz akışına** gönderilir. Ayrı bir tedavi AI sistemi oluşturulmaz.

Normal analiz sistemi bu bağlamı kullanarak mevcut ürün kurallarına göre klinik değerlendirme, önceliklendirilmiş tedavi seçenekleri, diğer olası tanılar ve gerektiğinde hekime soruları üretir.

## 7. Temel ayrım

**Görüntü motorları = görüntüden kanıt/bulgu çıkarma.**

**Normal klinik AI = seçilen diş için bütün mevcut kanıtları, diş durumunu ve manuel klinik bilgileri birlikte değerlendirme.**

Bu ayrım panoramik, periapikal ve ağız içi görüntü sistemlerinin ana mimari kuralıdır.
