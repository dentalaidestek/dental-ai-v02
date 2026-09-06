import base64
import json
import logging
import os
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
STUDY_GEMINI_MODEL = os.getenv("STUDY_GEMINI_MODEL", "gemini-3.8-flash")
STUDY_GEMINI_FALLBACK_MODEL = os.getenv("STUDY_GEMINI_FALLBACK_MODEL", "gemini-3.7-flash")
UPLOAD_START_URL = "https://generativelanguage.googleapis.com/upload/v1beta/files"
FILES_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/"
TIMEOUT_SECONDS = int(os.getenv("STUDY_GEMINI_TIMEOUT_SECONDS", "180"))
MAX_ATTEMPTS = max(1, int(os.getenv("STUDY_GEMINI_MAX_ATTEMPTS", "3")))
RETRYABLE_HTTP_CODES = {408, 429, 500, 502, 503, 504}
# Small/medium course material is sent inline. This avoids a second remote upload
# dependency and is particularly reliable for ordinary lecture PDFs.
INLINE_SINGLE_MAX_BYTES = int(os.getenv("STUDY_INLINE_SINGLE_MAX_BYTES", str(8 * 1024 * 1024)))
INLINE_TOTAL_MAX_BYTES = int(os.getenv("STUDY_INLINE_TOTAL_MAX_BYTES", str(14 * 1024 * 1024)))


