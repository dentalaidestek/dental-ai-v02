"""Foto Fikir: onaylı metinlerden hekime özel içerik görselleri.

Ana akış: konu secilir, slayt metinleri hekim tarafindan onaylanir, onayli
metinlerden karusel gorselleri uretilir. Marka kiti, Instagram profili ve
Reels cekim plani istege bagli araclardir. Mevzuat kontrolu yerel kural
listesiyle calisir; hicbir metin sunucuda saklanmaz, yalnizca is kaydi tutulur.

Mod: FOTO_FIKIR_MOCK=1 ile her ucap anahtarsiz ornek uretir. Anahtarlar
(ANTHROPIC_API_KEY / GEMINI_API_KEY) tanimliyken mock kapaliysa gercek
saglayicilar kullanilir; anahtar yoksa tum ucmlar 503 doner.
"""
from __future__ import annotations

import base64
import concurrent.futures
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import List, Optional, Tuple

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel
from sqlmodel import Field, Session, SQLModel, select

from app.http_transport import urlopen
from app.auth_rate import admit
from app import provider_budget
from app.foto_fikir_creative import (
    CREATIVE_DIRECTOR_BRIEF,
    actionable_tips,
    audit_creative_output,
    creative_prompt_for_slide,
    recommend_style,
    reel_shot_plan,
    safe_rewrite_suggestion,
    story_arc_roles,
)

try:
    from app import object_storage as _ff_storage
except Exception:  # pragma: no cover - depolama kapali kurulumlarda yerel dosya yeterli
    _ff_storage = None

logger = logging.getLogger("uvicorn.error.foto_fikir")

# Uç yolları tam yazılır: görsel servisi /uploads/... öneki router prefix'iyle çakışmasın.
foto_fikir_router = APIRouter(tags=["foto-fikir"])

FOTO_FIKIR_MOCK_ENV = "FOTO_FIKIR_MOCK"
FOTO_FIKIR_CLAUDE_MODEL = os.getenv("FOTO_FIKIR_CLAUDE_MODEL", "claude-haiku-5-5")
FF_GEMINI_IMAGE_MODELS = [
    item.strip()
    for item in os.getenv(
        "FF_GEMINI_IMAGE_MODELS",
        "gemini-3.5-flash-image,gemini-2.5-flash-image,gemini-2.0-flash-preview-image-generation",
    ).split(",")
    if item.strip()
]
FOTO_FIKIR_UNAVAILABLE = "Foto Fikir şu anda yapılandırılmadı; yönetici anahtarları eklemeli."
FOTO_FIKIR_QUOTA_LIMIT = 30
FOTO_FIKIR_MEVZUAT_DISCLAIMER = (
    "Mevzuat kontrolü yerel kural listesiyle yapılır; liste tüm riskleri kapsamaz ve "
    "rehberlik amaçlıdır. Yayın onayı ile nihai sorumluluk içerik paylaşımı yapan hekimdedir."
)
FF_KINDS = ["IDEA", "SLIDES", "MEVZUAT", "IMAGE", "BRAND", "IG", "REELS"]
FF_KIND_LABELS = {
    "IDEA": "Fikir",
    "SLIDES": "Slayt",
    "MEVZUAT": "Mevzuat",
    "IMAGE": "Görsel",
    "BRAND": "Marka Kiti",
    "IG": "Instagram",
    "REELS": "Reels",
}

# 15 özgün stil; sıra arayüzdeki kart sırasıdır (FF_STYLE_NAMES uzunluğu test edilir).
FF_STYLES = [
    {"id": "sade-klinik", "name": "Sade Klinik", "hint": "Beyaz zemin, net tipografi, okunabilir başlıklar."},
    {"id": "derin-lacivert", "name": "Derin Lacivert", "hint": "Koyu lacivert degrade, güven veren kurumsal ton."},
    {"id": "nane-esintisi", "name": "Nane Esintisi", "hint": "Ferah nane yeşili vurgular, temiz arka plan."},
    {"id": "yumusak-gul", "name": "Yumuşak Gül", "hint": "Pastel gül rengi, sıcak ve davetkâr his."},
    {"id": "mum-isigi", "name": "Mum Işığı", "hint": "Sıcak amber ışık, yumuşak geçişler."},
    {"id": "mermer-doku", "name": "Mermer Doku", "hint": "Mermer dokusu ve ince altın çizgiler."},
    {"id": "iki-renk", "name": "İki Renk", "hint": "Zıt iki renk bloğu, güçlü kontrast."},
    {"id": "yumusak-golge", "name": "Yumuşak Gölge", "hint": "Katmanlı kartlar, derinlik veren yumuşak gölgeler."},
    {"id": "su-cizgisi", "name": "Su Çizgisi", "hint": "İnce mavi dalgalı çizgiler, akışkan arka plan."},
    {"id": "kagit-kirma", "name": "Kağıt Katmanı", "hint": "Üst üste kağıt katmanları, el yapımı his."},
    {"id": "gece-neon", "name": "Gece Neon", "hint": "Koyu zeminde konturlu neon çizgiler."},
    {"id": "isik-odagi", "name": "Işık Odağı", "hint": "Merkezde spot ışık, kenarlarda karartma."},
    {"id": "toprak-ton", "name": "Toprak Tonları", "hint": "Kum ve kil tonları, doğal sıcaklık."},
    {"id": "cam-saydam", "name": "Cam Saydam", "hint": "Buğulu cam paneller, hafif saydamlık."},
    {"id": "defter-cizgi", "name": "Defter Çizgisi", "hint": "Çizgili defter zemin, el yazısı vurgular."},
]
FF_STYLE_MAP = {style["id"]: style for style in FF_STYLES}
FF_STYLE_NAMES = [style["name"] for style in FF_STYLES]

FOTO_FIKIR_SCENES = [
    "Loupe takarken",
    "Eldivenle kalp yaparken",
    "Ağız içi tarayıcıyla çalışırken",
    "Diş modeliyle anlatırken",
    "Hastayla konuşurken",
    "Resepsiyonda",
]

FF_UPLOAD_ROOT = "foto_fikir"
FF_BRAND_PREFIX = "brand_"
FF_IMAGE_PREFIX = "ff_"
FF_BRAND_FILE_LIMIT = 8 * 1024 * 1024
FF_BRAND_MAX_FILES = 3
FF_MEVZUAT_MAX_TEXTS = 12
FF_SLIDE_MAX_COUNT = 8
FF_PROVIDER_TIMEOUT = 120

_FF_UPLOAD_NAME_RE = re.compile(r"^(ff_|brand_)[A-Za-z0-9._-]+\.(png|jpe?g)$")


class FFUnavailable(RuntimeError):
    """Foto Fikir motoru yapılandırılmadığında veya sağlayıcı başarısız olduğunda yükselir."""


def _ff_mock() -> bool:
    return (os.getenv(FOTO_FIKIR_MOCK_ENV) or "").strip() == "1"


def _ff_has_claude() -> bool:
    return bool((os.getenv("ANTHROPIC_API_KEY") or "").strip())


def _ff_has_gemini() -> bool:
    return bool((os.getenv("GEMINI_API_KEY") or "").strip())


# ---------------------------------------------------------------------------
# Mevzuat yerel kuralları
# ---------------------------------------------------------------------------

def _ff_fold(text: str) -> str:
    """Anahtar eşleşmesi için Türkçe duyarsız küçük harf biçimi.

    Python'un lower() çağrısı 'İ' harfini 'i' + nokta birleştirme işareti
    (U+0307) yapar; bu işaret kaldırılır ve 'I' doğrudan 'i' sayılır.
    """
    folded = (text or "").replace("İ", "i").replace("I", "i").lower()
    return folded.replace("i\u0307", "i")


