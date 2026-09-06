import base64
import json
import logging
import mimetypes
import os
import socket
import time
import urllib.error
import urllib.request


logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)

GEMINI_TIMEOUT_SECONDS = int(os.getenv("GEMINI_TIMEOUT_SECONDS", "120"))
GEMINI_MAX_ATTEMPTS = max(1, int(os.getenv("GEMINI_MAX_ATTEMPTS", "3")))
MAX_REQUEST_BYTES = int(os.getenv("GEMINI_MAX_REQUEST_BYTES", str(19 * 1024 * 1024)))
RETRYABLE_HTTP_CODES = {408, 429, 500, 502, 503, 504}
ALLOWED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}


class GeminiAPIError(RuntimeError):
    """Kullanıcıya güvenli biçimde gösterilebilecek Gemini hata mesajı."""


def _validate_image_signature(data, mime_type, path):
    if not data:
        raise GeminiAPIError(f"Görüntü dosyası boş: {os.path.basename(path)}")

    if mime_type == "image/jpeg" and not data.startswith(b"\xff\xd8\xff"):
        raise GeminiAPIError(f"Geçersiz JPEG dosyası: {os.path.basename(path)}")

    if mime_type == "image/png" and not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise GeminiAPIError(f"Geçersiz PNG dosyası: {os.path.basename(path)}")

    if mime_type == "image/webp" and not (
        len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    ):
        raise GeminiAPIError(f"Geçersiz WEBP dosyası: {os.path.basename(path)}")


def _image_to_inline_data(image_path):
    path = os.path.abspath(image_path)

    if not os.path.exists(path):
        raise GeminiAPIError(f"Görüntü dosyası bulunamadı: {os.path.basename(path)}")

    if not os.path.isfile(path):
        raise GeminiAPIError(f"Geçersiz görüntü yolu: {os.path.basename(path)}")

    mime_type, _ = mimetypes.guess_type(path)
    mime_type = (mime_type or "").lower()

    if mime_type == "image/jpg":
        mime_type = "image/jpeg"

    if mime_type not in ALLOWED_IMAGE_MIME_TYPES:
        raise GeminiAPIError(
            f"Desteklenmeyen görüntü türü: {os.path.basename(path)}. "
            "JPG, PNG veya WEBP kullanın."
        )

    with open(path, "rb") as f:
        data = f.read()

    _validate_image_signature(data, mime_type, path)

    encoded = base64.b64encode(data).decode("ascii")

    return {
        "inline_data": {
            "mime_type": mime_type,
            "data": encoded,
        }
    }


def _build_payload(prompt, paths, response_schema=None):
    parts = [{"text": prompt}]

    for path in paths:
        if path:
            parts.append(_image_to_inline_data(path))

    generation_config = {
        "temperature": 0.1,
        "maxOutputTokens": 1800,
    }

    if response_schema is not None:
        generation_config["responseMimeType"] = "application/json"
        generation_config["responseSchema"] = response_schema

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": parts,
            }
        ],
        "generationConfig": generation_config,
    }

    payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    if len(payload_bytes) > MAX_REQUEST_BYTES:
        size_mb = len(payload_bytes) / (1024 * 1024)
        limit_mb = MAX_REQUEST_BYTES / (1024 * 1024)
        raise GeminiAPIError(
            f"Yüklenen görüntüler Gemini isteği için fazla büyük "
            f"({size_mb:.1f} MB; güvenli sınır {limit_mb:.0f} MB). "
            "Daha az veya daha küçük görüntüyle tekrar deneyin."
        )

    return payload_bytes


def _safe_http_error_message(code):
    if code == 429:
        return "Gemini kullanım limiti geçici olarak dolu. Lütfen kısa süre sonra tekrar deneyin."
    if code in {500, 502, 503, 504}:
        return "Gemini servisi geçici olarak yanıt veremiyor. Lütfen tekrar deneyin."
    if code == 408:
        return "Gemini isteği zaman aşımına uğradı. Lütfen tekrar deneyin."
    if code in {401, 403}:
        return "Gemini API yetkilendirmesi başarısız. Sunucu yapılandırmasını kontrol edin."
    if code == 400:
        return "Gemini isteği geçersiz bulundu. Görsel ve analiz verilerini kontrol edin."
    return f"Gemini API isteği başarısız oldu (HTTP {code})."


