# Yorum gönderimi, yönetici bildirimi ve sayfa hızı

Goal: küçük ok düğmesi; inceleme gerektiren içerik için mevcut admin bildirim merkezi ve doğru kuyruk bağlantısı; ölçülen gereksiz başlangıç/sorgu yükünü azaltmak.

Architecture: Mevcut sosyal akış ve AdminNotice/RealtimeEvent altyapısı kullanılır. İçerik ve bildirim aynı işlemde saklanır; ağ yayını yalnızca commit ve yanıt tamamlandıktan sonra yapılır. Yeni servis veya ücretli plan yok.

Constraints: PR #254 üzerinde devam; main/deploy yapılmaz. İnceleme bekleyen görseller otomatik yayınlanmaz. Bildirimde gönderinin metni/görseli/kişisel veri bulunmaz. Aktif doğrulanmış admin erişimi korunur.

- [ ] Düğmeyi yazma alanının içine küçük koyu yuvarlak yukarı ok olarak yerleştir; metin etiketi yalnızca erişilebilir ad olsun.
- [ ] Yeni/düzenlenen pending içerik için tekilleştirilmiş admin bildirimi, karar sonrası kapatma, doğrudan içerik bağlantısı ve admin menüsünde bekleyen sayısı; rollback ve başarısız anlık teslim durumlarını test et.
- [ ] Kurulu şema zaten hazırsa soğuk başlangıçta tekrarlanan migration/backfill'i atla; eksikte mevcut geçişi çalıştırıp tekrar denetle. Şema okumasını toplu yap. Uzman dizinindeki kişi başına tekrar sorguları toplu sorgulara çevir.
- [ ] İlgili API/PostgreSQL/hız ve mevcut akış testleri, bağımsız inceleme ve GitHub Chromium kontrolü; PR ve raporu güncelle.

Observed: canlı son yeniden açılışta süreç başlangıcından hazır olmaya yaklaşık 58 saniye (28 saniye import + 30 saniye startup); free plan. HTTP latency metriği boş, mevcut CPU ve bellek baskısı gözlenmedi. Tüm gecikmelerin tek nedeninin bu olduğu iddia edilmez.