_FF_MEVZUAT_RULES = [
    {
        "level": "KALDIR",
        "keywords": ("garanti", "%100", "kesin çözüm", "kurtulursunuz", "sonsuza kadar"),
        "reason": "Tedavi sonucu için garanti veya kesinlik vaadi içeriyor.",
        "suggestion": "Sonuç taahhüdünü kaldırın; tedavi planının hekim değerlendirmesiyle şekillendiğini belirtin.",
    },
    {
        "level": "KALDIR",
        "pair": ("öncesi", "sonrası"),
        "reason": "Tedavi öncesi/sonrası karşılaştırması yapılıyor.",
        "suggestion": "Karşılaştırma ifadesini kaldırın; tek durumu tarif eden nötr bir cümle kurun.",
    },
    {
        "level": "DIKKAT",
        "keywords": ("en iyi", "en güvenilir", "en başarılı", "en hızlı", "dünyanın en", "türkiyenin en", "bölgenin en", "bir numara", "rakipsiz"),
        "reason": "Üstünlük iddiası içeriyor; doğrulanabilir olmadığı için risklidir.",
        "suggestion": "Süperlatifi kaldırın; somut bilgilendirmeyle (süre, adım, malzeme) yeniden yazın.",
    },
    {
        "level": "DIKKAT",
        "keywords": ("indirim", "indirimli", "kampanya", "ücretsiz ilk", "hediye çek"),
        "reason": "İndirim veya kampanya ifadesi mevzuatta kısıtlanmıştır.",
        "suggestion": "Kampanya dilini çıkarın; hizmetin kapsamını nötr biçimde anlatın.",
    },
    {
        "level": "DIKKAT",
        "media_pair": (("radyo", "televizyon", "tv", "reklam"), "hasta"),
        "reason": "Hasta verilerinin radyo/televizyon paylaşımı ifşaya tabidir.",
        "suggestion": "Hasta bilgisi içeren yayın cümlesini kaldırın; yazılı onay olmadan paylaşmayın.",
    },
]


def mevzuat_local_check(text: str) -> Optional[dict]:
    """Tek bir metni yerel mevzuat kurallarıyla tarar; sorun yoksa None döner."""
    folded = _ff_fold(text or "")
    if not folded:
        return None
    for rule in _FF_MEVZUAT_RULES:
        if rule.get("keywords"):
            for keyword in rule["keywords"]:
                if keyword and keyword in folded:
                    return _ff_mevzuat_result(text, rule["level"], rule["reason"], rule["suggestion"])
        if rule.get("pair"):
            first, second = rule["pair"]
            if first in folded and second in folded:
                return _ff_mevzuat_result(text, rule["level"], rule["reason"], rule["suggestion"])
        if rule.get("media_pair"):
            media_words, sensitive = rule["media_pair"]
            if any(word in folded for word in media_words) and sensitive in folded:
                return _ff_mevzuat_result(text, rule["level"], rule["reason"], rule["suggestion"])
    return None


def _ff_mevzuat_result(text: str, level: str, reason: str, suggestion: str) -> dict:
    return {"index": 0, "text": text, "level": level, "reason": reason, "suggestion": suggestion}


# ---------------------------------------------------------------------------
# İş kaydı modeli ve kota
# ---------------------------------------------------------------------------

def _ff_utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class FotoFikirJob(SQLModel, table=True):
    """Foto Fikir üretim kaydı; kota görsel üreten işlerden hesaplanır."""

    id: str = Field(primary_key=True)
    user_id: int = Field(index=True)
    kind: str = Field(index=True)
    topic: str = ""
    style_id: Optional[str] = None
    payload: str = "{}"
    image_path: Optional[str] = None
    status: str = "DONE"
    provider: str = "mock"
    model: str = "mock"
    created_at: datetime = Field(default_factory=_ff_utcnow, index=True)


def foto_fikir_quota_used(session: Session, user_id: int) -> int:
    """Bu ay üretilen görsel sayısını (IMAGE + BRAND) sayar; sınır 30/ay.

    Bir karusel işi N görsel ürettiyse N hak yakar; payload'daki image_paths
    uzunluğu esas alınır, okunamayan payload'lar 1 görsel sayılır.
    """
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    rows = session.exec(
        select(FotoFikirJob.payload).where(
            FotoFikirJob.user_id == user_id,
            FotoFikirJob.kind.in_(["IMAGE", "BRAND"]),
            FotoFikirJob.created_at >= month_start,
        )
    ).all()
    total = 0
    for payload in rows:
        try:
            data = json.loads(payload or "{}")
            total += max(1, len(data.get("image_paths") or []))
        except Exception:
            total += 1
    return total


def _ff_check_quota(used: int) -> None:
    if used >= FOTO_FIKIR_QUOTA_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="Bu ayın 30 görsel üretim hakkı doldu. Haklar her ayın ilk gününde yenilenir.",
        )


def _ff_record_job(
    main_module,
    user_id: int,
    kind: str,
    topic: str,
    payload: dict,
    *,
    image_path: Optional[str] = None,
    style_id: Optional[str] = None,
    provider: str = "mock",
    model: str = "mock",
    status: str = "DONE",
) -> str:
    """İş kaydını yazar ve iş kimliğini döndürür; kayıt hatası üretimi bloklamaz."""
    job_id = uuid.uuid4().hex
    try:
        with main_module.Session(main_module.engine, expire_on_commit=False) as session:
            session.add(
                FotoFikirJob(
                    id=job_id,
                    user_id=user_id,
                    kind=kind,
                    topic=topic[:200],
                    style_id=style_id,
                    payload=json.dumps(payload, ensure_ascii=False),
                    image_path=image_path,
                    status=status,
                    provider=provider,
                    model=model,
                    created_at=_ff_utcnow(),
                )
            )
            session.commit()
    except Exception as exc:  # noqa: BLE001 - kayıt hatası kullanıcı yanıtını etkilememeli
        logger.warning("Foto Fikir iş kaydı yazılamadı kind=%s error=%r", kind, exc)
    return job_id


# ---------------------------------------------------------------------------
# Kimlik, yanıt ve hata yardımcıları
# ---------------------------------------------------------------------------

def _ff_json(data: dict, status: int = 200) -> JSONResponse:
    response = JSONResponse(data, status_code=status)
    response.headers["Cache-Control"] = "private, no-store"
    return response


def _ff_mock_flag(mock: bool) -> dict:
    if mock:
        return {"mock": True, "uyari": "örnek çıktı (mock)"}
    return {"mock": False}


def _ff_auth(request: Request) -> Tuple[object, object, Optional[JSONResponse]]:
    """main.get_current_user oturum deseni; döngüsel içe aktarmayı erteler.

    Sıra: önce web çerezi (dental_ai_session) değerlendirilir ve web yolu
    değişmeden korunur; çerez yokken "authorization" başlığındaki Bearer
    belirteci, mobil v1 yönlendiricilerinin kullandığı aynı belirteç
    mekanizmasıyla (app.mobile_api._mobile_user + SessionToken) çözülür.
    Geçersiz ya da süresi dolmuş belirteç, web yoluyla aynı 401 Türkçe
    yanıtı döner. Çerez ve başlık yokken main içe aktarılmaz; oturumsuz
    istek hızlı 401 alır.
    """
    if not request.cookies.get("dental_ai_session"):
        auth_header = request.headers.get("authorization") or ""
        scheme, _, token = auth_header.partition(" ")
        token = token.strip()
        if scheme.lower() != "bearer" or not token:
            return None, None, _ff_json({"detail": "Oturum gerekli."}, 401)
        from fastapi.security import HTTPAuthorizationCredentials

        from app import main as main_module
        from app import mobile_api as mobile_module

        try:
            user = mobile_module._mobile_user(
                HTTPAuthorizationCredentials(scheme=scheme, credentials=token)
            )
        except HTTPException:
            return main_module, None, _ff_json({"detail": "Oturum gerekli."}, 401)
        return main_module, user, None
    from app import main as main_module

    user = main_module.get_current_user(request)
    if not user:
        return main_module, None, _ff_json({"detail": "Oturum gerekli."}, 401)
    return main_module, user, None


@contextmanager
def _ff_engine_guard():
    """Sağlayıcı ve motor hatalarını güvenli Türkçe 503'e çevirir.

    HTTPException (400/429 gibi) olduğu gibi geçer; kimlik ve doğrulama
    yanıtları etkilenmez.
    """
    try:
        yield
    except HTTPException:
        raise
    except FFUnavailable as exc:
        logger.warning("Foto Fikir sağlayıcı kullanılamıyor: %r", exc)
        raise HTTPException(status_code=503, detail=FOTO_FIKIR_UNAVAILABLE) from exc
    except (json.JSONDecodeError, KeyError, TypeError, ValueError, IndexError, AttributeError) as exc:
        logger.warning("Foto Fikir motoru hatası: %r", exc)
        raise HTTPException(status_code=503, detail=FOTO_FIKIR_UNAVAILABLE) from exc


def _ff_throttle(main_module, user_id: int, action: str, *, limit: int, window: int = 60) -> None:
    """AI maliyeti doğuran uçlarda kullanıcı başına hız sınırı (ekonomik DoS koruması)."""
    try:
        admit(main_module.engine, "ff-" + action, str(user_id), limit=limit, window=window)
    except HTTPException as exc:
        if exc.status_code == 429:
            exc.detail = "Çok hızlı istek yapıyorsunuz; kısa bir süre sonra tekrar deneyin."
        raise


