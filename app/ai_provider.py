import json
import os
import urllib.request
import urllib.error

LOCAL_AI_URL = os.getenv(
    "DENTAL_LOCAL_AI_URL",
    "http://127.0.0.1:8080/v1/chat/completions"
)

MODEL = "gemma-4-E2B-it.litertlm"


def ask_ai(prompt, image_path=None, image_paths=None):
    """
    Dental AI -> yerel LiteRT-LM -> Gemma 4 E2B

    Tek veya birden fazla görüntüyü aynı vaka bağlamında
    Gemma'ya gönderir.
    """

    paths = []

    if image_paths:
        paths.extend(image_paths)
    elif image_path:
        paths.append(image_path)

    valid_paths = [
        os.path.abspath(path)
        for path in paths
        if path and os.path.exists(path)
    ]

    if valid_paths:
        content = [
            {
                "type": "text",
                "text": prompt
            }
        ]

        for absolute_path in valid_paths:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"file://{absolute_path}"
                    }
                }
            )
    else:
        content = prompt

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": content
            }
        ],
        "temperature": 0.1,
        "max_tokens": 1800,
        "stream": False
    }

    request = urllib.request.Request(
        LOCAL_AI_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=300
        ) as response:
            result = json.loads(
                response.read().decode("utf-8")
            )

        return result["choices"][0]["message"]["content"]

    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Yerel Gemma bağlantısı başarısız: {e}"
        )

    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise RuntimeError(
            f"Gemma API cevabı beklenen formatta değil: {e}"
        )
