import app.study_ai_v2 as ai_v2
from app.study_provider import ProviderTarget, StudyProviderError
from app.study_retrieval_v2 import RetrievalResult


class _FakeGemini:
    def __init__(self):
        self.model = None

    def generate_stream(self, **kwargs):
        self.model = kwargs["model"]
        yield "Birinci "
        yield "parça"


def test_v2_generation_uses_configured_single_model_and_streams(monkeypatch):
    fake = _FakeGemini()
    monkeypatch.delenv("STUDY_V2_GEMINI_MODEL", raising=False)
    monkeypatch.setattr(ai_v2, "get_provider", lambda name: fake if name == "gemini" else None)
    retrieval = RetrievalResult(note_context=["[KANIT sayfa=2]\nMetin"], evidence_sufficient=True)
    assert list(ai_v2.stream_rag_v2("Endodonti", "Nedir?", [], retrieval)) == ["Birinci ", "parça"]
    assert fake.model == ai_v2.ACADEMIC_V2_MODEL == "gemini-3.5-flash-lite"


def test_v2_nonstreaming_wrapper_joins_stream(monkeypatch):
    fake = _FakeGemini()
    monkeypatch.setattr(ai_v2, "get_provider", lambda name: fake)
    result = ai_v2.ask_rag_v2("Ortodonti", "Açıkla", [], RetrievalResult(note_context=["Kanıt"], evidence_sufficient=True))
    assert result == "Birinci parça"


class _FailBeforeOutput:
    def supports_generation_attachment(self, _mime_type):
        return True

    def generate_stream(self, **_kwargs):
        raise StudyProviderError("Gemini 503", code=503, retryable=True, tracked=True)
        yield  # pragma: no cover


class _FailAfterOutput(_FailBeforeOutput):
    def generate_stream(self, **_kwargs):
        yield "başladı"
        raise StudyProviderError("bağlantı koptu", retryable=False, tracked=True)


def test_v2_never_uses_second_provider_after_primary_call_fails(monkeypatch):
    primary = _FailBeforeOutput()
    fallback = _FakeGemini()
    monkeypatch.setattr(
        ai_v2,
        "_generation_targets",
        lambda: [ProviderTarget("gemini", "primary"), ProviderTarget("openai", "fallback")],
    )
    monkeypatch.setattr(ai_v2, "target_available", lambda _target: True)
    monkeypatch.setattr(
        ai_v2, "get_provider", lambda name: primary if name == "gemini" else fallback
    )
    monkeypatch.setattr(ai_v2, "report_target_failure", lambda *_args: None)

    try:
        list(ai_v2.stream_rag_v2(
            "Endodonti", "Nedir?", [],
            RetrievalResult(note_context=["Kanıt"], evidence_sufficient=True),
        ))
    except ai_v2.StudyAIError:
        pass
    else:  # pragma: no cover
        raise AssertionError("One failed provider call must not trigger a second external AI call")
    assert fallback.model is None


def test_v2_never_switches_provider_after_stream_has_started(monkeypatch):
    primary = _FailAfterOutput()
    fallback = _FakeGemini()
    monkeypatch.setattr(
        ai_v2,
        "_generation_targets",
        lambda: [ProviderTarget("gemini", "primary"), ProviderTarget("openai", "fallback")],
    )
    monkeypatch.setattr(ai_v2, "target_available", lambda _target: True)
    monkeypatch.setattr(
        ai_v2, "get_provider", lambda name: primary if name == "gemini" else fallback
    )
    monkeypatch.setattr(ai_v2, "report_target_failure", lambda *_args: None)

    stream = ai_v2.stream_rag_v2(
        "Endodonti", "Nedir?", [], RetrievalResult(note_context=["Kanıt"], evidence_sufficient=True)
    )
    assert next(stream) == "başladı"
    try:
        next(stream)
    except ai_v2.StudyAIError as exc:
        assert "Akademik AI yanıtı" in str(exc)
        assert "bağlantı koptu" not in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Partial stream must fail without a provider switch")
    assert fallback.model is None


def test_v2_provider_failures_do_not_expose_provider_or_raw_error(monkeypatch):
    monkeypatch.setattr(
        ai_v2,
        "_generation_targets",
        lambda: [ProviderTarget("gemini", "primary")],
    )
    monkeypatch.setattr(ai_v2, "target_available", lambda _target: True)
    monkeypatch.setattr(ai_v2, "get_provider", lambda _name: _FailBeforeOutput())
    monkeypatch.setattr(ai_v2, "report_target_failure", lambda *_args: None)

    try:
        list(ai_v2.stream_rag_v2(
            "Ortodonti", "Nedir?", [], RetrievalResult(note_context=["Kanıt"], evidence_sufficient=True)
        ))
    except ai_v2.StudyAIError as exc:
        public_message = str(exc)
        assert "Gemini" not in public_message
        assert "503" not in public_message
        assert "Akademik AI" in public_message
    else:  # pragma: no cover
        raise AssertionError("Provider failure must reach the public error boundary")