@contextmanager
def _ff_ai_budget(user_id: int):
    """Kullanıcı başına eşzamanlı Anthropic çağrısını ve istek bütçelerini sınırlar."""
    try:
        with provider_budget.reservation("anthropic", FOTO_FIKIR_CLAUDE_MODEL, account_scope=f"foto-fikir:{user_id}"):
            yield
    except provider_budget.ProviderBusy as exc:
        raise HTTPException(status_code=429, detail="Üretim hattı şu anda dolu; kısa bir süre sonra tekrar deneyin.") from exc


def _ff_clean(value, limit: int) -> str:
    text = str(value or "").strip()
    return text[:limit]


def _ff_safe_attr(obj, name: str) -> Optional[str]:
    value = getattr(obj, name, None)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


# ---------------------------------------------------------------------------
# Mock görsel motoru (Pillow)
# ---------------------------------------------------------------------------

FF_IMAGE_WIDTH = 1080
FF_IMAGE_HEIGHT = 1350
FF_NAVY_DEEP = (7, 26, 49)
FF_NAVY_MID = (24, 53, 91)
FF_ICE = (218, 228, 240)
FF_WHITE = (255, 255, 255)
FF_AMBER = (233, 168, 76)

# Türkçe glif (ş, ğ, ı, İ) desteği olan font tercih edilir; NotoSansSC bu
# harfleri kağıt kutusu (tofu) olarak çizer, bu yüzden listede yine de
# glif kontrolünden geçmesi şarttır.
_FF_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/chinese/NotoSansSC-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]
_FF_TURKISH_CHARS = "şŞğĞıİçÇöÖüÜ"


def _ff_font_file() -> Optional[str]:
    for path in _FF_FONT_CANDIDATES:
        if _ff_font_supports_turkish(path):
            return path
    return None


def _ff_font(size: int) -> ImageFont.FreeTypeFont:
    path = _ff_font_file()
    if path:
        try:
            return ImageFont.truetype(path, size)
        except Exception:  # noqa: BLE001 - bozuk font kaydında varsayılana düş
            pass
    return ImageFont.load_default()


def _ff_font_supports_turkish(path: str) -> bool:
    """Fontun Türkçe harfleri ayrı ayrı çizebildiğini test eder (tofu avcısı)."""
    cached = _FF_TURKISH_FONT_CACHE.get(path)
    if cached is not None:
        return cached
    ok = False
    try:
        font = ImageFont.truetype(path, 48)
        boxes = [font.getmask(ch).getbbox() for ch in _FF_TURKISH_CHARS]
        distinct = {box for box in boxes if box is not None}
        ok = len(distinct) >= len(_FF_TURKISH_CHARS) - 2
    except Exception:
        ok = False
    _FF_TURKISH_FONT_CACHE[path] = ok
    return ok


_FF_TURKISH_FONT_CACHE: dict = {}


def _ff_wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int, max_lines: int) -> List[str]:
    words = [word for word in (text or "").split() if word]
    lines: List[str] = []
    current = ""
    overflow = False
    for word in words:
        candidate = (current + " " + word).strip()
        if draw.textlength(candidate, font=font) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
            if len(lines) >= max_lines:
                overflow = True
                break
    if current and len(lines) < max_lines:
        lines.append(current)
    if overflow and lines:
        # Son satır taşarsa en son kelimeyi düşürüp üç nokta ekle.
        last = lines[-1]
        last_words = last.split()
        while last_words and draw.textlength(" ".join(last_words) + "…", font=font) > max_width:
            last_words = last_words[:-1]
        lines[-1] = (" ".join(last_words) + "…").strip() or last
    return lines


def _ff_mock_image(topic: str, headline: str, style_name: str) -> bytes:
    """1080x1350 lacivert degrade zeminli örnek karusel görseli üretir."""
    image = Image.new("RGB", (FF_IMAGE_WIDTH, FF_IMAGE_HEIGHT), FF_NAVY_DEEP)
    draw = ImageDraw.Draw(image)
    top, bottom = FF_NAVY_DEEP, FF_NAVY_MID
    for y in range(FF_IMAGE_HEIGHT):
        t = y / (FF_IMAGE_HEIGHT - 1)
        draw.line(
            (
                0,
                y,
                FF_IMAGE_WIDTH,
                y,
            ),
            fill=(
                int(top[0] + (bottom[0] - top[0]) * t),
                int(top[1] + (bottom[1] - top[1]) * t),
                int(top[2] + (bottom[2] - top[2]) * t),
            ),
        )
    kicker_font = _ff_font(44)
    headline_font = _ff_font(84)
    style_font = _ff_font(38)

    kicker = _ff_clean(topic, 64) or "Foto Fikir"
    kicker_y = 150
    draw.text((90, kicker_y), kicker, font=kicker_font, fill=FF_ICE)
    draw.line((90, kicker_y + 74, 90 + min(820, int(draw.textlength(kicker, font=kicker_font)) + 30), kicker_y + 76), fill=FF_AMBER, width=6)

    headline_lines = _ff_wrap(draw, _ff_clean(headline, 120) or "Başlık", headline_font, FF_IMAGE_WIDTH - 180, 3)
    line_height = 104
    start_y = (FF_IMAGE_HEIGHT - line_height * len(headline_lines)) // 2 - 40
    for index, line in enumerate(headline_lines):
        draw.text((90, start_y + index * line_height), line, font=headline_font, fill=FF_WHITE)

    band_top = FF_IMAGE_HEIGHT - 190
    draw.rectangle((0, band_top, FF_IMAGE_WIDTH, FF_IMAGE_HEIGHT), fill=(11, 35, 65))
    draw.text((90, band_top + 62), _ff_clean(style_name, 48) or "Sade Klinik", font=style_font, fill=FF_ICE)
    draw.ellipse((FF_IMAGE_WIDTH - 130, band_top + 56, FF_IMAGE_WIDTH - 90, band_top + 96), outline=FF_AMBER, width=5)

    buffer = BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def foto_fikir_overlay_name(png: bytes, display_name: str) -> bytes:
    """Sağ alt köşeye yarı opak şerit üzerinde hekim adını basar; çıktı PNG."""
    if not (display_name or "").strip():
        return png
    image = Image.open(BytesIO(png)).convert("RGBA")
    if image.width > 1080:
        ratio = 1080 / image.width
        image = image.resize((1080, max(1, int(image.height * ratio))), Image.LANCZOS)
    name = _ff_clean(display_name, 48)
    name_font = _ff_font(40)
    measure = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    text_width = int(measure.textlength(name, font=name_font))
    pad_x, pad_y = 26, 16
    band_w = min(image.width - 24, text_width + pad_x * 2)
    band_h = 74
    band_box = (image.width - band_w - 24, image.height - band_h - 24, image.width - 24, image.height - 24)
    strip = Image.new("RGBA", image.size, (0, 0, 0, 0))
    strip_draw = ImageDraw.Draw(strip)
    strip_draw.rounded_rectangle(band_box, radius=14, fill=(11, 35, 65, 168))
    image = Image.alpha_composite(image, strip)
    draw = ImageDraw.Draw(image)
    draw.text(
        (band_box[0] + pad_x, band_box[1] + pad_y - 2),
        name,
        font=name_font,
        fill=(255, 255, 255, 235),
    )
    buffer = BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Gerçek sağlayıcılar (repo desenleri: Claude metin, Gemini görsel)
# ---------------------------------------------------------------------------

