import base64
import json
import mimetypes
import os
import urllib.error
import urllib.request


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)


def _image_to_inline_data(image_path):
    path = os.path.abspath(image_path)

    if not os.path.exists(path):
        raise RuntimeError(f"Görüntü bulunamadı: {path}")

    mime_type, _ = mimetypes.guess_type(path)
    if not mime_type:
        mime_type = "image/jpeg"

    with open(path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")

    return {
        "inline_data": {
            "mime_type": mime_type,
            "data": encoded,
        }
    }


def ask_ai(prompt, image_path=None, image_paths=None):
    """
    Dental AI -> Gemini API

    Tek veya birden fazla görüntüyü aynı vaka bağlamında
    Gemini'ye gönderir.

    API anahtarı kodda tutulmaz.
    Render'da GEMINI_API_KEY environment variable olarak verilir.
    """

    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY tanımlı değil. "
            "Render Environment Variables bölümüne eklenmeli."
        )

    paths = []

    if image_paths:
        paths.extend(image_paths)
    elif image_path:
        paths.append(image_path)

    parts = [
        {
            "text": prompt
        }
    ]

    for path in paths:
        if path and os.path.exists(path):
            parts.append(_image_to_inline_data(path))

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": parts,
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 1800,
        },
    }

    request = urllib.request.Request(
        GEMINI_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": GEMINI_API_KEY,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            result = json.loads(
                response.read().decode("utf-8")
            )

        candidates = result.get("candidates", [])

        if not candidates:
            raise RuntimeError(
                f"Gemini cevap üretmedi: {json.dumps(result, ensure_ascii=False)[:2000]}"
            )

        response_parts = (
            candidates[0]
            .get("content", {})
            .get("parts", [])
        )

        texts = [
            part.get("text", "")
            for part in response_parts
            if part.get("text")
        ]

        answer = "\n".join(texts).strip()

        if not answer:
            raise RuntimeError(
                "Gemini cevap verdi ancak metin içeriği bulunamadı."
            )

        return answer

    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Gemini API HTTP {e.code}: {body[:3000]}"
        )

    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Gemini API bağlantısı başarısız: {e}"
        )

    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Gemini API cevabı JSON olarak okunamadı: {e}"
        )