def ask_ai(prompt, image_path=None, image_paths=None, response_schema=None):
    """
    Dental AI -> Gemini API.

    - Tek veya birden fazla dental görüntüyü destekler.
    - response_schema verilirse Gemini'den yapılandırılmış JSON ister.
    - Geçici HTTP/ağ hatalarında kontrollü retry uygular.
    - API anahtarını veya ham servis cevabını kullanıcı mesajına taşımaz.
    """

    if not GEMINI_API_KEY:
        raise GeminiAPIError(
            "GEMINI_API_KEY tanımlı değil. Render Environment Variables bölümünü kontrol edin."
        )

    paths = []
    if image_paths:
        paths.extend(image_paths)
    elif image_path:
        paths.append(image_path)

    payload_bytes = _build_payload(prompt, paths, response_schema=response_schema)
    last_error = None

    for attempt in range(1, GEMINI_MAX_ATTEMPTS + 1):
        request = urllib.request.Request(
            GEMINI_URL,
            data=payload_bytes,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": GEMINI_API_KEY,
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=GEMINI_TIMEOUT_SECONDS) as response:
                result = json.loads(response.read().decode("utf-8"))

            candidates = result.get("candidates", [])
            if not candidates:
                prompt_feedback = result.get("promptFeedback", {})
                logger.warning(
                    "Gemini cevap üretmedi. model=%s prompt_feedback=%s",
                    GEMINI_MODEL,
                    json.dumps(prompt_feedback, ensure_ascii=False)[:1200],
                )
                raise GeminiAPIError("Gemini bu istek için kullanılabilir bir yanıt üretmedi.")

            candidate = candidates[0]
            response_parts = candidate.get("content", {}).get("parts", [])
            texts = [
                part.get("text", "")
                for part in response_parts
                if isinstance(part, dict) and part.get("text")
            ]
            answer = "\n".join(texts).strip()

            if not answer:
                finish_reason = candidate.get("finishReason", "UNKNOWN")
                logger.warning(
                    "Gemini boş metin döndürdü. model=%s finish_reason=%s",
                    GEMINI_MODEL,
                    finish_reason,
                )
                raise GeminiAPIError("Gemini cevap verdi ancak metin içeriği bulunamadı.")

            return answer

        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            logger.warning(
                "Gemini HTTP hatası. model=%s status=%s attempt=%s/%s body=%s",
                GEMINI_MODEL,
                e.code,
                attempt,
                GEMINI_MAX_ATTEMPTS,
                body[:1500],
            )
            last_error = GeminiAPIError(_safe_http_error_message(e.code))

            if e.code not in RETRYABLE_HTTP_CODES or attempt >= GEMINI_MAX_ATTEMPTS:
                raise last_error

        except (urllib.error.URLError, TimeoutError, socket.timeout) as e:
            logger.warning(
                "Gemini bağlantı hatası. model=%s attempt=%s/%s error=%r",
                GEMINI_MODEL,
                attempt,
                GEMINI_MAX_ATTEMPTS,
                e,
            )
            last_error = GeminiAPIError(
                "Gemini bağlantısında geçici bir sorun oluştu. Lütfen tekrar deneyin."
            )
            if attempt >= GEMINI_MAX_ATTEMPTS:
                raise last_error

        except json.JSONDecodeError as e:
            logger.warning("Gemini API yanıt gövdesi JSON değil: %r", e)
            raise GeminiAPIError("Gemini servis cevabı okunamadı. Lütfen tekrar deneyin.")

        time.sleep(min(4, 2 ** (attempt - 1)))

    raise last_error or GeminiAPIError("Gemini isteği tamamlanamadı.")