def _ff_json_object(raw: str) -> Optional[dict]:
    text = (raw or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        text = text.strip("`").lstrip("json").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _ff_claude_text(prompt: str, *, max_tokens: int = 1600, system: Optional[str] = None) -> str:
    """Metin üretimi Claude messages API üzerinden; repo study_anthropic deseni."""
    api_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        raise FFUnavailable("ANTHROPIC_API_KEY tanımlı değil.")
    payload = {
        "model": FOTO_FIKIR_CLAUDE_MODEL,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        payload["system"] = system
    request = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        method="POST",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=FF_PROVIDER_TIMEOUT) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("Foto Fikir Claude hatası model=%s error=%r", FOTO_FIKIR_CLAUDE_MODEL, exc)
        raise FFUnavailable("Metin sağlayıcısı yanıt vermedi.") from exc
    text = "".join(
        block.get("text", "")
        for block in result.get("content", [])
        if isinstance(block, dict) and block.get("type") == "text"
    ).strip()
    if not text:
        raise FFUnavailable("Metin sağlayıcısı boş yanıt döndürdü.")
    return text


def _ff_gemini_image(prompt: str, reference_parts: Optional[list] = None) -> bytes:
    """Görsel üretimi Gemini image modelleri üzerinden sırayla denenir."""
    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key:
        raise FFUnavailable("GEMINI_API_KEY tanımlı değil.")
    parts = list(reference_parts or [])
    parts.append({"text": prompt})
    last_error: Optional[Exception] = None
    for model in FF_GEMINI_IMAGE_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        payload = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"responseModalities": ["IMAGE"]},
        }
        request = urllib.request.Request(
            url,
            method="POST",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        )
        try:
            with urlopen(request, timeout=FF_PROVIDER_TIMEOUT) as response:
                result = json.loads(response.read().decode("utf-8"))
            candidate = (result.get("candidates") or [{}])[0]
            for part in candidate.get("content", {}).get("parts", []):
                inline = part.get("inlineData") if isinstance(part, dict) else None
                data_b64 = (inline or {}).get("data")
                if data_b64:
                    return base64.b64decode(data_b64)
            last_error = FFUnavailable("Model görsel parçası döndürmedi.")
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            logger.warning("Foto Fikir Gemini görsel hatası model=%s error=%r", model, exc)
            last_error = exc
    raise FFUnavailable(f"Görsel sağlayıcısı başarısız oldu ({last_error!r}).")


def _ff_brand_photo_paths(main_module, user_id: int) -> List[Path]:
    root = Path(main_module.UPLOAD_DIR) / FF_UPLOAD_ROOT / str(user_id)
    if not root.is_dir():
        return []
    photos = [
        item for item in root.iterdir()
        if item.is_file() and item.name.startswith(FF_BRAND_PREFIX)
        and item.suffix.lower() in (".png", ".jpg", ".jpeg")
    ]
    photos.sort(key=lambda item: item.stat().st_mtime)
    return photos


def _ff_brand_photo_urls(main_module, user_id: int) -> List[str]:
    return [_ff_image_url(str(path)) for path in _ff_brand_photo_paths(main_module, user_id)]


def _ff_storage_ensure_local(path: Path) -> Path:
    if _ff_storage is None:
        if not path.is_file():
            raise FileNotFoundError(str(path))
        return path
    return _ff_storage.ensure_local(path)


def _ff_storage_write_bytes(path: Path, data: bytes, *, content_type: str) -> str:
    if _ff_storage is None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return str(path)
    return _ff_storage.write_bytes(path, data, content_type=content_type)


def _ff_brand_reference_parts(main_module, user_id: int, limit: int = FF_BRAND_MAX_FILES) -> list:
    """Marka kiti fotoğraflarını Gemini inlineData referans parçalarına çevirir."""
    parts = []
    for path in _ff_brand_photo_paths(main_module, user_id)[:limit]:
        try:
            local = _ff_storage_ensure_local(path)
            data = local.read_bytes()
            if len(data) > FF_BRAND_FILE_LIMIT:
                continue
            mime = "image/png" if local.suffix.lower() == ".png" else "image/jpeg"
            parts.append({"inlineData": {"mimeType": mime, "data": base64.b64encode(data).decode("ascii")}})
        except Exception as exc:  # noqa: BLE001 - okunamayan referans atlanır
            logger.warning("Foto Fikir marka kiti referansı okunamadı path=%s error=%r", path.name, exc)
    return parts


FF_STYLE_ART_DIRECTIONS = {
    "Sade Klinik": "temiz beyaz arka plan, ince koyu gri tipografi, minimal klinik estetik",
    "Derin Lacivert": "koyu lacivert degrade zemin, beyaz başlık tipografisi, kurumsal güven tonu",
    "Nane Esintisi": "açık nane yeşili vurgular, ferah beyaz zemin, yumuşak köşeler",
    "Yumuşak Gül": "pastel gül rengi arka plan, sıcak ve davetkâr tıbbi estetik",
    "Mum Işığı": "sıcak amber ışık vurgusu, yumuşak gölgeli krem zemin",
    "Mermer Doku": "açık mermer dokusu, ince altın ayraç çizgileri, zarif seri",
    "İki Renk": "iki zıt renk bloğu, güçlü kontrastlı başlık alanı",
    "Yumuşak Gölge": "katmanlı kartlar, yumuşak derinlik gölgeleri, açık gri zemin",
    "Su Çizgisi": "ince mavi dalgalı çizgi süslemeleri, akışkan açık zemin",
    "Kağıt Katmanı": "üst üste kağıt katmanları, hafif el yapımı doku hissi",
    "Gece Neon": "gece koyusu zemin, konturlu neon çizgi vurguları",
    "Işık Odağı": "merkezde spot ışık, kenarlarda yumuşak karartma",
    "Toprak Tonları": "kum ve kil tonlarında doğal sıcak palet",
    "Cam Saydam": "buğulu cam panel efektleri, hafif saydam katmanlar",
    "Defter Çizgi": "çizgili defter zemin, el yazısı tarzı vurgular",
}


def _ff_default_visual_prompt(topic: str, style: dict, slide: dict, draft: Optional[dict] = None) -> str:
    """Slayt için varsayılan görsel yönergeleri; Claude taslağı varsa zenginleşir."""
    direction = FF_STYLE_ART_DIRECTIONS.get(style.get("name", ""), FF_STYLE_ART_DIRECTIONS["Sade Klinik"])
    headline = _ff_clean(slide.get("headline") or topic, 120)
    body = _ff_clean(slide.get("body") or "", 220)
    prompt = (
        "Diş hekimliği hastası için bilgilendirici sosyal medya görseli tasarla. "
        f"Arka plan: {direction}. Görselde yazı üretme; yalnızca görsel kompozisyon kullan. "
        f"Konu: {_ff_clean(topic, 120)}. Slayt başlığı: {headline}."
    )
    if body:
        prompt += f" Slayt metni: {body}."
    if draft:
        composition = _ff_clean(draft.get("composition"), 300)
        if composition:
            prompt += f" Kompozisyon notu: {composition}."
    prompt += " Diş sağlığı temasına uygun, profesyonel, hasta dostu ve sade bir illüstrasyon."
    return prompt


def _ff_visual_prompt_drafts(topic: str, style: dict, slides: List[dict]) -> dict:
    """Claude'dan slayt başına kompozisyon taslağı ister; hata olursa boş döner."""
    if not _ff_has_claude():
        return {}
    listing = json.dumps(
        [{"index": index, "headline": _ff_clean(slide.get("headline"), 120)} for index, slide in enumerate(slides)],
        ensure_ascii=False,
    )
    prompt = (
        "Bir diş hekimi için karusel görsel kompozisyon taslağı hazırla. Konu: "
        f"{_ff_clean(topic, 120)}. Görsel stil: {style.get('name')}. Slaytlar: {listing}\n"
        'Yalnızca şu JSON biçimini döndür: {"slides": [{"index": 0, "composition": "tek cümle kompozisyon notu"}]}'
    )
    data = _ff_json_object(_ff_claude_text(prompt, max_tokens=800))
    if not data:
        return {}
    drafts = {}
    for item in data.get("slides") or []:
        if isinstance(item, dict) and isinstance(item.get("index"), int) and item.get("composition"):
            drafts[item["index"]] = {"composition": str(item["composition"])}
    return drafts


# ---------------------------------------------------------------------------
# Mock içerik havuzları (özgün Türkçe diş hekimliği eğitimi)
# ---------------------------------------------------------------------------

_FF_IDEA_TEMPLATES = [
    {
        "title": "{topic}: yaygın 3 yanlışı ayıklayalım",
        "angle": "Hastaların en çok inandığı yanlış bilgileri tek tek düzeltir; kaydırma sırasında tatmin edici bir seri kurar.",
        "hook": "\"Bunu hâlâ yapıyorsanız durun\" diyerek açılır.",
    },
    {
        "title": "{topic} konusunda ilk 24 saat",
        "angle": "Zaman çizelgesi biçiminde ilerler; hasta için neyin normal, neyin acele başvuru gerektirdiğini ayırır.",
        "hook": "\"Bugün yaptıklarınız, yarın hissetikleriniz\" cümlesiyle kurar.",
    },
    {
        "title": "Hastalar bize {topic} için ne soruyor?",
        "angle": "Gerçek muayene sorularından derlenmiş bir soru-cevap serisi; her kartta tek soru ve kısa yanıt.",
        "hook": "En sık duyulan soruyu alıntılayarak başlar.",
    },
    {
        "title": "{topic} için sabah ve akşam rutini",
        "angle": "Günlük alışkanlıkları iki basit listeye böler; takip edilebilir görsel adımlar sunar.",
        "hook": "\"İki dakikalık rutin, uzun vadeli fark\" vaadiyle açar.",
    },
    {
        "title": "{topic} ne zaman uzman işidir?",
        "angle": "Evde yapılabileceklerle mutlaka klinik değerlendirme gerektiren durumları net biçimde ayırır.",
        "hook": "\"Kendiniz çözebilirsiniz ama şu durumda bize gelin\" dengesi kurar.",
    },
]