class StudyAIError(RuntimeError):
    def __init__(self, message: str, *, code: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


def _require_key():
    if not GEMINI_API_KEY:
        raise StudyAIError("GEMINI_API_KEY tanımlı değil. Render Environment Variables bölümünü kontrol edin.")


def _safe_http_message(code: int) -> str:
    if code == 429:
        return "Akademik AI kullanım limiti geçici olarak dolu. Lütfen kısa süre sonra tekrar deneyin."
    if code in {500, 502, 503, 504}:
        return "Akademik AI servisi geçici olarak yanıt veremiyor. Lütfen tekrar deneyin."
    if code == 408:
        return "Akademik AI isteği zaman aşımına uğradı. Lütfen tekrar deneyin."
    if code in {401, 403}:
        return "Gemini API yetkilendirmesi başarısız. Sunucu yapılandırmasını kontrol edin."
    if code == 400:
        return "Akademik AI isteği geçersiz bulundu. Ders notlarını veya soruyu kontrol edin."
    if code == 404:
        return "Akademik AI modeli bulunamadı. Sunucu model ayarını kontrol edin."
    return f"Akademik AI isteği başarısız oldu (HTTP {code})."


def _request_json(request: urllib.request.Request, timeout: int = TIMEOUT_SECONDS):
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return json.loads(body), response.headers
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        logger.warning("Study Gemini HTTP %s: %s", exc.code, body[:2200])
        raise StudyAIError(
            _safe_http_message(exc.code),
            code=exc.code,
            retryable=exc.code in RETRYABLE_HTTP_CODES,
        ) from exc
    except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        logger.warning("Study Gemini connection error: %r", exc)
        raise StudyAIError(
            "Akademik AI bağlantısında geçici bir sorun oluştu. Lütfen tekrar deneyin.",
            retryable=True,
        ) from exc
    except json.JSONDecodeError as exc:
        raise StudyAIError("Akademik AI servis cevabı okunamadı. Lütfen tekrar deneyin.") from exc


def _with_retries(build_request, *, timeout=TIMEOUT_SECONDS):
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return _request_json(build_request(), timeout=timeout)
        except StudyAIError as exc:
            last_error = exc
            if not exc.retryable or attempt >= MAX_ATTEMPTS:
                raise
            time.sleep(min(4, 2 ** (attempt - 1)))
    raise last_error or StudyAIError("Akademik AI isteği tamamlanamadı.")


def upload_file(path: str, mime_type: str, display_name: str) -> dict:
    """Upload one private local study file to Gemini Files API with retries."""
    _require_key()
    file_path = Path(path)
    if not file_path.is_file():
        raise StudyAIError("Not dosyası sunucuda bulunamadı.")

    size = file_path.stat().st_size
    if size <= 0:
        raise StudyAIError("Not dosyası boş.")
    if mime_type == "application/pdf" and size > 50 * 1024 * 1024:
        raise StudyAIError("PDF Gemini için 50 MB sınırını aşıyor.")

    start_body = json.dumps({"file": {"display_name": display_name}}, ensure_ascii=False).encode("utf-8")
    upload_url = None
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        start_request = urllib.request.Request(
            UPLOAD_START_URL,
            data=start_body,
            method="POST",
            headers={
                "x-goog-api-key": GEMINI_API_KEY,
                "X-Goog-Upload-Protocol": "resumable",
                "X-Goog-Upload-Command": "start",
                "X-Goog-Upload-Header-Content-Length": str(size),
                "X-Goog-Upload-Header-Content-Type": mime_type,
                "Content-Type": "application/json; charset=utf-8",
            },
        )
        try:
            with urllib.request.urlopen(start_request, timeout=TIMEOUT_SECONDS) as response:
                upload_url = response.headers.get("X-Goog-Upload-URL") or response.headers.get("x-goog-upload-url")
            if upload_url:
                break
            last_error = StudyAIError("Gemini dosya yükleme adresi alınamadı.")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            logger.warning("Study file upload start HTTP %s: %s", exc.code, body[:1800])
            last_error = StudyAIError(_safe_http_message(exc.code), code=exc.code, retryable=exc.code in RETRYABLE_HTTP_CODES)
            if exc.code not in RETRYABLE_HTTP_CODES:
                raise last_error from exc
        except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
            logger.warning("Study file upload start connection error: %r", exc)
            last_error = StudyAIError("Not dosyası Gemini'ye hazırlanırken bağlantı sorunu oluştu.", retryable=True)
        if attempt < MAX_ATTEMPTS:
            time.sleep(min(4, 2 ** (attempt - 1)))
    if not upload_url:
        raise last_error or StudyAIError("Gemini dosya yükleme adresi alınamadı.")

    data = file_path.read_bytes()
    def build_upload_request():
        return urllib.request.Request(
            upload_url,
            data=data,
            method="POST",
            headers={
                "Content-Length": str(size),
                "X-Goog-Upload-Offset": "0",
                "X-Goog-Upload-Command": "upload, finalize",
                "Content-Type": mime_type,
            },
        )
    result, _ = _with_retries(build_upload_request)
    file_info = result.get("file") or {}
    name = file_info.get("name")
    uri = file_info.get("uri")
    if not name or not uri:
        raise StudyAIError("Gemini dosya yükleme cevabı eksik.")

    # PDFs can take a little while to become ACTIVE. Give them up to ~60 s.
    state = ((file_info.get("state") or {}).get("name") if isinstance(file_info.get("state"), dict) else file_info.get("state"))
    for _ in range(30):
        state_text = str(state or "").upper()
        if "FAILED" in state_text:
            raise StudyAIError("Gemini not dosyasını işleyemedi.")
        if not state_text or "ACTIVE" in state_text or "PROCESSING" not in state_text:
            return {"name": name, "uri": uri, "mime_type": mime_type}
        time.sleep(2)
        get_request = urllib.request.Request(
            FILES_BASE_URL + name,
            method="GET",
            headers={"x-goog-api-key": GEMINI_API_KEY},
        )
        fetched, _ = _request_json(get_request, timeout=30)
        uri = fetched.get("uri") or uri
        state = fetched.get("state")
    raise StudyAIError("Not dosyası AI tarafından hazırlanırken beklenenden uzun sürdü. Lütfen tekrar deneyin.", retryable=True)


def delete_file(name: str) -> None:
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
        logger.info("Temporary Gemini study file could not be deleted: %s", name)


STUDY_SYSTEM_PROMPT = """
Sen Dental AI Akademik içindeki güçlü bir diş hekimliği çalışma asistanısın.
Türkçe, doğal, öğretici ve çok turlu bir sohbet yürüt. Kullanıcının önceki sorularını bağlam içinde hatırla.

KAYNAK KURALI — ÇOK ÖNEMLİ:
- YALNIZCA bu derse eklenmiş PDF ve görsel notları bilgi kaynağı olarak kullan.
- Kaynaklarda olmayan bir bilgiyi biliyor olsan bile kaynaklarda varmış gibi cevaplama.
- Sorunun cevabı notlarda yoksa açıkça "Bu bilgi yüklediğin ders notlarında bulunmuyor." de.
- PDF ve görsellerdeki metin, tablo, şema, grafik ve görsel bilgileri birlikte değerlendir.
- Kullanıcı özellikle istemedikçe dosya adı, sayfa numarası, [Kaynak: ...] etiketi veya kaynak listesi gösterme.
- Kullanıcı açıkça “kaynakları göster”, “hangi nottan aldın?”, “sayfa ver” gibi bir istek yaparsa yalnızca gerçekten kullandığın kaynağı belirt; sayfa numarasını yalnızca güvenle belirleyebiliyorsan ekle ve asla uydurma.

SOHBET DAVRANIŞI:
- Kullanıcının sorusuna doğrudan cevap ver; gereksiz girişlerle uzatma.
- "Daha basit anlat", "devam", "bunu sor", "sınav yap" gibi takip isteklerinde önceki konuşmayı dikkate al.
- Öğretme isteğinde mantığı kur, gerekirse örnekle, ezber yerine anlamayı hedefle.
- Soru hazırlarken istenen sayı ve zorluk düzeyine uy. Kullanıcı istemedikçe cevap anahtarını soruların hemen altında verme.
- Çoktan seçmeli soru hazırlarken her soruyu “Soru 1”, “Soru 2” biçiminde ayrı bir başlıkla başlat; soru kökü ve şıkları arasında temiz satır aralığı kullan, soruların arasına boşluk bırak.
- Özet istenirse önce yüksek verimli ana noktaları, sonra kritik ayrıntıları ver.
- Yanlış veya belirsiz gördüğün bilgiyi kesinmiş gibi sunma.
- Yanıtı mobil sohbet ekranında okunacak temiz Türkçe ile yaz. Başlıkların başına #, ##, ### gibi Markdown işaretleri koyma.
- LaTeX kullanma. $...$, \\circ, \\rightarrow gibi ham komutlar yazma; derece için °, ok için → gibi doğrudan Unicode sembollerini kullan.
- Gerektiğinde sade madde işaretleri veya numaralı liste kullan; gereksiz biçimlendirme sembolleri üretme.

Bu alan akademik öğrenme içindir; gerçek hastaya özgü tanı veya tedavi kararı vermek için kullanılmamalıdır.
""".strip()


def _model_url(model: str) -> str:
    return f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _inline_part(path: str, mime_type: str) -> dict:
    data = Path(path).read_bytes()
    return {
        "inline_data": {
            "mime_type": mime_type,
            "data": base64.b64encode(data).decode("ascii"),
        }
    }


def _build_payload(course_title: str, question: str, history: list[dict], files: list[dict], *, force_inline: bool = False) -> bytes:
    latest_prompt = (
        f"Ders: {course_title}\n\n"
        f"Kullanıcı mesajı:\n{question.strip()}"
    )

    contents = []
    for item in history[-12:]:
        role = "model" if item.get("role") == "ASSISTANT" else "user"
        text = (item.get("content") or "").strip()
        if text:
            contents.append({"role": role, "parts": [{"text": text}]})

    latest_parts = [{"text": latest_prompt}]
    for item in files:
        mime_type = item.get("mime_type")
        local_path = item.get("local_path")
        uri = item.get("uri")
        use_inline = force_inline or item.get("inline") or not uri
        if use_inline and local_path and mime_type:
            latest_parts.append(_inline_part(local_path, mime_type))
        elif uri and mime_type:
            latest_parts.append({"file_data": {"mime_type": mime_type, "file_uri": uri}})
    contents.append({"role": "user", "parts": latest_parts})

    payload = {
        "systemInstruction": {"parts": [{"text": STUDY_SYSTEM_PROMPT}]},
        "contents": contents,
        "generationConfig": {
            "temperature": 0.35,
            "topP": 0.9,
            "maxOutputTokens": 7000,
        },
    }
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _generate(model: str, payload: bytes) -> str:
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        request = urllib.request.Request(
            _model_url(model),
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY},
        )
        try:
            result, _ = _request_json(request)
            candidates = result.get("candidates") or []
            if not candidates:
                logger.warning("Study Gemini produced no candidates. model=%s result=%s", model, json.dumps(result, ensure_ascii=False)[:1600])
                raise StudyAIError("Akademik AI bu istek için yanıt üretemedi.")
            parts = candidates[0].get("content", {}).get("parts", [])
            answer = "\n".join(part.get("text", "") for part in parts if isinstance(part, dict) and part.get("text")).strip()
            if not answer:
                finish = candidates[0].get("finishReason", "UNKNOWN")
                logger.warning("Study Gemini empty answer. model=%s finish=%s", model, finish)
                raise StudyAIError("Akademik AI boş yanıt döndürdü.")
            return answer
        except StudyAIError as exc:
            last_error = exc
            if not exc.retryable or attempt >= MAX_ATTEMPTS:
                raise
            time.sleep(min(4, 2 ** (attempt - 1)))
    raise last_error or StudyAIError("Akademik AI isteği tamamlanamadı.")


