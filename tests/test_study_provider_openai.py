from app.study_provider import OpenAIStudyProvider


def test_openai_responses_history_uses_role_appropriate_content_types(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    provider = OpenAIStudyProvider()
    captured = {}

    def fake_request(payload):
        captured.update(payload)
        return {"output_text": "Yanıt"}

    monkeypatch.setattr(provider, "_request_json", fake_request)

    answer = provider.generate(
        model="test-model",
        system_prompt="Sistem",
        history=[
            {"role": "USER", "content": "İlk soru"},
            {"role": "ASSISTANT", "content": "İlk yanıt"},
        ],
        prompt="Devam",
    )

    assert answer == "Yanıt"
    assert captured["input"][1]["content"][0]["type"] == "input_text"
    assert captured["input"][2]["content"][0]["type"] == "output_text"