def _ff_mock_ideas(topic_hint: str) -> List[dict]:
    topic = _ff_clean(topic_hint, 120) or "ağız ve diş sağlığı"
    ideas = []
    for template in _FF_IDEA_TEMPLATES:
        ideas.append({
            "title": template["title"].format(topic=topic),
            "angle": template["angle"],
            "hook": template["hook"],
        })
    return ideas


_FF_SLIDE_STRUCTURES = [
    {
        "headline": "{topic} neden önemli?",
        "body": "Ağız sağlığı, genel sağlığın görünür penceresidir. {topic} konusunda bilinçli olmak, küçük sorunları büyük tedavilerden önce yakalar.",
        "note": "Açılış kartı: okuyucuyu konuya bağlayan tek cümle.",
    },
    {
        "headline": "Bilmeniz gereken 3 temel adım",
        "body": "Günde iki kez iki dakika fırçalama, günde bir kez diş ipi ve düzenli kontrol. {topic} bakımının temeli bu üç alışkanlığa dayanır.",
        "note": "Adımları numaralı listeye dönüştürebilirsiniz.",
    },
    {
        "headline": "En sık yapılan hatalar",
        "body": "Sert fırçalama diş etini geri çeker; aceleyle yıkanan macuna fluor kalır. {topic} bakımında doğru teknik, doğru üründen önce gelir.",
        "note": "Hata kartlarında telkin dili yerine gözlem dili kullanın.",
    },
    {
        "headline": "Hangi durumda hekime gelmeli?",
        "body": "İki günden uzun süren hassasiyet, kanayan diş eti veya ağzınızda iyileşmeyen yara varsa muayene geciktirilmemelidir.",
        "note": "Acil başvuru eşiğini netleştirin; korku dili kullanmayın.",
    },
    {
        "headline": "Efsane mi, gerçek mi?",
        "body": "Ağrı geçince tedavi bitermiş gibi görünse de sorun kaynağı sürer. {topic} hakkındaki efsaneleri tek tek ayıklamak tedavi süresini kısaltır.",
        "note": "Efsane/gerçek ikilisi karuselde iyi kaydırma oranı verir.",
    },
    {
        "headline": "Çocuklarda fark ne olur?",
        "body": "Süt dişleri kalıcı dişlerin yerini hazırlar. {topic} alışkanlıkları okul çağında kazanılır; aile düzeni en güçlü etkenidir.",
        "note": "Aile hedefli içerikte ebeveyn tonunu yumuşak tutun.",
    },
    {
        "headline": "Kontrol aralığı ne olmalı?",
        "body": "Çoğu yetişkin için altı ayda bir kontrol yeterlidir; risk grubundaki hastalar için hekim kısa aralık önerebilir. Takviminize not edin.",
        "note": "Kliniğinize uygun kontrol aralığını buraya yazın.",
    },
    {
        "headline": "Özet: küçük alışkanlıklar, kalıcı fark",
        "body": "{topic} bakımı pahalı ürünlerle değil, düzenli alışkanlıklarla korunur. Bugünden başlayacak tek değişiklik seçin ve sürdürün.",
        "note": "Kapanış kartında tek eylem çağrısı bırakın.",
    },
]

_FF_SLIDE_TONES = {
    "bilgilendirici": "sade ve açık anlatım",
    "samimi": "içten, sohbet havasında anlatım",
    "profesyonel": "resmî ve özlü anlatım",
    "eğitici": "adım adım öğreten anlatım",
}


def _ff_mock_slides(topic: str, slide_count: int, tone: str) -> List[dict]:
    clean_topic = _ff_clean(topic, 120) or "ağız ve diş sağlığı"
    tone_note = _FF_SLIDE_TONES.get(_ff_clean(tone, 40), _FF_SLIDE_TONES["bilgilendirici"])
    slides = []
    for index in range(max(3, min(FF_SLIDE_MAX_COUNT, slide_count))):
        template = _FF_SLIDE_STRUCTURES[index % len(_FF_SLIDE_STRUCTURES)]
        slides.append({
            "headline": _ff_clean(template["headline"].format(topic=clean_topic), 120),
            "body": _ff_clean(template["body"].format(topic=clean_topic), 220),
            "note": f"{tone_note}; {template['note']}",
        })
    return slides


_FF_IG_HIGHLIGHTS = ["Klinik", "Randevu", "Bakım Önerileri", "Yorumlar", "Sık Sorulanlar"]


def _ff_mock_ig() -> dict:
    grid_formats = ("Tek Kare", "Karusel", "Reels")
    grid_ideas = [
        "Sabah fırçalama rutini kartı",
        "Diş ipi adım adım karuseli",
        "Kontrol günü hatırlatması",
        "Hassasiyet neden olur sorusu",
        "Muayene odası tanıtımı",
        "Efsane ve gerçek serisi",
        "Çocuklarda ilk muayene rehberi",
        "Ekip tanıtım karesi",
        "Haftalık soru-cevap kutusu",
    ]
    return {
        "bio": "Ağız ve diş sağlığı odaklı klinik içeriği: günlük bakım önerileri, kontrol hatırlatmaları ve sade eğitim serileri. Randevu: profildeki bağlantı.",
        "highlights": list(_FF_IG_HIGHLIGHTS),
        "grid_plan": [
            {"idea": idea, "format": grid_formats[index % len(grid_formats)]}
            for index, idea in enumerate(grid_ideas)
        ],
    }


_FF_REELS_SCENARIO = [
    ("0-3 sn", "Konuyu soruyla aç: {topic} hakkında ilk aklınıza gelen yanlış nedir?"),
    ("3-8 sn", "Kısa cevap verin; yanlışı tek cümleyle düzeltin."),
    ("8-20 sn", "Uygulamayı kameraya yakın gösterin; iki adımı yavaşça tekrar edin."),
    ("20-35 sn", "Sık yapılan hatayı adıyla söyleyin ve doğru halini karşılaştırın."),
    ("35-45 sn", "Tek cümlelik özetle kapatın ve kaydet çağrısı yapın."),
]

_FF_REELS_CAPCUT = [
    "Sesi netleştirin; arka plan gürültüsünü azaltın.",
    "En iyi üç cümleyi seçip kaba kurguyu 45 saniyeye indirin.",
    "İlk üç saniyeye büyük punto altyazı ekleyin.",
    "Uygulama anına yakın plan için kamera kaydını bölün.",
    "Geçişlerde tek stil geçişi kullanın; sıçramalı kesim yeterlidir.",
    "Altyazıları satır satır senkronize edin.",
    "Sessiz bölümlerde hafif fon müziği düşürün.",
    "Kapak karesini manuel seçin ve konu metnini yazın.",
]


def _ff_mock_reels(topic: str) -> dict:
    clean_topic = _ff_clean(topic, 120) or "ağız ve diş sağlığı"
    hooks = [
        f"{clean_topic} konusunda bu hatayı hâlâ yapıyor musunuz?",
        f"{clean_topic} için iki dakikada doğru rutin",
        f"Hastalar bize {clean_topic} için en çok bunu soruyor",
    ]
    return {
        "hooks": hooks,
        "senaryo": [
            {"aralik": aralik, "metin": metin.format(topic=clean_topic)}
            for aralik, metin in _FF_REELS_SCENARIO
        ],
        "capcut_adimlari": list(_FF_REELS_CAPCUT),
    }


# ---------------------------------------------------------------------------
# Dosya ve iş görünüm yardımcıları
# ---------------------------------------------------------------------------

def _ff_save_image(main_module, user_id: int, data: bytes, *, prefix: str = FF_IMAGE_PREFIX, ext: str = ".png") -> str:
    """Görseli UPLOAD_DIR/foto_fikir/{user_id} altına yazar; göreli yolu döndürür."""
    ext = ext if ext.startswith(".") else "." + ext
    target = Path(main_module.UPLOAD_DIR) / FF_UPLOAD_ROOT / str(user_id) / f"{prefix}{uuid.uuid4().hex}{ext}"
    content_type = "image/png" if ext == ".png" else "image/jpeg"
    return _ff_storage_write_bytes(target, data, content_type=content_type)


