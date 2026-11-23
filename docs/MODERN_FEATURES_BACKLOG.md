# MODERN ÖZELLİK BACKLOG — Dental AI (sosyal + AI esintili, ChatGPT-executable)

**Amaç:** Dünyanın en çok kullanılan sosyal medya ve AI uygulamalarında olan, Dental AI'ın işine yarayacak, sistemimizde olmayan özellikleri kodlanmış, doğrudan uygulanabilir iş kalemleri olarak bırakmak. Her kalemde **nerede / nasıl / kabul kriteri / test** vardır; sıralama P1 (önce) → P3.

**Çalışma kuralları (zaten repo standardı):** her backend ucu `app/mobile_*_api.py` veya `main.py`'de Türkçe hata mesajlarıyla; her davranış için node testi (`mobile/tests/<ad>.cjs`) + pytest (`tests/test_<ad>.py`); test kuralları gevşetilmez; idempotent gönderimler `request_key` makbuz deseniyle (ör. `mobile_academic_api.py`).

---

## P1 — Bu hafta yapılabilecekler

### P1-1: AI Akıllı Yanıtlar (mesaj kutusunda 3 öneri çipi)
- **Nerede:** web mantığı yok (yeni); backend `app/mobile_consultation_api.py` (mesaj akışının yanına `POST /api/mobile/v1/support/smart-replies` — gövde: `case_id`, `client_context:"latest_messages_hash"`); mobil `mobile/src/modernApi.ts` + `ModernScreens.tsx` CaseRoom composer'ının hemen üstü.
- **Nasıl:** son 8 mesajı (metadata düzeyi: rol+uzunluk+son içerik özeti, ham içerik gönderme — E2EE kurallarına dikkat) LLM'e ver, 3 kısa yanıt öner (≤120 karakter); rate limit (dakikada 6); yanıt çipine dokununca TextInput'a yerleşir, otomatik GÖNDERMEZ.
- **Kabul:** 3 çip ≤1.2 sn'de gelir; boş sohbette hiç çip yok; çip dokunuşu sadece metni doldurur; LLM hatasında sessiz (çip yok, hata bloğu yok).
- **Test:** `mobile/tests/smartReplies.cjs` (uç sözleşme, rate limit 429, boş sohbet boş liste) + `tests/test_mobile_smart_replies.py`.

### P1-2: Sesle dikte (mesaj kutusunda mikrofon)
- **Nerede:** `mobile/src/ModernScreens.tsx` composer (＋ ile ↑ arasına mic ikonu), mevcut ASR altyapısı `voice_exam` zincirinden (`/voice-exam` ASR uçları) yeniden kullanılır.
- **Nasıl:** basılı tut-kaydet (expo-av), bırak→ASR→metni imleç konumuna ekle; maxLength 4000 korunur; dikte metni **mesaj gönderim akışına karışmaz** (yalnız TextInput değeri).
- **Kabul:** izin reddinde Türkçe açıklama; kayıt iptali metin eklemez; E2EE/normal mesaj yolunda fark yok.
- **Test:** kaynak sözleşme testi `mobile/tests/chatDictation.cjs` (izin reddi metni, maxLength birleşimi) + cihaz kabulü kullanıcıda.

### P1-3: Program hatırlatma bildirimleri (randevu/ders/sınav öncesi)
- **Nerede:** backend zamanlayıcı (mevcut WorkJob altyapısı) → Expo push (`/push/devices` kayıtları mobilde var: `modernApi` push/devices); web karşılığı web-push VAPID (var).
- **Nasıl:** APPOINTMENT/EXAM başlangıcından 30 dk önce push ("Randevunuz 30 dakika sonra: {hasta}"); event silinirse hatırlatma iptal; kullanıcı push ayarı (NativePushSettings) "Hatırlatmalar" anahtarıyla kontrol eder.
- **Kabul:** saat dilimi doğru (TR), tekrar eden dersler her hafta tek bildirim; push izni kapalıysa sessiz atlanır.
- **Test:** `tests/test_program_reminders.py` (zamanlama, iptal, saat dilimi) + `mobile/tests/reminderSettings.cjs`.

### P1-4: Görsel çizim anotasyonu mobilde — ✅ TAMAMLANDI (2026-11-21, bu envanter kalemi kapanmıştır)
- **Düzeltme:** Kalem/çizim düzenleyicisi mobilde zaten mevcuttu (`NativeImageEditor.tsx`, commit `d5e03e18`): PanResponder stroke çizimi, renk/kalınlık araçları, Geri al/Temizle, `captureRef` ile görüntü+strokes JPEG q0.9 kompoziti, dosya adı web ile birebir `isaretlenmis-gorsel.jpg`. Eklenen parite cilası: (1) `✎ İşaretle` artık web annotation-launch gibi doğrudan çizim editörünü açar (not anotasyonu `✎ Not` girişine taşındı, aynı delege uç), (2) kompozit çözünürlük cap'ı web `EDITOR_MAX_DIMENSION` ile eşitlendi (1600→4096, `chatFiles.ts fitChatImage`), (3) `mobile/tests/chatDrawAnnotation.cjs` ile web sözleşme zinciri (composite → `sendChatImage(reply_to_message_id)` → `client_message_id`) test altına alındı. Süit 985/985 yeşil.

---

## P2 — Kısa vade (sosyal + AI genişleme)

