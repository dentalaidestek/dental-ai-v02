import app.study_ai_v2 as ai_v2
from app.study_retrieval_v2 import RetrievalResult


class _FakeGemini:
    def __init__(self):
        self.model = None

    def generate_stream(self, **kwargs):
        self.model = kwargs["model"]
        yield "Birinci "
        yield "parça"


def test_v2_generation_is_fixed_to_gemini_38_and_streams(monkeypatch):
    fake = _FakeGemini()
    monkeypatch.delenv("STUDY_V2_GEMINI_MODEL", raising=False)
    monkeypatch.setattr(ai_v2, "get_provider", lambda name: fake if name == "gemini" else None)
    retrieval = RetrievalResult(note_context=["[KANIT sayfa=2]\nMetin"])
    assert list(ai_v2.stream_rag_v2("Endodonti", "Nedir?", [], retrieval)) == ["Birinci ", "parça"]
    assert fake.model == "gemini-3.8-flash"


def test_v2_nonstreaming_wrapper_joins_stream(monkeypatch):
    fake = _FakeGemini()
    monkeypatch.setattr(ai_v2, "get_provider", lambda name: fake)
    result = ai_v2.ask_rag_v2("Ortodonti", "Açıkla", [], RetrievalResult(note_context=["Kanıt"]))
    assert result == "Birinci parça"
