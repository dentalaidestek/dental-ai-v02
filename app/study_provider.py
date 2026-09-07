from __future__ import annotations

import base64
import json
import importlib
import logging
import os
import re
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

from app.study_router_state import (
    record_api_result,
    record_local_failure,
    target_available as router_target_available,
)

logger = logging.getLogger(__name__)


class StudyProviderError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: int | None = None,
        retryable: bool = False,
        tracked: bool = False,
    ):
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.tracked = tracked


@dataclass(frozen=True)
class ProviderTarget:
    provider: str
    model: str


class StudyProvider:
    """Provider-neutral contract used by Academic AI and RAG."""

    name = "base"

    def generate(
        self,
        *,
        model: str,
        system_prompt: str,
        history: list[dict],
        prompt: str,
        attachments: list[dict] | None = None,
        temperature: float = 0.3,
        max_output_tokens: int = 7000,
    ) -> str:
        raise NotImplementedError

    def embed_text(self, *, model: str, text: str, dimensions: int = 768) -> list[float]:
        raise NotImplementedError

    def embed_binary(
        self,
        *,
        model: str,
        data: bytes,
        mime_type: str,
        dimensions: int = 768,
    ) -> list[float]:
        raise NotImplementedError

    def supports_binary_embedding(self, mime_type: str) -> bool:
        return False

    def supports_generation_attachment(self, mime_type: str) -> bool:
        return False


_PROVIDER_FACTORIES: dict[str, Callable[[], StudyProvider]] = {}
_PROVIDER_CACHE: dict[str, StudyProvider] = {}


def register_provider(name: str, factory: Callable[[], StudyProvider]) -> None:
    key = (name or "").strip().lower()
    if not key:
        raise ValueError("Provider adı boş olamaz.")
    _PROVIDER_FACTORIES[key] = factory
    _PROVIDER_CACHE.pop(key, None)


def _load_external_provider_modules() -> None:
    raw = (os.getenv("STUDY_PROVIDER_MODULES") or "").strip()
    if not raw:
        return
    for module_name in raw.split(","):
        module_name = module_name.strip()
        if not module_name:
            continue
        try:
            importlib.import_module(module_name)
        except Exception as exc:
            logger.warning("Academic provider module could not be loaded: %s (%s)", module_name, exc)


def get_provider(name: str) -> StudyProvider:
    _load_external_provider_modules()
    key = (name or "").strip().lower()
    factory = _PROVIDER_FACTORIES.get(key)
    if not factory:
        raise StudyProviderError(f"Akademik AI sağlayıcısı yapılandırılmamış: {name}.")
    if key not in _PROVIDER_CACHE:
        _PROVIDER_CACHE[key] = factory()
    return _PROVIDER_CACHE[key]


def _provider_has_key(provider: str) -> bool:
    mapping = {
        "gemini": "GEMINI_API_KEY",
        "cohere": "COHERE_API_KEY",
        "groq": "GROQ_API_KEY",
        "mistral": "MISTRAL_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
    }
    env = mapping.get(provider)
    return True if env is None else bool((os.getenv(env) or "").strip())


