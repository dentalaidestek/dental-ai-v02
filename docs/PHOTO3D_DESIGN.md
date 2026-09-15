# Dental AI — ağız içi fotoğraftan 3D görselleştirme

Amaç, CBCT'si veya intraoral tarayıcısı olmayan kliniklerde hasta iletişimini güçlendiren bir 3D sunum katmanı sağlamaktır.

- Tek fotoğraf: `single_view_photo_relief`; parlaklık/kenar geometrisinden renkli 3D yüzey/nokta bulutu üretir.
- Çok açılı 2-8 fotoğraf: ORB + Essential Matrix + pose recovery + triangulation ile `multiview_sparse_sfm` oluşturmayı dener.
- Çoklu görünüm yetersizse otomatik tek-fotoğraf relief'e düşer.
- Çıktı Three.js ile döndürülebilir/zoom yapılabilir.

Bu modül kendisini **CBCT**, gerçek medikal hacim, metrik 3D tarama veya tanısal 3D rekonstrüksiyon olarak tanıtmaz. API çıktısında `diagnostic=false` ve `medical_volume=false` zorunludur.

Geliştirme kontrol UI'si: `/viewer` → “Fotoğraftan 3D”. Production deploy bu dalda yapılmaz.
