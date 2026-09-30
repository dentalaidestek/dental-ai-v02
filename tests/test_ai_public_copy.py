import json

from app.ai_engine import parse_ai_result


def test_clinical_results_hide_infrastructure_vocabulary():
    raw = json.dumps({
        "status": "FINAL",
        "most_likely": "OpenAI model çıktısına göre görüntü motoru bulgusu mevcut.",
        "findings": ["Gemini provider fallback yaptı."],
    })

    result = parse_ai_result(raw)
    public_text = json.dumps(result, ensure_ascii=False).lower()

    for hidden_term in ("openai", "gemini", "provider", "fallback", "model", "motor"):
        assert hidden_term not in public_text
