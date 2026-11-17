# Uzman desteği — native/web parity ve inbox güvenilirliği (2026-11-17)

## Web-first inceleme

Değişikliklerden önce mevcut dalın web akışı incelendi:

- `app/templates/messages.html`: Mesajlar, arama, Tümü/Okunmamış/Bekleyen/Kaçırılan/Geçmiş filtreleri, gerçek zamanlı satır güncellemesi.
- `app/templates/_message_row.html`: Webde gösterilen Türkçe durum etiketi, okunmamış sayısı, son mesaj ve zaman.
- `app/templates/expert_case_room.html`: Katılımcı kimliği, vaka durumu, mesaj geçmişi, okundu bilgisi ve bağlantı koptuğunda catch-up.
- `app/main.py`: `_consultation_display_status`, `_consultation_inbox_rows`, kullanıcıya özel silme/geri yükleme ve okundu cursor'u.
- `app/mobile_api.py`: Native inbox sayfalaması, son mesaj, unread count ve vaka/mesaj sahiplik denetimleri.
- `mobile/src/ModernScreens.tsx`, `mobile/src/modernApi.ts`, `mobile/src/consultationRealtime.ts`: Native filtreler, realtime olayları, mesaj cursor'u ve okundu işaretleme.

## Bulunan ve düzeltilen farklar

1. **Android typecheck kaynak hatası:** `Consultations` bileşeni `userId` değişkenini `applyConsultationInboxEvent` çağrısında kullanıyordu fakat prop olarak almıyordu. Hem alt sekme hem stack navigasyon giriş noktası artık oturumdaki `user.id` değerini geçiriyor. Bu, statik kaynak incelemesinde belirlenen TypeScript ad çözümleme hatasıdır; GitHub runner başlamadığı için tam `tsc` sonucu henüz alınamadı.
2. **Durum metinleri ve filtre eşitliği:** Native inbox ham enum değerlerini gösteriyor, web ise kullanıcı rolüne ve deadline'a göre `Yeni Talep`, `Bekleyen`, `Aktif`, `Kaçırılan`, `Geçmiş` gibi etiketler gösteriyordu. Mobile API artık webdeki `_consultation_display_status` helper'ını kullanıp `status_key` ve `status_label` döndürüyor. Native arama/filtre/sıralama kanonik anahtarı, kart etiketi Türkçe metni kullanıyor; eski API için raw status fallback'i korundu.
3. **Geri yüklenmiş sohbetin native inbox'ta kaybolması:** Eski mobile query herhangi bir tarihsel `deleted_at` satırı bulunan vakayı gizliyordu. Web canonical state ise en yeni inbox-state satırının silinmiş olup olmadığına bakar. Duplicate state'lerde son satır geri yüklenmişse mobile artık sohbeti gösteriyor; yalnızca en yeni state silinmişse gizliyor.
4. **Duplicate state ile yanlış unread sayısı:** Native, duplicate state kayıtlarından SQL sırası belirsiz tek bir satırı seçiyordu. Web en yüksek `last_read_at` değerini birleştirir. Mobile artık sayfa başına gruplanmış `MAX(last_read_at)` kullanıyor; unread sorgusundaki korelasyon da aynı maksimumu kullanıyor.
5. **Sahiplik izolasyonu:** En yeni silme durumu ve read cursor yalnızca oturumdaki kullanıcıya ait state satırlarından hesaplanıyor. Başka hesabın silme kaydı mevcut kullanıcının görüşmesini gizleyemez.

## Regresyon kapsamı

- `mobile/tests/consultationRealtime.cjs`: inbox bileşeninin `userId` prop'u ve her iki navigation giriş noktasının kimliği geçirmesi.
- `tests/test_mobile_query_efficiency.py`: tarihsel deleted + yeni restored duplicate state, en yüksek read timestamp, başka hesabın state izolasyonu, web durum etiketi ve bounded query budget.
- Mevcut mesaj event dedupe, outgoing/incoming unread artışı, CASE_READ ve message cursor testleri korunuyor.

Query budget testleri artık vaka inbox sayfası için en fazla 5 sabit SELECT round-trip kabul ediyor; kayıt sayısı arttıkça vaka başına sorgu oluşmaması şartı korunuyor. Bu bir 60.000 kullanıcı kapasite kanıtı değildir; gerçek PostgreSQL yük testi hâlâ gereklidir.

## CI başlangıç kanıtı

Bu çalışmanın başlangıç HEAD'i `0108f5be3d13e52f9f96fab68231f3163ce217ab` idi. En son bağlı workflow run'ları:

- Android CI: `44046300667` — typecheck ve beta-apk job'ları failure.
- Security recovery: `44046300586` — security job failure.
- Admin security: `44046300626` — security job failure.
- Expert social: `44046300478` — regression job failure.
- Voice regression: `44046300477` — voice job failure.

Altı ilgili job için adım listeleri boş; log indirmeleri `BlobNotFound 404`, artifact listeleri boş. Dolayısıyla npm/tsc, pytest, Gradle veya beta testleri başlamamış. Kaynakta yukarıdaki TypeScript hatası bulunup düzeltildi; fakat Security workflow'larının kod testleri runner başlamadığı için hâlâ doğrulanamadı. Runner/account/billing kök nedeni mevcut GitHub kayıtlarından görünmüyor.

## Dağıtım sınırı

PR #257 açık ve Draft kalır. Main merge, canlı deploy, migration, APK/IPA yayını ve klinik kayıt değişikliği yapılmadı.
