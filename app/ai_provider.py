import json
import logging
import os
import socket
import time
import urllib.error
import urllib.request

try:
    from app.xray_trace import xray_trace_event
except Exception:
    def xray_trace_event(*args, **kwargs):
        return None

from app.vision_llm_context import structured_vision_text


logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("DENTAL_CLINICAL_AI_MODEL", "gemini-3.8-flash")
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)
GEMINI_TIMEOUT_SECONDS = int(os.getenv("GEMINI_TIMEOUT_SECONDS", "120"))
GEMINI_MAX_ATTEMPTS = max(1, int(os.getenv("GEMINI_MAX_ATTEMPTS", "3")))
MAX_REQUEST_BYTES = int(os.getenv("GEMINI_MAX_REQUEST_BYTES", str(4 * 1024 * 1024)))
RETRYABLE_HTTP_CODES = {408, 429, 500, 502, 503, 504}


class GeminiAPIError(RuntimeError):
    """Kullanıcıya güvenli biçimde gösterilebilecek klinik AI hata mesajı."""


def _safe_http_error_message(code):
    if code == 429:
        return "Klinik AI kullanım limiti geçici olarak dolu. Lütfen kısa süre sonra tekrar deneyin."
    if code in {500, 502, 503, 504}:
        return "Klinik AI servisi geçici olarak yanıt veremiyor. Lütfen tekrar deneyin."
    if code == 408:
        return "Klinik AI isteği zaman aşımına uğradı. Lütfen tekrar deneyin."
    if code in {401, 403}:
        return "Klinik AI API yetkilendirmesi başarısız. Sunucu yapılandırmasını kontrol edin."
    if code == 400:
        return "Klinik AI isteği geçersiz bulundu. Analiz verilerini kontrol edin."
    return f"Klinik AI isteği başarısız oldu (HTTP {code})."


def _policy_prompt(prompt: str, image_paths=None) -> str:
    structured = structured_vision_text(image_paths)
    return f"""{prompt}

DENTAL AI GÖRÜNTÜ GÜVENLİK VE MİMARİ KURALI — ÜST ÖNCELİKLİ:
- Bu isteğe hiçbir radyografi/fotoğraf pikseli eklenmemiştir. Görüntüyü doğrudan gördüğünü veya incelediğini söyleme.
- Radyografik/görsel bulgular için TEK izinli kaynak aşağıdaki DentalAI özel görüntü motorlarının yapılandırılmış çıktısıdır.
- Motor çıktısında bulunmayan bir radyografik bulguyu görüntüden çıkarmış gibi üretme.
- confidence alanı modelin bu örnekteki tespit skorudur; accuracy/mAP değildir.
- Hekim klinik metni ayrı kanıttır; onu radyografik bulgu gibi sunma.
- Aşağıdaki motor çıktıları boş/erişilemez ise yeni radyografik bulgu üretme; yalnız klinik metin ve kanıt bağlamıyla devam et.

DENTALAI_STRUCTURED_VISION_OUTPUT:
{structured}
""".strip()


def _build_payload(prompt: str, response_schema=None):
    # Text-only by design. There is intentionally no inline_data/image/file part.
    generation_config = {"temperature": 0.1, "maxOutputTokens": 1800}
    if response_schema is not None:
        generation_config["responseMimeType"] = "application/json"
        generation_config["responseSchema"] = response_schema
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": generation_config,
    }
    payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if len(payload_bytes) > MAX_REQUEST_BYTES:
        raise GeminiAPIError("Klinik AI metin isteği güvenli boyut sınırını aşıyor.")
    return payload_bytes


def ask_ai(prompt, image_path=None, image_paths=None, response_schema=None):
    """DentalAI clinical LLM provider.

    The public function keeps the legacy image arguments so existing call sites do
    not break. The arguments are never serialized to Gemini. They are consumed
    locally only to obtain structured outputs from DentalAI's dedicated vision
    motors, then discarded from the external request.
    """
    if not GEMINI_API_KEY:
        raise GeminiAPIError("GEMINI_API_KEY tanımlı değil. Render Environment Variables bölümünü kontrol edin.")

    paths = []
    if image_paths:
        paths.extend([p for p in image_paths if p])
    elif image_path:
        paths.append(image_path)

    final_prompt = _policy_prompt(prompt, paths)
    payload_bytes = _build_payload(final_prompt, response_schema=response_schema)
    last_error = None

    provider_started = time.perf_counter()
    xray_trace_event(
        "provider.request.begin",
        provider="gemini_text_only",
        model=GEMINI_MODEL,
        image_pixel_count=0,
        structured_vision_source_count=len(paths),
        payload_bytes=len(payload_bytes),
        structured_output=bool(response_schema),
        max_attempts=GEMINI_MAX_ATTEMPTS,
    )

    for attempt in range(1, GEMINI_MAX_ATTEMPTS + 1):
        attempt_started = time.perf_counter()
        request = urllib.request.Request(
            GEMINI_URL,
            data=payload_bytes,
            headers={"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=GEMINI_TIMEOUT_SECONDS) as response:
                result = json.loads(response.read().decode("utf-8"))
            candidates = result.get("candidates", [])
            if not candidates:
                raise GeminiAPIError("Klinik AI bu istek için kullanılabilir bir yanıt üretmedi.")
            candidate = candidates[0]
            response_parts = candidate.get("content", {}).get("parts", [])
            texts = [part.get("text", "") for part in response_parts if isinstance(part, dict) and part.get("text")]
            answer = "\n".join(texts).strip()
            if not answer:
                raise GeminiAPIError("Klinik AI cevap verdi ancak metin içeriği bulunamadı.")

            usage = result.get("usageMetadata") or {}
            xray_trace_event(
                "provider.attempt.success",
                provider="gemini_text_only",
                model=GEMINI_MODEL,
                attempt=attempt,
                answer_chars=len(answer),
                prompt_tokens=usage.get("promptTokenCount"),
                output_tokens=usage.get("candidatesTokenCount"),
                total_tokens=usage.get("totalTokenCount"),
                elapsed_ms=round((time.perf_counter()-attempt_started)*1000, 1),
                total_elapsed_ms=round((time.perf_counter()-provider_started)*1000, 1),
            )
            return answer

        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            logger.warning("Clinical AI HTTP error model=%s status=%s attempt=%s body=%s", GEMINI_MODEL, exc.code, attempt, body[:1200])
            last_error = GeminiAPIError(_safe_http_error_message(exc.code))
            if exc.code not in RETRYABLE_HTTP_CODES or attempt >= GEMINI_MAX_ATTEMPTS:
                raise last_error
        except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
            logger.warning("Clinical AI network error model=%s attempt=%s error=%r", GEMINI_MODEL, attempt, exc)
            last_error = GeminiAPIError("Klinik AI bağlantısında geçici bir sorun oluştu. Lütfen tekrar deneyin.")
            if attempt >= GEMINI_MAX_ATTEMPTS:
                raise last_error
        except json.JSONDecodeError as exc:
            logger.warning("Clinical AI response is not JSON: %r", exc)
            raise GeminiAPIError("Klinik AI servis cevabı okunamadı. Lütfen tekrar deneyin.")

        time.sleep(min(4, 2 ** (attempt - 1)))

    raise last_error or GeminiAPIError("Klinik AI isteği tamamlanamadı.")