def get_generation_targets(profile: str = "complex") -> list[ProviderTarget]:
    """Deterministic Academic AI chain with quota/health skipping only.

    No runtime quality scoring or provider probing is performed. A healthy first
    target receives the request; fallbacks are used only after a real failure or
    when router state already marks a target unavailable.
    """
    targets: list[ProviderTarget] = []

    def add(provider: str, model: str) -> None:
        provider = (provider or "").strip().lower()
        model = (model or "").strip()
        if not provider or not model or not _provider_has_key(provider):
            return
        target = ProviderTarget(provider, model)
        if target not in targets:
            targets.append(target)

    # Custom chain is intentionally opt-in. Old Render variables cannot
    # accidentally re-enable Gemini Lite/Mistral/known-bad targets.
    use_custom = (os.getenv("STUDY_AI_USE_CUSTOM_CHAIN") or "").strip().lower() in {
        "1", "true", "yes", "on"
    }
    raw = (os.getenv("STUDY_AI_PROVIDER_CHAIN") or "").strip() if use_custom else ""
    if raw:
        for item in raw.split(","):
            provider, sep, model = item.strip().partition(":")
            if sep:
                add(provider, model)
        return targets

    profile = (profile or "complex").strip().lower()
    complex_mode = profile in {"complex", "deep", "broad", "exam"}

    gemini_primary = (os.getenv("STUDY_GEMINI_MODEL") or "gemini-3.8-flash").strip()
    gemini_fallback = (os.getenv("STUDY_GEMINI_FALLBACK_MODEL") or "gemini-3.7-flash").strip()
    cohere_plus = (os.getenv("STUDY_COHERE_PLUS_MODEL") or "command-a-plus-05-2026").strip()
    cohere_reasoning = (os.getenv("STUDY_COHERE_REASONING_MODEL") or "command-a-reasoning-08-2025").strip()
    cohere_standard = (os.getenv("STUDY_COHERE_MODEL") or "command-a-03-2025").strip()
    groq_120b = (os.getenv("STUDY_GROQ_STRONG_MODEL") or "openai/gpt-oss-120b").strip()
    groq_20b = (os.getenv("STUDY_GROQ_FAST_MODEL") or "openai/gpt-oss-20b").strip()
    groq_qwen36 = (os.getenv("STUDY_GROQ_QWEN_FAST_MODEL") or "qwen/qwen3.6-27b").strip()
    openrouter_free = (os.getenv("STUDY_OPENROUTER_MODEL") or "openrouter/free").strip()

    if complex_mode:
        ordered = [
            ("gemini", gemini_primary),
            ("gemini", gemini_fallback),
            ("groq", groq_120b),
            ("cohere", cohere_plus),
            ("cohere", cohere_reasoning),
            ("groq", groq_20b),
            ("cohere", cohere_standard),
            ("groq", groq_qwen36),
            ("openrouter", openrouter_free),
        ]
    else:
        # Normal questions conserve the strongest Gemini pool by starting at 3.7,
        # while still keeping both Gemini targets ahead of other providers.
        ordered = [
            ("gemini", gemini_fallback),
            ("gemini", gemini_primary),
            ("groq", groq_20b),
            ("cohere", cohere_standard),
            ("groq", groq_120b),
            ("cohere", cohere_plus),
            ("cohere", cohere_reasoning),
            ("groq", groq_qwen36),
            ("openrouter", openrouter_free),
        ]

    for provider, model in ordered:
        add(provider, model)

    return targets


def report_target_failure(target: ProviderTarget, error: StudyProviderError) -> None:
    # HTTP-backed failures are already accounted for by the provider adapter.
    if not getattr(error, "tracked", False):
        record_local_failure(target.provider, target.model, status_code=error.code)


def report_target_success(target: ProviderTarget) -> None:
    # Kept for compatibility with staged code. Successful vendor calls are
    # recorded at the HTTP adapter where rate-limit headers/token usage exist.
    return None


def target_available(target: ProviderTarget) -> bool:
    return router_target_available(target.provider, target.model)


def get_embedding_target() -> ProviderTarget:
    return ProviderTarget(
        (os.getenv("STUDY_EMBEDDING_PROVIDER") or "gemini").strip().lower(),
        (os.getenv("STUDY_EMBEDDING_MODEL") or "gemini-embedding-2").strip(),
    )


def get_embedding_dimensions() -> int:
    try:
        value = int(os.getenv("STUDY_EMBEDDING_DIMENSIONS", "768"))
    except ValueError:
        value = 768
    return max(128, min(value, 3072))