def _ff_image_url(image_path: Optional[str]) -> Optional[str]:
    if not image_path:
        return None
    parts = Path(image_path).parts
    if len(parts) < 2:
        return None
    return f"/uploads/foto_fikir/{parts[-2]}/{parts[-1]}"


def _ff_job_view(row: FotoFikirJob) -> dict:
    created = getattr(row, "created_at", None)
    if isinstance(created, datetime):
        created_text = created.isoformat(timespec="seconds")
    else:
        created_text = str(created or "")
    return {
        "id": row.id,
        "kind": row.kind,
        "label": FF_KIND_LABELS.get(row.kind, row.kind),
        "topic": row.topic,
        "created_at": created_text,
        "image_url": _ff_image_url(row.image_path) if row.image_path else None,
        "status": row.status,
    }


# ---------------------------------------------------------------------------
# İstek modelleri
# ---------------------------------------------------------------------------

class FFIdeasRequest(BaseModel):
    topic_hint: str = ""


class FFSlidesRequest(BaseModel):
    topic: str = ""
    slide_count: int = 5
    tone: str = "bilgilendirici"


class FFMevzuatRequest(BaseModel):
    texts: List[str] = []


class FFSlideInput(BaseModel):
    headline: str = ""
    body: str = ""


class FFGenerateImageRequest(BaseModel):
    topic: str = ""
    style_id: str = ""
    slides: List[FFSlideInput] = []
    include_name: bool = False


class FFBrandGenerateRequest(BaseModel):
    scene: str = ""


class FFIgRequest(BaseModel):
    pass


class FFReelsRequest(BaseModel):
    topic: str = ""


# ---------------------------------------------------------------------------
# Uçlar (tümü /api/foto-fikir/*, görsel servisi /uploads/*)
# ---------------------------------------------------------------------------

@foto_fikir_router.get("/api/foto-fikir/bootstrap")
def foto_fikir_bootstrap(request: Request):
    main_module, user, auth_error = _ff_auth(request)
    if auth_error:
        return auth_error
    with _ff_engine_guard():
        with main_module.Session(main_module.engine, expire_on_commit=False) as session:
            used = foto_fikir_quota_used(session, user.id)
            recent_rows = session.exec(
                select(FotoFikirJob)
                .where(FotoFikirJob.user_id == user.id)
                .order_by(FotoFikirJob.created_at.desc(), FotoFikirJob.id.desc())
                .limit(6)
            ).all()
            specialty = _ff_safe_attr(user, "specialty")
            unvan = _ff_safe_attr(user, "unvan")
            doctor_profile_cls = getattr(main_module, "DoctorProfile", None)
            if doctor_profile_cls is not None:
                try:
                    profile_row = session.get(doctor_profile_cls, user.id)
                    if profile_row is not None:
                        specialty = specialty or _ff_safe_attr(profile_row, "specialty")
                        if getattr(profile_row, "is_specialist", False) and not unvan:
                            unvan = "Uzman Diş Hekimi"
                except Exception:  # noqa: BLE001 - profil okuma kota ve stili etkilemez
                    pass
        brand_urls = _ff_brand_photo_urls(main_module, user.id)
        return _ff_json({
            "profile": {
                "display_name": _ff_safe_attr(user, "display_name") or _ff_safe_attr(user, "username") or "Hekim",
                "unvan": unvan,
                "specialty": specialty,
            },
            "styles": FF_STYLES,
            "quota": {"used": used, "limit": FOTO_FIKIR_QUOTA_LIMIT, "period": "ay"},
            "brand_kit": {"exists": bool(brand_urls), "photos_count": len(brand_urls), "photos": brand_urls},
            "recent": [_ff_job_view(row) for row in reversed(recent_rows)],
            **_ff_mock_flag(_ff_mock()),
        })


@foto_fikir_router.post("/api/foto-fikir/ideas")
def foto_fikir_ideas(request: Request, body: FFIdeasRequest):
    main_module, user, auth_error = _ff_auth(request)
    if auth_error:
        return auth_error
    with _ff_engine_guard():
        _ff_throttle(main_module, user.id, "ideas", limit=10)
        topic = _ff_clean(body.topic_hint, 200)
        mock = _ff_mock()
        if mock:
            ideas = _ff_mock_ideas(topic)
            provider, model = "mock", "mock"
        else:
            if not _ff_has_claude():
                raise FFUnavailable("ANTHROPIC_API_KEY tanımlı değil.")
            prompt = (
                "Bir diş hekiminin sosyal medya içerik fikirlerini hazırla. Konu ipucu: "
                f"{topic or 'ağız ve diş sağlığı'}. Beş fikir üret; her fikir hasta eğitimi amaçlı, "
                "mevzuata uygun (garanti, üstünlük ve kampanya iddiası yok) olsun.\n"
                'Yalnızca şu JSON biçimini döndür: {"ideas": [{"title": "...", "angle": "...", "hook": "..."}]}'
            )
            with _ff_ai_budget(user.id):
                data = _ff_json_object(_ff_claude_text(prompt, system=CREATIVE_DIRECTOR_BRIEF)) or {}
            ideas = data.get("ideas") or []
            if len(ideas) < 3:
                raise FFUnavailable("Fikir sağlayıcısının yanıtı okunamadı.")
            ideas = ideas[:5]
            provider, model = "claude+local", FOTO_FIKIR_CLAUDE_MODEL
        creative_audit = audit_creative_output("IDEA", ideas)
        _ff_record_job(main_module, user.id, "IDEA", topic, {"ideas": ideas, "creative_audit": creative_audit}, provider=provider, model=model)
        return _ff_json({
            "ideas": ideas,
            "creative_audit": creative_audit,
            "tips": actionable_tips(creative_audit),
            **_ff_mock_flag(mock),
        })


@foto_fikir_router.post("/api/foto-fikir/slides")
def foto_fikir_slides(request: Request, body: FFSlidesRequest):
    main_module, user, auth_error = _ff_auth(request)
    if auth_error:
        return auth_error
    with _ff_engine_guard():
        _ff_throttle(main_module, user.id, "slides", limit=10)
        topic = _ff_clean(body.topic, 200)
        slide_count = body.slide_count
        if slide_count < 3 or slide_count > FF_SLIDE_MAX_COUNT:
            raise HTTPException(status_code=400, detail="Slayt sayısı 3 ile 8 arasında olmalı.")
        tone = _ff_clean(body.tone, 40) or "bilgilendirici"
        mock = _ff_mock()
        if mock:
            slides = _ff_mock_slides(topic, slide_count, tone)
            provider, model = "mock", "mock"
        else:
            if not _ff_has_claude():
                raise FFUnavailable("ANTHROPIC_API_KEY tanımlı değil.")
            prompt = (
                f"Diş hekimliği hastası için {slide_count} kartlık karusel metni yaz. Konu: {topic or 'ağız ve diş sağlığı'}. "
                f"Ton: {tone}. Her kart 120 karakteri geçmeyen başlık ve 220 karakteri geçmeyen gövde metni içersin; "
                "mevzuata uygun yaz (garanti, üstünlük, kampanya iddiası yok; öncesi/sonrası karşılaştırması yok).\n"
                'Yalnızca şu JSON biçimini döndür: {"slides": [{"headline": "...", "body": "...", "note": "..."}]}'
            )
            with _ff_ai_budget(user.id):
                data = _ff_json_object(_ff_claude_text(prompt, system=CREATIVE_DIRECTOR_BRIEF)) or {}
            slides = data.get("slides") or []
            if len(slides) < 3:
                raise FFUnavailable("Slayt sağlayıcısının yanıtı okunamadı.")
            slides = [
                {
                    "headline": _ff_clean(slide.get("headline"), 120),
                    "body": _ff_clean(slide.get("body"), 220),
                    "note": _ff_clean(slide.get("note"), 200) or None,
                }
                for slide in slides[:slide_count]
            ]
            provider, model = "claude+local", FOTO_FIKIR_CLAUDE_MODEL
        roles = story_arc_roles(len(slides))
        for slide, role in zip(slides, roles):
            slide["role"] = role
        _ff_record_job(main_module, user.id, "SLIDES", topic, {"slides": slides}, provider=provider, model=model)
        return _ff_json({"slides": slides, **_ff_mock_flag(mock)})


