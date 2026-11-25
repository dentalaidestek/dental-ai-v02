// Ana sayfa ⋮ penceresinden açılan bilgi sayfaları: hakkımızda, iletişim,
// kullanım+topluluk kuralları ve gizlilik özeti. Web /legal metinleriyle
// uyumlu düz metin versiyonu (app/legal_texts.py · 2026.11.25).
export type LegalSection={heading:string;paragraphs:string[]};
export type LegalDoc={key:string;title:string;intro:string;sections:LegalSection[];footnote?:string};

export const LEGAL_DOCS:Record<string,LegalDoc>={
 about:{
  key:"about",title:"Hakkımızda",
  intro:"DENTAL AI, diş hekimliği alanında klinik değerlendirme süreçlerini desteklemek için geliştirilen yapay zekâ destekli bir klinik karar destek platformudur.",
  sections:[
   {heading:"Ne sunuyoruz?",paragraphs:[
    "AI Analiz — Röntgen ve klinik görüntülerin destek amaçlı yapay zekâ değerlendirmesi; hastaya bağlanan analiz geçmişi.",
    "Hasta Yönetimi ve Diş Şeması — Hasta kayıtları, etkileşimli diş şeması, tedavi geçmişi ve klinik notlar.",
    "Sesli Muayene — Onaylı görüşme kaydının yazıya çevrilmesi ve klinik bilgilerle desteklenen değerlendirme.",
    "Uzmandan Destek — Doğrulanmış uzmanlarla vaka danışmanlığı ve güvenli vaka görüşmesi.",
    "Akademik AI — Kendi ders notlarınız ve kaynaklarınız üzerinden eğitim amaçlı soru-cevap.",
    "Foto Fikir — Sosyal medya içerik fikirleri, slayt metinleri ve görsel üretimi.",
    "Dental Akış — Mesleki paylaşım ve güncel akış.",
   ]},
  ],
  footnote:"Önemli: Platform çıktıları kesin tanı veya tedavi kararı değildir; hekim muayenesinin veya profesyonel klinik değerlendirmenin yerine geçmez. Nihai klinik karar, hastayı değerlendiren yetkili sağlık mesleği mensubuna aittir.",
 },
 contact:{
  key:"contact",title:"İletişim",
  intro:"Hesap, teknik destek, gizlilik, topluluk kuralları veya platform kullanımıyla ilgili her konuda aşağıdaki kanalları kullanabilirsiniz.",
  sections:[
   {heading:"Uygulama içi destek talebi (en hızlı kanal)",paragraphs:[
    "Ana sayfa menüsünden veya hasta profilindeki “Destek Talebi Oluştur” seçeneğinden destek ekibine doğrudan ulaşabilirsiniz.",
    "Vaka ile ilgili bir bildirimdeyseniz, ilgili görüşmenin kartındaki “Sorun Bildir” seçeneğini kullanmanız incelemeyi hızlandırır.",
   ]},
   {heading:"E-posta",paragraphs:["destek@dentalai.tr"]},
   {heading:"Gizlilik ve bildirimler",paragraphs:[
    "Yapılan bildirimlerin içeriği destek inceleme ekibi dışında ilgili kişiyle paylaşılmaz. Kişisel veri ve gizlilik konulu başvurularda talebinizi açık şekilde belirtmeniz değerlendirme sürecini kolaylaştırır.",
   ]},
  ],
 },
 rules:{
  key:"rules",title:"Kullanım ve Topluluk Kuralları",
  intro:"Bu kurallar vaka görüşmeleri, destek talepleri, Dental Akış paylaşımları ve platformun tüm iletişim alanlarında beklenen davranışları düzenler.",
  sections:[
   {heading:"Birbirimize saygı",paragraphs:[
    "Hakaret, küfür, aşağılama, alay, dışlama ve kaba üslup yasaktır. Tıbbi tartışmalar mesleki gerekçelerle, anlaşılır ve nazik bir dilde yürütülür; yanlış bilgiyi düzeltirken de saygılı dil kullanılır.",
   ]},
   {heading:"Yasak içerik ve davranışlar",paragraphs:[
    "Taciz, tehdit, şantaj veya ısrarlı özel mesaj baskısı; hakaret, küfür, müstehcen ifade ve nefret söylemi; cinsel içerik veya uygunsuz görsel paylaşımı; spam, zincir mesaj, reklam ve izinsiz ticari içerik; sahte hesap ve kimlik taklidi; başkasının hesabına veya verilerine erişme girişimi; yanıltıcı tıbbi iddialar ve dolandırıcılık çabaları platformun hiçbir alanında kabul edilmez.",
   ]},
   {heading:"Hasta verisi ve klinik paylaşım",paragraphs:[
    "Vaka paylaşımlarında hastanın kimliğine ilişkin bilgiler (ad-soyad, TC kimlik, telefon, adres, tam yüz fotoğrafı gibi) paylaşılmamalıdır. Klinik görseller yalnızca tedavi ve danışmanlık amacıyla, hastanın bilgisi ve hukuki onayı çerçevesinde paylaşılır.",
   ]},
   {heading:"İçerik üretimi ve yayımlama",paragraphs:[
    "Foto Fikir ve benzeri araçlardan üretilen içeriklerin yayımlanması kullanıcıya aittir; tıbbi iddiaların, hasta onaylarının ve reklam-mevzuat kurallarının uygunluğu kullanıcı sorumluluğundadır. Yanıltıcı tedavi vaadi veya tanı garantisi içeren içerik yayımlanamaz.",
   ]},
   {heading:"İhlalleri bildirme",paragraphs:[
    "Görüşme listesinde ilgili kartın menüsünden “Sorun Bildir” seçeneğini kullanın; sebep olarak Taciz, Hakaret veya Küfür, Spam, Uygunsuz Davranış veya Diğer seçilir. İsterseniz uygulama içi Destek Talepleri ekranından da ulaşabilirsiniz. Bildirimin içeriği destek inceleme ekibi dışında ilgili kişiyle paylaşılmaz.",
   ]},
   {heading:"İnceleme ve yaptırımlar",paragraphs:[
    "Bildirimler ve otomatik güvenlik sinyalleri ekiple incelenir. Sonuca göre içerik kaldırma, uyarı, karşılıklı mesajlaşmanın kapatılması, özellik kısıtlaması, geçici askıya alma ve ağır veya tekrarlayan ihlallerde hesabın kapatılması uygulanabilir. Değerlendirilen kullanıcı, durumu Destek Talepleri üzerinden açıklama hakkına sahiptir.",
   ]},
  ],
  footnote:"Uygulama koşullarının tamamı için web sitemizdeki “Üyelik ve Kullanım Koşulları” ve “Topluluk ve İletişim Kuralları” metinlerine bakabilirsiniz.",
 },
 privacy:{
  key:"privacy",title:"Gizlilik",
  intro:"DENTAL AI kullanımında kişisel veriler yalnızca hizmetin sunulması için gerekli ölçüde işlenir.",
  sections:[
   {heading:"Klinik veriler ve hastalarınız",paragraphs:[
    "Hasta ve klinik veriler yüksek gizlilik gerektirir. Yalnızca mesleki ve hukuki olarak işlemeye yetkili olduğunuz verileri sisteme yükleyebilirsiniz; hasta kayıtlarınıza erişim yetkisiz kullanıcılara kapalıdır.",
   ]},
   {heading:"Mesajlar, ekler ve görüşmeler",paragraphs:[
    "Vaka görüşmesi ve destek talebi mesajları ile görsel, PDF ve ses ekleri yalnızca hizmet sunulmak amacıyla saklanır ve yalnızca görüşmenin tarafları ile görüntülenebilir. Listeden kaldırdığınız bir görüşme, size sunulan kısa geri yükleme süresi boyunca kurtarılabilir.",
   ]},
   {heading:"Sesli muayene",paragraphs:[
    "Ses bölümleri yazıya çevrilene kadar geçici olarak tutulur; ham ses ve tam konuşma dökümü hasta dosyasına otomatik yazılmaz. Yalnızca sizin seçip onayladığınız alanlar kaydedilir.",
   ]},
   {heading:"Güvenlik ve saklama",paragraphs:[
    "Şifreler uygun kriptografik yöntemlerle korunur; yetkisiz erişime karşı teknik ve idari tedbirler uygulanır. Veriler işleme amacı süresince ve mevzuatın öngördüğü sürelerde muhafaza edilir, amacı kalkınca silinir veya anonim hale getirilir. Barındırma, e-posta ve yapay zekâ altyapısı sağlayıcılarıyla paylaşım yürürlükteki mevzuata uygun yapılır.",
   ]},
  ],
  footnote:"Detaylı metinler: web sitemizdeki “Gizlilik Politikası” ve “KVKK Aydınlatma Metni”. Soru ve talepleriniz için İletişim sayfasındaki kanalları kullanabilirsiniz.",
 },
};