class GeminiStudyProvider(StudyProvider):
    name = "gemini"
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
    RETRYABLE_HTTP_CODES = {408, 429, 500, 502, 503, 504}

    def __init__(self):
        self.api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
        try:
            self.timeout = int(os.getenv("STUDY_GEMINI_TIMEOUT_SECONDS", "75"))
        except ValueError:
            self.timeout = 75
        try:
            self.max_attempts = max(1, int(os.getenv("STUDY_GEMINI_MAX_ATTEMPTS", "1")))
        except ValueError:
            self.max_attempts = 1

    def _require_key(self) -> None:
        if not self.api_key:
            raise StudyProviderError(
                "GEMINI_API_KEY tanımlı değil. Sunucu Environment Variables bölümünü kontrol edin."
            )

    @staticmethod
    def _safe_message(code: int) -> str:
        if code == 429:
            return "Akademik AI kullanım limiti geçici olarak dolu. Lütfen kısa süre sonra tekrar deneyin."
        if code in {500, 502, 503, 504}:
            return "Akademik AI sağlayıcısı geçici olarak yanıt veremiyor. Lütfen tekrar deneyin."
        if code == 408:
            return "Akademik AI isteği zaman aşımına uğradı. Lütfen tekrar deneyin."
        if code in {401, 403}:
            return "Akademik AI sağlayıcı yetkilendirmesi başarısız. Sunucu yapılandırmasını kontrol edin."
        if code == 400:
            return "Akademik AI isteği sağlayıcı tarafından geçersiz bulundu."
        if code == 404:
            return "Akademik AI modeli bulunamadı. Sunucu model ayarını kontrol edin."
        return f"Akademik AI sağlayıcı isteği başarısız oldu (HTTP {code})."

    def _request_json(
        self,
        url: str,
        payload: dict,
        *,
        model: str,
        operation: str,
        timeout: int | None = None,
    ) -> dict:
        self._require_key()
        if not router_target_available(self.name, model):
            raise StudyProviderError(
                "Gemini hedefi kota/sağlık kaydına göre geçici olarak beklemede.",
                code=429,
                retryable=True,
                tracked=True,
            )
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        last_error: StudyProviderError | None = None
        for attempt in range(1, self.max_attempts + 1):
            request = urllib.request.Request(
                url,
                data=data,
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": self.api_key,
                },
            )
            started = time.perf_counter()
            try:
                with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                    body = response.read().decode("utf-8")
                    try:
                        result = json.loads(body)
                    except json.JSONDecodeError as exc:
                        record_api_result(
                            provider=self.name, model=model, operation=operation, success=False,
                            status_code=getattr(response, "status", 200),
                            latency_ms=int((time.perf_counter() - started) * 1000),
                            response_headers=response.headers, error_body=body,
                        )
                        raise StudyProviderError(
                            "Akademik AI sağlayıcı cevabı okunamadı.",
                            code=getattr(response, "status", 200),
                            tracked=True,
                        ) from exc
                    record_api_result(
                        provider=self.name, model=model, operation=operation, success=True,
                        status_code=getattr(response, "status", 200),
                        latency_ms=int((time.perf_counter() - started) * 1000),
                        response_headers=response.headers, response_json=result,
                    )
                    return result
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                logger.warning("Gemini Academic provider HTTP %s: %s", exc.code, body[:2200])
                record_api_result(
                    provider=self.name, model=model, operation=operation, success=False,
                    status_code=exc.code,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    response_headers=exc.headers, error_body=body,
                )
                last_error = StudyProviderError(
                    self._safe_message(exc.code),
                    code=exc.code,
                    retryable=exc.code in self.RETRYABLE_HTTP_CODES,
                    tracked=True,
                )
                if exc.code == 429:
                    raise last_error
            except StudyProviderError:
                raise
            except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
                logger.warning("Gemini Academic provider connection error: %r", exc)
                record_api_result(
                    provider=self.name, model=model, operation=operation, success=False,
                    status_code=None,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                )
                last_error = StudyProviderError(
                    "Akademik AI sağlayıcısına bağlanırken geçici bir sorun oluştu.",
                    retryable=True,
                    tracked=True,
                )

            if not last_error.retryable or attempt >= self.max_attempts:
                raise last_error
            time.sleep(min(1.5, 2 ** (attempt - 1)))
        raise last_error or StudyProviderError("Akademik AI sağlayıcı isteği tamamlanamadı.")

    def generate(
        self,
        *,
        model: str,
        system_prompt: str,
        history: list[dict],
        prompt: str,
        attachments: list[dict] | None = None,
        temperature: float = 0.3,
        max_output_tokens: int = 7000,
    ) -> str:
        contents: list[dict] = []
        for item in history:
            text = (item.get("content") or "").strip()
            if not text:
                continue
            role = "model" if item.get("role") == "ASSISTANT" else "user"
            contents.append({"role": role, "parts": [{"text": text}]})

        latest_parts: list[dict] = [{"text": prompt}]
        for attachment in attachments or []:
            label = (attachment.get("label") or "").strip()
            if label:
                latest_parts.append({"text": label})
            raw = attachment.get("data")
            mime_type = attachment.get("mime_type")
            if isinstance(raw, bytes) and mime_type:
                latest_parts.append({
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": base64.b64encode(raw).decode("ascii"),
                    }
                })
        contents.append({"role": "user", "parts": latest_parts})

        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "topP": 0.9,
                "maxOutputTokens": max_output_tokens,
            },
        }
        result = self._request_json(f"{self.BASE_URL}/{model}:generateContent", payload, model=model, operation="generation")
        candidates = result.get("candidates") or []
        if not candidates:
            raise StudyProviderError("Akademik AI bu istek için yanıt üretemedi.")
        parts = candidates[0].get("content", {}).get("parts", [])
        answer = "\n".join(
            part.get("text", "")
            for part in parts
            if isinstance(part, dict) and part.get("text")
        ).strip()
        if not answer:
            raise StudyProviderError("Akademik AI boş yanıt döndürdü.")
        return answer

    def _embed(self, *, model: str, parts: list[dict], dimensions: int) -> list[float]:
        payload = {
            "content": {"parts": parts},
            "embedContentConfig": {
                "outputDimensionality": dimensions,
                "autoTruncate": True,
            },
        }
        result = self._request_json(f"{self.BASE_URL}/{model}:embedContent", payload, model=model, operation="embedding", timeout=75)
        values = (result.get("embedding") or {}).get("values") or []
        if not values:
            raise StudyProviderError("Akademik RAG embedding cevabı boş döndü.")
        return [float(value) for value in values]

    def embed_text(self, *, model: str, text: str, dimensions: int = 768) -> list[float]:
        return self._embed(
            model=model,
            parts=[{"text": text}],
            dimensions=dimensions,
        )

    def embed_binary(
        self,
        *,
        model: str,
        data: bytes,
        mime_type: str,
        dimensions: int = 768,
    ) -> list[float]:
        return self._embed(
            model=model,
            parts=[{
                "inline_data": {
                    "mime_type": mime_type,
                    "data": base64.b64encode(data).decode("ascii"),
                }
            }],
            dimensions=dimensions,
        )

    def supports_binary_embedding(self, mime_type: str) -> bool:
        return mime_type in {
            "application/pdf",
            "image/jpeg",
            "image/png",
            "image/webp",
        }

    def supports_generation_attachment(self, mime_type: str) -> bool:
        return mime_type in {
            "application/pdf",
            "image/jpeg",
            "image/png",
            "image/webp",
        }