@foto_fikir_router.post("/api/foto-fikir/mevzuat-check")
def foto_fikir_mevzuat_check(request: Request, body: FFMevzuatRequest):
    main_module, user, auth_error = _ff_auth(request)
    if auth_error:
        return auth_error
    with _ff_engine_guard():
        _ff_throttle(main_module, user.id, "mevzuat", limit=30)
        texts = [(_ff_clean(text, 300) if isinstance(text, str) else "") for text in body.texts][:FF_MEVZUAT_MAX_TEXTS]
        results = []
        for index, text in enumerate(texts):
            found = mevzuat_local_check(text)
            if found is None:
                results.append({"index": index, "text": text, "level": "OK", "reason": "", "suggestion": ""})
            else:
                results.append({"index": index, "text": text, "level": found["level"], "reason": found["reason"], "suggestion": found["suggestion"]})
        for result in results:
            if result["level"] in ("DIKKAT", "KALDIR"):
                result["creative_alternative"] = safe_rewrite_suggestion(result["text"])
        _ff_record_job(
            main_module, user.id, "MEVZUAT", texts[0][:120] if texts else "", {"results": results},
            provider="local", model="yerel-kurallar",
        )
        return _ff_json({"results": results, "disclaimer": FOTO_FIKIR_MEVZUAT_DISCLAIMER})


@foto_fikir_router.post("/api/foto-fikir/generate-image")
def foto_fikir_generate_image(request: Request, body: FFGenerateImageRequest):
    main_module, user, auth_error = _ff_auth(request)
    if auth_error:
        return auth_error
    with _ff_engine_guard():
        _ff_throttle(main_module, user.id, "generate", limit=3)
        topic = _ff_clean(body.topic, 200)
        style = FF_STYLE_MAP.get(_ff_clean(body.style_id, 60)) or FF_STYLES[0]
        if len(body.slides or []) > FF_SLIDE_MAX_COUNT:
            raise HTTPException(status_code=400, detail="En fazla 8 slayt gönderilebilir.")
        slides = []
        for item in (body.slides or [])[:FF_SLIDE_MAX_COUNT]:
            slide = {"headline": _ff_clean(item.headline, 120), "body": _ff_clean(item.body, 220)}
            if slide["headline"] or slide["body"]:
                slides.append(slide)
        if not topic and not slides:
            raise HTTPException(status_code=400, detail="Konu ve en az bir slayt metni gerekli.")
        if not slides:
            slides = [{"headline": topic, "body": ""}]
        with main_module.Session(main_module.engine, expire_on_commit=False) as session:
            used = foto_fikir_quota_used(session, user.id)
        _ff_check_quota(used)
        _ff_t0 = time.perf_counter()
        mock = _ff_mock()
        display_name = _ff_safe_attr(user, "display_name") or ""
        paths: List[str] = []
        skipped = 0
        if mock:
            for slide in slides:
                png = _ff_mock_image(topic, slide["headline"] or topic, style["name"])
                if body.include_name and display_name:
                    png = foto_fikir_overlay_name(png, display_name)
                paths.append(_ff_save_image(main_module, user.id, png))
        else:
            if not _ff_has_gemini():
                raise FFUnavailable("GEMINI_API_KEY tanımlı değil.")
            with _ff_ai_budget(user.id):
                drafts = _ff_visual_prompt_drafts(topic, style, slides)
            prompts: List[str] = []
            for index, slide in enumerate(slides):
                try:
                    prompts.append(creative_prompt_for_slide(topic, style["id"], slide))
                except Exception:  # noqa: BLE001 - yönetmen prompt'u kurulamazsa varsayılan yönergeler
                    prompts.append(_ff_default_visual_prompt(topic, style, slide, drafts.get(index)))
            # Slayt görselleri paralel üretilir (ThreadPoolExecutor, stdlib);
            # sonuç sırası slayt sırasını korur, tek slayt hatası işi düşürmez.
            with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(len(prompts), 4))) as pool:
                futures = [pool.submit(_ff_gemini_image, prompt) for prompt in prompts]
                for future in futures:
                    try:
                        png = future.result()
                    except Exception as exc:  # noqa: BLE001 - tek slayt hatası diğer görselleri korur
                        skipped += 1
                        logger.warning("Foto Fikir slayt görseli üretilemedi, atlandı: %r", exc)
                        continue
                    if body.include_name and display_name:
                        png = foto_fikir_overlay_name(png, display_name)
                    paths.append(_ff_save_image(main_module, user.id, png))
        uretim_ms = int((time.perf_counter() - _ff_t0) * 1000)
        creative_audit = audit_creative_output("IMAGE", {"topic": topic, "slides": slides, "style": style["id"]})
        recommendation = recommend_style(topic)
        tips = actionable_tips(creative_audit)
        payload = {
            "slides": slides,
            "style": style["name"],
            "include_name": body.include_name,
            "image_paths": paths,
            "uretim_ms": uretim_ms,
            "skipped": skipped,
            "style_recommendation": recommendation,
            "tips": tips,
            "creative_audit": creative_audit,
        }
        job_id = _ff_record_job(
            main_module, user.id, "IMAGE", topic, payload,
            image_path=paths[0] if paths else None,
            style_id=style["id"],
            provider="mock" if mock else "claude+local+gemini",
            model="mock" if mock else f"{FOTO_FIKIR_CLAUDE_MODEL}+{FF_GEMINI_IMAGE_MODELS[0] if FF_GEMINI_IMAGE_MODELS else 'gemini'}",
        )
        urls = [_ff_image_url(path) for path in paths]
        response_data = {
            "job_id": job_id,
            "image_url": urls[0] if urls else None,
            "images": urls,
            "style": style["name"],
            "quota": {"used": used + max(1, len(paths)), "limit": FOTO_FIKIR_QUOTA_LIMIT, "period": "ay"},
            "creative_audit": payload["creative_audit"],
            "style_recommendation": recommendation,
            "tips": tips,
            "uretim_ms": uretim_ms,
            "skipped": skipped,
            **_ff_mock_flag(mock),
        }
        if _ff_clean(body.style_id, 60):
            # Hekimin stili korundu; yönetmen önerisi ayrıca "suggestion" olarak iletilir.
            response_data["suggestion"] = recommendation
        if skipped:
            response_data["uyari"] = (
                "Görsel sağlayıcısı tüm slaytlar için yanıt vermedi; iş kaydedildi, tekrar deneyin."
                if skipped >= len(slides)
                else f"{skipped} slayt görseli üretilemedi; diğer slaytlar üretildi."
            )
        return _ff_json(response_data)


@foto_fikir_router.post("/api/foto-fikir/brand-kit")
def foto_fikir_brand_kit(request: Request, files: List[UploadFile] = File(...)):
    main_module, user, auth_error = _ff_auth(request)
    if auth_error:
        return auth_error
    with _ff_engine_guard():
        _ff_throttle(main_module, user.id, "brand-upload", limit=6)
        if len(files) > FF_BRAND_MAX_FILES:
            raise HTTPException(status_code=400, detail="En fazla 3 fotoğraf yükleyin.")
        saved = 0
        for item in files:
            data = item.file.read(FF_BRAND_FILE_LIMIT + 1)
            if not data:
                raise HTTPException(status_code=400, detail="Fotoğraf boş görünüyor; yeniden deneyin.")
            if len(data) > FF_BRAND_FILE_LIMIT:
                raise HTTPException(status_code=400, detail="Fotoğraflar en fazla 8 MB olabilir.")
            name = _ff_clean(item.filename, 120).lower()
            mime = (item.content_type or "").lower()
            if mime == "image/png" or name.endswith(".png"):
                ext = ".png"
            elif mime in ("image/jpeg", "image/jpg") or name.endswith((".jpg", ".jpeg")):
                ext = ".jpg"
            else:
                raise HTTPException(status_code=400, detail="Yalnızca PNG veya JPEG fotoğraf yükleyin.")
            try:
                probe = Image.open(BytesIO(data))
                probe.verify()
            except Exception as exc:
                raise HTTPException(status_code=400, detail="Fotoğraf okunamadı; PNG veya JPEG deneyin.") from exc
            _ff_save_image(main_module, user.id, data, prefix=FF_BRAND_PREFIX, ext=ext)
            saved += 1
        urls = _ff_brand_photo_urls(main_module, user.id)
        return _ff_json({
            "exists": True,
            "photos_count": len(urls),
            "photos": urls,
            "saved": saved,
            **_ff_mock_flag(_ff_mock()),
        })