### P2-1: Kısa video (Reels benzeri) — Dental Akış dikey video akışı
- **Nerede:** backend `main.py` posts router (post type VIDEO + WorkJob transcode + poster üretimi); mobil `socialApi.ts` + `NativeSocialMediaViewer.tsx` (tam ekran dikey swipe pager, sessiz otomatik oynatma); web `dental-akis` video oynatıcı.
- **Nasıl:** ≤60 sn, ≤50 MB; **hasta verisi maskeleme kontrolü zorunlu** (yüz/röntgen üstü veri — yayın öncesi otomatik uyarı + rapor akışı); transcode arızasında kullanıcıya Türkçe durum.
- **Kabul:** dikey pager, dokun-duraklat, rapor butonu çalışır; transcode başarısız postu görünmez yapar ama sahibine hata gösterir.
- **Test:** `tests/test_video_posts.py` (boyut/süre limitleri, transcode WorkJob, maskeleme uyarısı) + `mobile/tests/videoPost.cjs`.

### P2-2: Stories (24 saat geçici vaka paylaşımları)
- **Nerede:** yeni uç `posts/stories` (TTL 24s, arşiv yok — KVKK: otomatik silme WorkGarbage'a bağlanır); mobil Dental Akış üstünde story şeridi; görüntüleme listesi sahibine.
- **Kabul:** TTL sonrası içeren+meta dahil silinir; ekran görüntüsü alma bilgilendirmesi (mümkünse) + rapor.
- **Test:** `tests/test_stories_ttl.py` + `mobile/tests/stories.cjs`.

### P2-3: Yorum thread'leri + @bahsetme
- **Nerede:** posts yorum modeline `parent_id` + mention parse (`@kullanıcı`); bildirim mention'a bağlanır (`/notifications`); mobil `NativeSocialMediaViewer` yorum paneli.
- **Kabul:** 2 derinlik thread; mention'da profil linki; bildirim tıklayınca ilgili gönderi açılır.
- **Test:** `tests/test_comment_threads.py` + `mobile/tests/commentThread.cjs`.

### P2-4: Before/After galerisi (tedavi öncesi/sonrası)
- **Nerede:** tedavi kaydı modeline eşleşen görsel çifti (`before_media_id`/`after_media_id`); hasta profilinde galeri sekmesi; uzman onaylıysa Dental Akış "vaka paylaşımı" olarak (hasta rızası alanı zorunlu).
- **Kabul:** rıza olmadan sosyal paylaşım butonu görünmez; çift görsel tek kayıt olarak silinir.
- **Test:** `tests/test_treatment_gallery.py` + `mobile/tests/beforeAfter.cjs`.

### P2-5: AI akıllı akış sıralaması
- **Nerede:** Dental Akış feed'i (şu an kronolojik) → skorlama: branş eşleşmesi + etkileşim geçmişi + tazelik; **yalnız kendi davranış verisi** (üçüncü parti yok); "Tümü/Keşfet" sekmeleri korunur.
- **Kabul:** skorlama deterministik test edilebilir (birim); kullanıcı "kronolojik" sıralama tercih edebilmeli (ayar anahtarı).
- **Test:** `tests/test_feed_ranking.py`.

### P2-6: Deep linking
- **Nerede:** `expo-linking` + universal links (`dentalai.tr/app/...`); hedefler: uzman profili, vaka odası, analiz sonucu, ders; kimlik doğrulaması sonrası hedefe yönlendirme.
- **Kabul:** oturum yoksa login→hedef devamı; geçersiz/erişimsiz link Türkçe boş durum.
- **Test:** `mobile/tests/deepLink.cjs` (rota çözümleme tablosu).

---

## P3 — Stratejik (planlanmalı)

### P3-1: Teledanışmanlık görüntülü görüşme
- WebRTC (LiveKit/Daily tarzı yönetilen hizmet veya öz-barındırma); vaka odasında "Görüntülü Danışma" butonu; kayıt rıza akışı + mediko-legal onay metni (KVKK + klinik sorumluluk); randevu tabanlı planlama program'a yazar.
- **Kabul:** katılım linki sadece vaka taraflarına; bağlantı kalite göstergesi; çağrı sonrası otomatik vaka notu.

### P3-2: AI RAG arama (notlar + vakalar birleşik semantik arama)
- Mevcut akademik semantik altyapı (academic-semantic CI zinciri) genişletilir: "kendi vakalarım + ders notlarım" arasında soru→kaynak arama; yanıt yalnız kullanıcının erişim kapsamındaki kaynaklardan.
- **Kabul:** kapsam dışı kayıt asla dönmez (test: iki hesap izolasyonu); kaynak satır içi alıntılı.

### P3-3: Gönderi taslakları + zamanlanmış paylaşım
- Posts `scheduled_at` (WorkJob yayınlama); mobil taslak paneli.

### P3-4: AI analiz sonucu sesli özet (TTS)
- Sonuç ekranında "Dinle" (TTS altyapısı ile); erişilebilirlik + hızlı kullanım.

### P3-5: Çoklu dil altyapısı (TR dışı)
- i18n katmanı; tüm TR string'ler anahtarlanır (büyük refaktör — yalnız ihtiyaç doğrulandığında).

---

## Bilinçli olarak YAPILMAYACAKLAR (kapsam dışı notu)
- Genel amaçlı sosyal API'ler (Instagram/Twitter paylaşım botları) — hasta verisi riski; yalnız uygulama içi paylaşım.
- Üçüncü parti reklam/izleme SDK'ları — KVKK + klinik güven duruşu.
- Otomatik AI tanı raporu paylaşımı (hastaya doğrudan) — hekim onayı olmadan çıktı gitmez (mevcut kural korunur).