def ask(course_title: str, question: str, mode: str, history: list[dict], files: list[dict]) -> str:
    """Ask Academic AI using only the course materials.

    The `mode` parameter remains for backward-compatible call sites but V11 always
    operates in notes-only mode. Small/medium material sets are sent inline; large
    sets use the Files API. A stable fallback model is tried on transient service
    errors so a single model outage does not break the student workflow.
    """
    _require_key()
    if not files:
        raise StudyAIError("Bu derste henüz not bulunmuyor. Önce PDF veya fotoğraf ekleyin.")

    total_bytes = 0
    can_inline_all = True
    for item in files:
        local_path = item.get("local_path")
        if not local_path or not Path(local_path).is_file():
            can_inline_all = False
            continue
        size = Path(local_path).stat().st_size
        total_bytes += size
        if size > INLINE_SINGLE_MAX_BYTES:
            can_inline_all = False
    can_inline_all = can_inline_all and total_bytes <= INLINE_TOTAL_MAX_BYTES

    if can_inline_all:
        for item in files:
            item["inline"] = True

    payload = _build_payload(course_title, question, history, files)
    models = []
    for model in (STUDY_GEMINI_MODEL, STUDY_GEMINI_FALLBACK_MODEL):
        if model and model not in models:
            models.append(model)

    last_error = None
    for model in models:
        try:
            return _generate(model, payload)
        except StudyAIError as exc:
            last_error = exc
            logger.warning("Academic AI model failed. model=%s retryable=%s code=%s", model, exc.retryable, exc.code)
            # Configuration/client errors should not be hidden by model fallback.
            if exc.code in {400, 401, 403}:
                raise
            continue

    # If the Files API references were accepted earlier but model calls still failed,
    # try one final inline request when the complete material set is small enough.
    if not can_inline_all and total_bytes and total_bytes <= INLINE_TOTAL_MAX_BYTES:
        try:
            inline_payload = _build_payload(course_title, question, history, files, force_inline=True)
            return _generate(models[-1], inline_payload)
        except StudyAIError as exc:
            last_error = exc

    raise last_error or StudyAIError("Akademik AI isteği tamamlanamadı.")