@foto_fikir_router.post("/api/foto-fikir/brand-kit/generate")
def foto_fikir_brand_generate(request: Request, body: FFBrandGenerateRequest):
    main_module, user, auth_error = _ff_auth(request)
    if auth_error:
        return auth_error
    with _ff_engine_guard():
        _ff_throttle(main_module, user.id, "brand-generate", limit=3)
        scene = _ff_clean(body.scene, 80)
        if scene not in FOTO_FIKIR_SCENES:
            raise HTTPException(status_code=400, detail="Geçerli bir sahne seçin.")
        if not _ff_brand_photo_paths(main_module, user.id):
            raise HTTPException(status_code=400, detail="Önce marka kiti fotoğrafı yükleyin.")
        with main_module.Session(main_module.engine, expire_on_commit=False) as session:
            used = foto_fikir_quota_used(session, user.id)
        _ff_check_quota(used)
        _ff_t0 = time.perf_counter()
        mock = _ff_mock()
        reason = "referanslı"
        if mock:
            png = _ff_mock_image(scene, scene, "Marka Kiti")
        else:
            if not _ff_has_gemini():
                raise FFUnavailable("GEMINI_API_KEY tanımlı değil.")
            references = _ff_brand_reference_parts(main_module, user.id)
            prompt = (
                "Marka kitindeki gerçek kişiye sadık kal; yüzü değiştirme, görselde yazı üretme. "
                f"Klinik ortamında şu sahneyi doğal ışıkla tasarla: {scene}. "
                "Profesyonel diş hekimliği görseli, hasta dostu kompozisyon."
            )
            if references:
                png = _ff_gemini_image(prompt, reference_parts=references)
                reason = "referanslı"
            else:
                png = _ff_gemini_image(_ff_default_visual_prompt(scene, FF_STYLES[0], {"headline": scene, "body": ""}))
                reason = "referanssız"
        image_path = _ff_save_image(main_module, user.id, png)
        uretim_ms = int((time.perf_counter() - _ff_t0) * 1000)
        job_id = _ff_record_job(
            main_module, user.id, "BRAND", scene, {"scene": scene, "reason": reason, "uretim_ms": uretim_ms},
            image_path=image_path,
            provider="mock" if mock else "gemini",
            model="mock" if mock else (FF_GEMINI_IMAGE_MODELS[0] if FF_GEMINI_IMAGE_MODELS else "gemini"),
        )
        return _ff_json({
            "job_id": job_id,
            "image_url": _ff_image_url(image_path),
            "scene": scene,
            "reason": reason,
            "uretim_ms": uretim_ms,
            "quota": {"used": used + 1, "limit": FOTO_FIKIR_QUOTA_LIMIT, "period": "ay"},
            **_ff_mock_flag(mock),
        })


@foto_fikir_router.post("/api/foto-fikir/ig-profile")
def foto_fikir_ig_profile(request: Request, body: FFIgRequest):
    main_module, user, auth_error = _ff_auth(request)
    if auth_error:
        return auth_error
    with _ff_engine_guard():
        _ff_throttle(main_module, user.id, "ig", limit=5)
        mock = _ff_mock()
        if mock:
            plan = _ff_mock_ig()
            provider, model = "mock", "mock"
        else:
            if not _ff_has_claude():
                raise FFUnavailable("ANTHROPIC_API_KEY tanımlı değil.")
            prompt = (
                "Bir diş hekimi kliniği için Instagram profil planı hazırla. 150 karakteri geçmeyen bio, "
                "5 öne çıkan albüm adı ve 9 gönderilik ızgara planı öner; mevzuata uygun dil kullan.\n"
                'Yalnızca şu JSON biçimini döndür: {"bio": "...", "highlights": ["..."], '
                '"grid_plan": [{"idea": "...", "format": "Tek Kare|Karusel|Reels"}]}'
            )
            with _ff_ai_budget(user.id):
                plan = _ff_json_object(_ff_claude_text(prompt)) or {}
            if not plan.get("bio") or len(plan.get("highlights") or []) < 3 or len(plan.get("grid_plan") or []) < 6:
                raise FFUnavailable("Instagram planı sağlayıcısının yanıtı okunamadı.")
            provider, model = "claude+local", FOTO_FIKIR_CLAUDE_MODEL
        _ff_record_job(main_module, user.id, "IG", "Instagram profili", {"plan": plan}, provider=provider, model=model)
        return _ff_json({**plan, **_ff_mock_flag(mock)})


@foto_fikir_router.post("/api/foto-fikir/reels")
def foto_fikir_reels(request: Request, body: FFReelsRequest):
    main_module, user, auth_error = _ff_auth(request)
    if auth_error:
        return auth_error
    with _ff_engine_guard():
        _ff_throttle(main_module, user.id, "reels", limit=5)
        topic = _ff_clean(body.topic, 200)
        if not topic:
            raise HTTPException(status_code=400, detail="Reels konusu gerekli.")
        mock = _ff_mock()
        if mock:
            plan = _ff_mock_reels(topic)
            provider, model = "mock", "mock"
        else:
            if not _ff_has_claude():
                raise FFUnavailable("ANTHROPIC_API_KEY tanımlı değil.")
            prompt = (
                f"Diş hekimliği konusu için kısa video çekim planı hazırla: {topic}. Üç kanca cümlesi, "
                "saniye aralıklı senaryo (aralik + metin) ve sekiz adımlı kurgu listesi (CapCut) öner; mevzuata uygun yaz.\n"
                'Yalnızca şu JSON biçimini döndür: {"hooks": ["..."], "senaryo": [{"aralik": "0-3 sn", "metin": "..."}], '
                '"capcut_adimlari": ["..."]}'
            )
            with _ff_ai_budget(user.id):
                plan = _ff_json_object(_ff_claude_text(prompt, system=CREATIVE_DIRECTOR_BRIEF)) or {}
            if len(plan.get("hooks") or []) < 2 or not plan.get("senaryo") or len(plan.get("capcut_adimlari") or []) < 4:
                raise FFUnavailable("Reels planı sağlayıcısının yanıtı okunamadı.")
            provider, model = "claude+local", FOTO_FIKIR_CLAUDE_MODEL
        for row in plan.get("senaryo") or []:
            if isinstance(row, dict):
                row["shot"] = reel_shot_plan(topic, str(row.get("aralik") or ""), str(row.get("metin") or ""))
        plan["creative_audit"] = audit_creative_output(
            "REELS", {"topic": topic, "hooks": plan.get("hooks") or [], "senaryo": plan.get("senaryo") or []}
        )
        plan["tips"] = actionable_tips(plan["creative_audit"])
        _ff_record_job(main_module, user.id, "REELS", topic, {"plan": plan}, provider=provider, model=model)
        return _ff_json({**plan, **_ff_mock_flag(mock)})


@foto_fikir_router.get("/api/foto-fikir/history")
def foto_fikir_history(request: Request):
    main_module, user, auth_error = _ff_auth(request)
    if auth_error:
        return auth_error
    with _ff_engine_guard():
        with main_module.Session(main_module.engine, expire_on_commit=False) as session:
            rows = session.exec(
                select(FotoFikirJob)
                .where(FotoFikirJob.user_id == user.id)
                .order_by(FotoFikirJob.created_at.desc(), FotoFikirJob.id.desc())
                .limit(20)
            ).all()
        return _ff_json({"jobs": [_ff_job_view(row) for row in reversed(rows)]})


@foto_fikir_router.get("/uploads/foto_fikir/{owner_id}/{name}")
def foto_fikir_upload(request: Request, owner_id: int, name: str):
    main_module, user, auth_error = _ff_auth(request)
    if auth_error:
        return auth_error
    if getattr(user, "id", None) != owner_id:
        return _ff_json({"detail": "Bu görseli görüntüleme yetkiniz yok."}, 403)
    if not _FF_UPLOAD_NAME_RE.fullmatch(name or ""):
        return _ff_json({"detail": "Dosya bulunamadı."}, 404)
    target = Path(main_module.UPLOAD_DIR) / FF_UPLOAD_ROOT / str(owner_id) / name
    try:
        local = _ff_storage_ensure_local(target)
    except Exception as exc:  # noqa: BLE001 - eksik nesne ve depolama hatası aynı kapıdan döner
        logger.warning("Foto Fikir görseli bulunamadı name=%s error=%r", name, exc)
        return _ff_json({"detail": "Dosya bulunamadı."}, 404)
    suffix = Path(local).suffix.lower()
    if suffix == ".png":
        media = "image/png"
    elif suffix in (".jpg", ".jpeg"):
        media = "image/jpeg"
    else:
        return _ff_json({"detail": "Dosya bulunamadı."}, 404)
    return FileResponse(Path(local), media_type=media, headers={"Cache-Control": "private, no-store"})