class CohereStudyProvider(StudyProvider):
    name = "cohere"
    CHAT_URL = "https://api.cohere.com/v2/chat"
    EMBED_URL = "https://api.cohere.com/v2/embed"
    RETRYABLE_HTTP_CODES = {408, 429, 500, 502, 503, 504}

    def __init__(self):
        self.api_key = (os.getenv("COHERE_API_KEY") or "").strip()
        try:
            self.timeout = int(os.getenv("STUDY_COHERE_TIMEOUT_SECONDS", "90"))
        except ValueError:
            self.timeout = 90

    def _require_key(self) -> None:
        if not self.api_key:
            raise StudyProviderError("COHERE_API_KEY tanımlı değil.", code=401)

    def _request_json(self, url: str, payload: dict, *, operation: str) -> dict:
        self._require_key()
        model = str(payload.get("model") or "unknown")
        if not router_target_available(self.name, model):
            raise StudyProviderError(
                "Cohere hedefi kota/sağlık kaydına göre geçici olarak beklemede.",
                code=429, retryable=True, tracked=True,
            )
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "X-Client-Name": "Dental AI Akademik",
            },
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
                try:
                    result = json.loads(body)
                except json.JSONDecodeError as exc:
                    record_api_result(
                        provider=self.name, model=model, operation=operation, success=False,
                        status_code=getattr(response, "status", 200),
                        latency_ms=int((time.perf_counter() - started) * 1000),
                        response_headers=response.headers, error_body=body,
                    )
                    raise StudyProviderError("Cohere sağlayıcı cevabı okunamadı.", tracked=True) from exc
                record_api_result(
                    provider=self.name, model=model, operation=operation, success=True,
                    status_code=getattr(response, "status", 200),
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    response_headers=response.headers, response_json=result,
                )
                return result
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            logger.warning("Cohere Academic provider HTTP %s: %s", exc.code, body[:1800])
            record_api_result(
                provider=self.name, model=model, operation=operation, success=False,
                status_code=exc.code, latency_ms=int((time.perf_counter() - started) * 1000),
                response_headers=exc.headers, error_body=body,
            )
            if exc.code == 429:
                message = "Cohere ücretsiz/trial kullanım limiti dolu."
            elif exc.code in {401, 403}:
                message = "Cohere API anahtarı geçersiz veya yetkisiz."
            elif exc.code == 404:
                message = "Cohere modeli bulunamadı."
            else:
                message = f"Cohere sağlayıcısı isteği başarısız oldu (HTTP {exc.code})."
            raise StudyProviderError(
                message, code=exc.code, retryable=exc.code in self.RETRYABLE_HTTP_CODES, tracked=True,
            ) from exc
        except StudyProviderError:
            raise
        except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
            record_api_result(
                provider=self.name, model=model, operation=operation, success=False,
                status_code=None, latency_ms=int((time.perf_counter() - started) * 1000),
            )
            raise StudyProviderError(
                "Cohere sağlayıcısına bağlanırken geçici bir sorun oluştu.",
                retryable=True, tracked=True,
            ) from exc

    def generate(
        self,
        *,
        model: str,
        system_prompt: str,
        history: list[dict],
        prompt: str,
        attachments: list[dict] | None = None,
        temperature: float = 0.3,
        max_output_tokens: int = 7000,
    ) -> str:
        if attachments:
            raise StudyProviderError(
                "Cohere bu RAG isteğindeki ham PDF/görsel bağlamı için bu adaptörde kullanılmıyor.",
                code=415,
            )
        messages = [{"role": "system", "content": system_prompt}]
        for item in history:
            text = (item.get("content") or "").strip()
            if not text:
                continue
            messages.append({
                "role": "assistant" if item.get("role") == "ASSISTANT" else "user",
                "content": text,
            })
        messages.append({"role": "user", "content": prompt})
        result = self._request_json(self.CHAT_URL, {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_output_tokens,
        }, operation="generation")
        content = ((result.get("message") or {}).get("content") or [])
        answer = "\n".join(
            str(item.get("text") or "")
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        ).strip()
        if not answer:
            raise StudyProviderError("Cohere boş yanıt döndürdü.")
        return answer

    def embed_text(self, *, model: str, text: str, dimensions: int = 768) -> list[float]:
        allowed = (256, 512, 1024, 1536)
        output_dimension = min(allowed, key=lambda value: abs(value - dimensions))
        input_type = "search_query" if text.lstrip().startswith("Diş hekimliği ders notlarında") else "search_document"
        result = self._request_json(self.EMBED_URL, {
            "model": model,
            "texts": [text],
            "input_type": input_type,
            "embedding_types": ["float"],
            "output_dimension": output_dimension,
        }, operation="embedding")
        vectors = ((result.get("embeddings") or {}).get("float") or [])
        if not vectors or not vectors[0]:
            raise StudyProviderError("Cohere embedding cevabı boş döndü.")
        return [float(value) for value in vectors[0]]

    def embed_binary(
        self,
        *,
        model: str,
        data: bytes,
        mime_type: str,
        dimensions: int = 768,
    ) -> list[float]:
        if not mime_type.startswith("image/"):
            raise StudyProviderError("Cohere adaptörü ham PDF binary embedding kullanmıyor.", code=415)
        allowed = (256, 512, 1024, 1536)
        output_dimension = min(allowed, key=lambda value: abs(value - dimensions))
        data_url = f"data:{mime_type};base64,{base64.b64encode(data).decode('ascii')}"
        result = self._request_json(self.EMBED_URL, {
            "model": model,
            "images": [data_url],
            "input_type": "search_document",
            "embedding_types": ["float"],
            "output_dimension": output_dimension,
        }, operation="embedding")
        vectors = ((result.get("embeddings") or {}).get("float") or [])
        if not vectors or not vectors[0]:
            raise StudyProviderError("Cohere görsel embedding cevabı boş döndü.")
        return [float(value) for value in vectors[0]]

    def supports_binary_embedding(self, mime_type: str) -> bool:
        return mime_type in {"image/jpeg", "image/png", "image/webp", "image/gif"}

    def supports_generation_attachment(self, mime_type: str) -> bool:
        return False

