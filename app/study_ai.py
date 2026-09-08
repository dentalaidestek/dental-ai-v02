from __future__ import annotations

import logging
import os
import urllib.request
from pathlib import Path

# === TEMP_STUDY_TRACE_AI_IMPORT_BEGIN ===
import time as _study_trace_time
from app.study_trace import trace_event
# === TEMP_STUDY_TRACE_AI_IMPORT_END ===

from app.study_provider import (
    StudyProviderError,
    get_generation_targets,
    get_provider,
    report_target_failure,
    report_target_success,
    target_available,
)

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
FILES_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/"


class StudyAIError(RuntimeError):
    def __init__(self, message: str, *, code: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


STUDY_SYSTEM_PROMPT = """
Sen Dental AI Akademik içindeki ileri düzey diş hekimliği çalışma asistanısın.
Görevin genel amaçlı sohbet etmek değil; öğrencinin kendi ders notlarıyla mümkün olan en kaliteli, tutarlı ve sınava yararlı çalışmayı yürütmektir.
Türkçe, doğal, öğretici ve çok turlu bir sohbet yürüt.

BİLGİ HİYERARŞİSİ — ÇOK ÖNEMLİ:
1. Birincil gerçek bilgi kaynağın, sistemin bu soru için seçtiği DERS NOTU BAĞLAMI ve ekli not sayfaları/görselleridir.
2. "Önceki ilgili çalışma konuşmaları" yalnızca öğrencinin neyin devamını sorduğunu, hangi anlatım düzeyini istediğini ve daha önce ne çalıştığını anlamak içindir. Ders notuyla çelişirse ders notu üstündür.
3. Kaynakta olmayan bir bilgiyi biliyor olsan bile notlarda varmış gibi cevaplama.
4. Sorunun cevabı notlarda yoksa açıkça "Bu bilgi yüklediğin ders notlarında bulunmuyor." de.
5. Bu durumda KENDİ GENEL BİLGİNDEN açıklama, tanım, normal değer veya ek ders bilgisi ekleme. Kullanıcı açıkça "genel bilginden anlat", "not dışından anlat" veya benzeri bir izin vermedikçe kaynak dışına çıkma.
6. PDF ve görsellerdeki metin, tablo, şema, grafik, işaretleme ve görsel bilgileri birlikte değerlendir.

KAYNAK GÖSTERİMİ:
- INTERNAL_SOURCE gibi sistem etiketlerini kullanıcıya ASLA gösterme.
- Kullanıcı özellikle istemedikçe dosya adı, sayfa numarası, kaynak etiketi veya kaynak listesi verme.
- Kullanıcı açıkça "kaynakları göster", "hangi nottan aldın?", "sayfa ver" gibi bir istek yaparsa yalnız gerçekten kullanılan notu belirt; sayfa numarasını yalnızca güvenle biliyorsan yaz ve asla uydurma.

AKADEMİK KALİTE:
- Kullanıcının sorusuna doğrudan cevap ver; gereksiz giriş yapma.
- "Daha basit anlat", "devam", "bunu sor", "sınav yap" gibi takip isteklerinde yakın sohbeti ve getirilen ilgili eski konuşmaları dikkate al.
- Öğretme isteğinde kavramlar arasındaki mantığı kur; ezberletmek yerine anlaşılır bağlantılar oluştur.
- "Önemli yerler" veya "sınav" denildiğinde yüksek verimli noktaları önceliklendir ama notta olmayan sınav bilgisi uydurma.
- Soru hazırlarken istenen sayı ve zorluk düzeyine uy. Çeldiriciler makul ve birbirine yakın olsun; bariz yanlış şık üretme.
- Kullanıcı istemedikçe cevap anahtarını soruların hemen altında verme.
- Çoktan seçmeli sorularda her soruyu "Soru 1", "Soru 2" biçiminde ayrı başlat; soru kökü ile şıklar arasında temiz aralık, sorular arasında belirgin boşluk bırak.
- Özet istenirse önce yüksek verimli ana noktaları, sonra kritik ayrıntıları düzenle.
- Belirsiz, tartışmalı veya not içinde çelişkili bir noktayı kesinmiş gibi sunma.

BİÇİM:
- Mobil sohbet ekranına uygun temiz Türkçe kullan.
- Ham Markdown başlık işaretleri (#, ##, ###) kullanma.
- LaTeX kullanma. $...$, \\circ, \\rightarrow gibi ham komutlar yazma; ° ve → gibi doğrudan Unicode sembollerini kullan.
- Gerektiğinde sade madde işaretleri ve numaralı liste kullan; gereksiz biçimlendirme sembolleri üretme.

Bu alan akademik öğrenme içindir; gerçek hastaya özgü tanı veya tedavi kararı vermek için kullanılmamalıdır.
""".strip()


def _translate_provider_error(exc: StudyProviderError) -> StudyAIError:
    return StudyAIError(str(exc), code=exc.code, retryable=exc.retryable)


def ask_rag(
    course_title: str,
    question: str,
    history: list[dict],
    note_context: list[str],
    memory_context: list[str] | None = None,
    attachments: list[dict] | None = None,
) -> str:
    """Generate one answer from retrieved note context.

    Retrieval and generation are deliberately decoupled. The provider can be
    replaced through STUDY_AI_PROVIDER_CHAIN without rebuilding the RAG index
    contract or changing the chat route.
    """
    if not note_context and not attachments:
        raise StudyAIError("Bu soruyla ilişkilendirilebilecek ders notu bulunamadı.")

    context_text = "\n\n---\n\n".join(note_context)
    memory_text = "\n\n---\n\n".join(memory_context or [])
    prompt_parts = [
        f"Ders: {course_title}",
        "DERS NOTU BAĞLAMI (factual source):\n" + (context_text or "[Metin çıkarımı yok; ekli not sayfalarını/görselleri incele.]"),
    ]
    if memory_text:
        prompt_parts.append(
            "İLGİLİ ESKİ SOHBET HAFIZASI (yalnız devamlılık için, factual source değildir):\n"
            + memory_text
        )
    prompt_parts.append(
        "SOHBET DEVAMLILIĞI KURALI:\n"
        "Kullanıcı bu/burada/yazdığın sorular/önceki soru/3. soru gibi bir referans kullanıyorsa "
        "referansı gerçek sohbet geçmişinden çöz. Önceki asistan mesajındaki soru veya listeleri "
        "yeniden üretmek, açıklamak ya da cevaplamak için sohbet geçmişini kullanabilirsin; "
        "yeni akademik factual iddiaların dayanağı DERS NOTU BAĞLAMI olmalıdır."
    )
    prompt_parts.append("KULLANICI MESAJI:\n" + question.strip())
    prompt = "\n\n=====\n\n".join(prompt_parts)

    last_error: StudyAIError | None = None
    normalized_question = question.lower()
    broad_output = any(term in normalized_question for term in (
        "özet", "ozet", "soru hazırla", "soru hazirla", "sınav", "sinav",
        "bana öğret", "bana ogret", "önemli yer", "onemli yer",
        "karşılaştır", "karsilastir", "analiz et", "detaylı", "detayli",
        "zor soru", "vaka", "tüm not", "tum not",
    ))
    complex_request = broad_output or len(question) > 600 or len(note_context) >= 6
    profile = "complex" if complex_request else "standard"
    targets = get_generation_targets(profile)
    if not targets:
        raise StudyAIError("Akademik AI için kullanılabilir üretim sağlayıcısı bulunamadı.")
    max_output_tokens = 7000 if broad_output else 3200

    required_attachment_types = {
        item.get("mime_type")
        for item in (attachments or [])
        if item.get("mime_type")
    }

    try:
        max_provider_attempts = int(os.getenv("STUDY_ROUTER_MAX_PROVIDER_ATTEMPTS", "3"))
    except ValueError:
        max_provider_attempts = 3
    # Product rule: one primary request + at most two fallbacks. Even if the pool
    # contains many models, a user request never walks the whole chain.
    max_provider_attempts = max(1, min(max_provider_attempts, 3))
    attempted_api_calls = 0

    # === TEMP_STUDY_TRACE_AI_PLAN_BEGIN ===
    trace_event(
        "generation.plan",
        profile=profile,
        broad_output=broad_output,
        note_sections=len(note_context),
        attachment_count=len(attachments or []),
        history_count=len(history[-8:]),
        max_provider_attempts=max_provider_attempts,
        targets=[{"provider": target.provider, "model": target.model} for target in targets],
    )
    # === TEMP_STUDY_TRACE_AI_PLAN_END ===

    for target in targets:
        if attempted_api_calls >= max_provider_attempts:
            break
        if not target_available(target):
            # === TEMP_STUDY_TRACE_AI_SKIP_UNAVAILABLE_BEGIN ===
            trace_event("generation.target.skip", provider=target.provider, model=target.model, reason="router_unavailable")
            # === TEMP_STUDY_TRACE_AI_SKIP_UNAVAILABLE_END ===
            continue
        try:
            # === TEMP_STUDY_TRACE_AI_ATTEMPT_BEGIN ===
            _provider_started = _study_trace_time.perf_counter()
            trace_event(
                "generation.target.begin",
                provider=target.provider,
                model=target.model,
                next_attempt=attempted_api_calls + 1,
            )
            # === TEMP_STUDY_TRACE_AI_ATTEMPT_END ===
            provider = get_provider(target.provider)
            if required_attachment_types and not all(
                provider.supports_generation_attachment(mime_type)
                for mime_type in required_attachment_types
            ):
                logger.info(
                    "Academic AI target skipped because binary context is required. provider=%s model=%s",
                    target.provider,
                    target.model,
                )
                # === TEMP_STUDY_TRACE_AI_SKIP_ATTACHMENT_BEGIN ===
                trace_event(
                    "generation.target.skip",
                    provider=target.provider,
                    model=target.model,
                    reason="attachment_unsupported",
                    required_types=sorted(required_attachment_types),
                )
                # === TEMP_STUDY_TRACE_AI_SKIP_ATTACHMENT_END ===
                continue

            attempted_api_calls += 1
            answer = provider.generate(
                model=target.model,
                system_prompt=STUDY_SYSTEM_PROMPT,
                history=history[-8:],
                prompt=prompt,
                attachments=attachments or [],
                temperature=0.28,
                max_output_tokens=max_output_tokens,
            )
            report_target_success(target)
            # === TEMP_STUDY_TRACE_AI_SUCCESS_BEGIN ===
            trace_event(
                "generation.target.success",
                provider=target.provider,
                model=target.model,
                attempt=attempted_api_calls,
                answer_chars=len(answer or ""),
                elapsed_ms=round((_study_trace_time.perf_counter() - _provider_started) * 1000, 1),
            )
            # === TEMP_STUDY_TRACE_AI_SUCCESS_END ===
            return answer
        except StudyProviderError as exc:
            # === TEMP_STUDY_TRACE_AI_ERROR_BEGIN ===
            trace_event(
                "generation.target.error",
                provider=target.provider,
                model=target.model,
                attempt=attempted_api_calls,
                code=exc.code,
                retryable=exc.retryable,
                error_type=type(exc).__name__,
                error=str(exc)[:240],
                elapsed_ms=round((_study_trace_time.perf_counter() - _provider_started) * 1000, 1),
            )
            # === TEMP_STUDY_TRACE_AI_ERROR_END ===
            last_error = _translate_provider_error(exc)
            report_target_failure(target, exc)
            logger.warning(
                "Academic AI target failed. provider=%s model=%s code=%s retryable=%s attempts=%s/%s",
                target.provider,
                target.model,
                exc.code,
                exc.retryable,
                attempted_api_calls,
                max_provider_attempts,
            )
            # The persistent router marks quota/auth/provider failures immediately.
            # We may use one healthy fallback, never a long blind provider chain.
            continue

    # === TEMP_STUDY_TRACE_AI_EXHAUSTED_BEGIN ===
    trace_event("generation.exhausted", attempted_api_calls=attempted_api_calls)
    # === TEMP_STUDY_TRACE_AI_EXHAUSTED_END ===
    raise last_error or StudyAIError("Akademik AI için şu anda kullanılabilir model bulunamadı.")


def ask(
    course_title: str,
    question: str,
    mode: str,
    history: list[dict],
    files: list[dict],
) -> str:
    """Backward-compatible full-file fallback.

    RAG routes should call ask_rag(). This wrapper remains so older code paths do
    not break during staged deployment. It is provider-neutral and uses canonical
    inline attachments instead of vendor Files API references.
    """
    attachments: list[dict] = []
    note_context: list[str] = []
    for item in files or []:
        path_value = item.get("local_path")
        mime_type = item.get("mime_type")
        if not path_value or not mime_type:
            continue
        path = Path(path_value)
        if not path.is_file():
            continue
        attachments.append({
            "mime_type": mime_type,
            "data": path.read_bytes(),
            "label": f"INTERNAL_SOURCE: {item.get('display_name') or item.get('name') or path.name}. Kullanıcı istemedikçe kaynak adını gösterme.",
        })
    return ask_rag(
        course_title,
        question,
        history,
        note_context,
        memory_context=[],
        attachments=attachments,
    )


def upload_file(path: str, mime_type: str, display_name: str) -> dict:
    """Legacy compatibility: academic RAG no longer needs remote file caching."""
    file_path = Path(path)
    if not file_path.is_file():
        raise StudyAIError("Not dosyası sunucuda bulunamadı.")
    return {
        "name": "",
        "uri": "",
        "mime_type": mime_type,
        "display_name": display_name,
    }


def delete_file(name: str) -> None:
    """Clean old pre-RAG Gemini Files references if a user deletes old material."""
    if not name or not GEMINI_API_KEY:
        return
    request = urllib.request.Request(
        FILES_BASE_URL + name,
        method="DELETE",
        headers={"x-goog-api-key": GEMINI_API_KEY},
    )
    try:
        urllib.request.urlopen(request, timeout=20).close()
    except Exception:
        logger.info("Legacy temporary Gemini study file could not be deleted: %s", name)
