import os
import json
import urllib.request
import urllib.error

LOCAL_AI_URL = os.getenv(
    "DENTAL_LOCAL_AI_URL",
    "http://127.0.0.1:8080/v1/chat/completions"
)

def ask_local_ai(prompt: str, image_path=None) -> str:
    payload = {
        "model": "gemma-4-E2B-it",
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.2,
        "stream": False
    }

    data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        LOCAL_AI_URL,
        data=data,
        headers={
            "Content-Type": "application/json"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            result = json.loads(response.read().decode("utf-8"))

        return result["choices"][0]["message"]["content"]

    except urllib.error.URLError as e:
        raise RuntimeError(
            "Yerel Gemma sunucusuna bağlanılamadı: "
            f"{LOCAL_AI_URL} ({e})"
        )