class OpenAICompatibleStudyProvider(StudyProvider):
    """Small dependency-free adapter for OpenAI-compatible chat APIs."""

    API_KEY_ENV = ""
    BASE_URL = ""
    RETRYABLE_HTTP_CODES = {408, 429, 500, 502, 503, 504}

    def __init__(self):
        self.api_key = (os.getenv(self.API_KEY_ENV) or "").strip()
        try:
            self.timeout = int(os.getenv("STUDY_FALLBACK_TIMEOUT_SECONDS", "75"))
        except ValueError:
            self.timeout = 75

    def _require_key(self) -> None:
        if not self.api_key:
            raise StudyProviderError(f"{self.API_KEY_ENV} tanımlı değil.", code=401)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _request_json(self, payload: dict, *, operation: str = "generation") -> dict:
        self._require_key()
        model = str(payload.get("model") or "unknown")
        if not router_target_available(self.name, model):
            raise StudyProviderError(
                f"{self.name} hedefi kota/sağlık kaydına göre geçici olarak beklemede.",
                code=429, retryable=True, tracked=True,
            )
        request = urllib.request.Request(
            self.BASE_URL,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers=self._headers(),
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
                try:
                    result = json.loads(body)
                except json.JSONDecodeError as exc:
                    record_api_result(
                        provider=self.name, model=model, operation=operation, success=False,
                        status_code=getattr(response, "status", 200),
                        latency_ms=int((time.perf_counter() - started) * 1000),
                        response_headers=response.headers, error_body=body,
                    )
                    raise StudyProviderError(
                        f"{self.name} sağlayıcı cevabı okunamadı.", tracked=True
                    ) from exc
                record_api_result(
                    provider=self.name, model=model, operation=operation, success=True,
                    status_code=getattr(response, "status", 200),
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    response_headers=response.headers, response_json=result,
                )
                return result
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            logger.warning("%s Academic provider HTTP %s: %s", self.name, exc.code, body[:1800])
            record_api_result(
                provider=self.name, model=model, operation=operation, success=False,
                status_code=exc.code, latency_ms=int((time.perf_counter() - started) * 1000),
                response_headers=exc.headers, error_body=body,
            )
            if exc.code == 429:
                message = f"{self.name} ücretsiz kullanım limiti dolu."
            elif exc.code in {401, 403}:
                message = f"{self.name} API anahtarı geçersiz veya yetkisiz."
            elif exc.code == 404:
                message = f"{self.name} modeli bulunamadı."
            else:
                message = f"{self.name} sağlayıcısı isteği başarısız oldu (HTTP {exc.code})."
            raise StudyProviderError(
                message, code=exc.code, retryable=exc.code in self.RETRYABLE_HTTP_CODES, tracked=True,
            ) from exc
        except StudyProviderError:
            raise
        except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
            record_api_result(
                provider=self.name, model=model, operation=operation, success=False,
                status_code=None, latency_ms=int((time.perf_counter() - started) * 1000),
            )
            raise StudyProviderError(
                f"{self.name} sağlayıcısına bağlanırken geçici bir sorun oluştu.",
                retryable=True, tracked=True,
            ) from exc

    @staticmethod
    def _answer_from_openai_response(result: dict) -> str:
        choices = result.get("choices") or []
        if not choices:
            raise StudyProviderError("Akademik AI bu sağlayıcıdan yanıt alamadı.")
        content = (choices[0].get("message") or {}).get("content")
        if isinstance(content, str):
            answer = content.strip()
        elif isinstance(content, list):
            answer = "\n".join(
                str(item.get("text") or "")
                for item in content
                if isinstance(item, dict) and item.get("text")
            ).strip()
        else:
            answer = ""
        original_answer = answer
        answer = re.sub(r"(?is)<think>.*?</think>", "", answer).strip()
        if re.match(r"(?is)^\s*<think>", original_answer) and "</think>" not in original_answer.lower():
            raise StudyProviderError(
                "Akademik AI final yanıt üretmeden reasoning sınırına ulaştı.",
                retryable=True,
            )
        if not answer:
            raise StudyProviderError("Akademik AI boş yanıt döndürdü.")
        return answer

    def generate(
        self,
        *,
        model: str,
        system_prompt: str,
        history: list[dict],
        prompt: str,
        attachments: list[dict] | None = None,
        temperature: float = 0.3,
        max_output_tokens: int = 7000,
    ) -> str:
        if attachments:
            raise StudyProviderError(
                f"{self.name} bu istekteki görsel/PDF bağlamını güvenilir biçimde işleyemiyor.",
                code=415,
            )
        messages = [{"role": "system", "content": system_prompt}]
        for item in history:
            text = (item.get("content") or "").strip()
            if not text:
                continue
            role = "assistant" if item.get("role") == "ASSISTANT" else "user"
            messages.append({"role": role, "content": text})
        messages.append({"role": "user", "content": prompt})
        result = self._request_json({
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_output_tokens,
            "stream": False,
        })
        return self._answer_from_openai_response(result)


class GroqStudyProvider(OpenAICompatibleStudyProvider):
    name = "groq"
    API_KEY_ENV = "GROQ_API_KEY"
    BASE_URL = "https://api.groq.com/openai/v1/chat/completions"

    def _headers(self) -> dict[str, str]:
        headers = super()._headers()
        headers["User-Agent"] = (
            os.getenv("STUDY_GROQ_USER_AGENT")
            or "DentalAI/1.0 (+https://dentalai.tr)"
        ).strip()
        headers["Accept"] = "application/json"
        return headers


class MistralStudyProvider(OpenAICompatibleStudyProvider):
    name = "mistral"
    API_KEY_ENV = "MISTRAL_API_KEY"
    BASE_URL = "https://api.mistral.ai/v1/chat/completions"


class OpenRouterStudyProvider(OpenAICompatibleStudyProvider):
    name = "openrouter"
    API_KEY_ENV = "OPENROUTER_API_KEY"
    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

    def _headers(self) -> dict[str, str]:
        headers = super()._headers()
        headers["HTTP-Referer"] = (os.getenv("STUDY_OPENROUTER_SITE_URL") or "https://dentalai.tr").strip()
        headers["X-Title"] = "Dental AI Akademik"
        return headers

    def supports_generation_attachment(self, mime_type: str) -> bool:
        return mime_type in {"application/pdf", "image/jpeg", "image/png", "image/webp"}

    def generate(
        self,
        *,
        model: str,
        system_prompt: str,
        history: list[dict],
        prompt: str,
        attachments: list[dict] | None = None,
        temperature: float = 0.3,
        max_output_tokens: int = 7000,
    ) -> str:
        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        for item in history:
            text = (item.get("content") or "").strip()
            if text:
                messages.append({
                    "role": "assistant" if item.get("role") == "ASSISTANT" else "user",
                    "content": text,
                })

        user_content: list[dict] = [{"type": "text", "text": prompt}]
        for index, attachment in enumerate(attachments or [], start=1):
            raw = attachment.get("data")
            mime_type = attachment.get("mime_type")
            if not isinstance(raw, bytes) or not mime_type:
                continue
            data_url = f"data:{mime_type};base64,{base64.b64encode(raw).decode('ascii')}"
            label = (attachment.get("label") or f"not-{index}").strip()
            user_content.append({"type": "text", "text": label})
            if mime_type == "application/pdf":
                user_content.append({
                    "type": "file",
                    "file": {
                        "filename": f"ders-notu-{index}.pdf",
                        "file_data": data_url,
                    },
                })
            elif mime_type.startswith("image/"):
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": data_url},
                })
        messages.append({"role": "user", "content": user_content})
        result = self._request_json({
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_output_tokens,
            "stream": False,
        })
        return self._answer_from_openai_response(result)


register_provider("gemini", GeminiStudyProvider)
register_provider("cohere", CohereStudyProvider)
register_provider("groq", GroqStudyProvider)
register_provider("mistral", MistralStudyProvider)
register_provider("openrouter", OpenRouterStudyProvider)
