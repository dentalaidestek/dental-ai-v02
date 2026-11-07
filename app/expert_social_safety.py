"""Bounded network and media handling. No clinical content is sent to AI providers."""

from __future__ import annotations
import asyncio
import io
import ipaddress
import re
import socket
import unicodedata
import warnings
from html.parser import HTMLParser
from urllib.parse import urlsplit, urljoin, urlunsplit
import aiohttp
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_IMAGE_BYTES = 8 * 1024 * 1024


def safe_url(value: str) -> str:
    value = value.strip()
    if len(value) > 2048 or re.search(r"[\x00-\x20\\]", value):
        raise ValueError("Geçerli bir HTTPS bağlantısı girin.")
    try:
        p = urlsplit(value)
        host = (p.hostname or "").encode("idna").decode("ascii").lower().rstrip(".")
        if (
            p.scheme != "https"
            or not host
            or p.username
            or p.password
            or p.port not in (None, 443)
        ):
            raise ValueError()
        try:
            public_addresses([host])
        except ValueError:
            # A DNS name is allowed here; its resolved addresses are checked at connect time.
            try:
                ipaddress.ip_address(host)
            except ValueError:
                pass
            else:
                raise
        if (
            "." not in host
            or host.endswith((".localhost", ".local", ".internal"))
            or host in ("metadata.google.internal",)
        ):
            raise ValueError()
        if not re.fullmatch(r"[a-z0-9.-]+", host) and ":" not in host:
            raise ValueError()
        netloc = "[" + host + "]" if ":" in host else host
        return urlunsplit(("https", netloc, p.path or "/", p.query, ""))
    except (ValueError, UnicodeError) as exc:
        raise ValueError("Güvenli bir HTTPS bağlantısı girin.") from exc


def public_addresses(addresses):
    if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
        raise ValueError("Özel ağ adreslerine erişilemez.")
    return addresses


class PublicResolver(aiohttp.abc.AbstractResolver):
    async def resolve(self, host, port=0, family=socket.AF_INET):
        rows = await asyncio.get_running_loop().getaddrinfo(
            host, port, type=socket.SOCK_STREAM
        )
        public_addresses([r[4][0] for r in rows])
        return [
            dict(hostname=host, host=r[4][0], port=port, family=r[0], proto=0, flags=0)
            for r in rows
        ]

    async def close(self):
        pass


async def fetch_bytes(url: str, *, limit=512 * 1024, accept="text/html", timeout=6):
    """Resolve once through a validating resolver; connect to that exact public IP.

    No env proxy, cookies, credentials or automatic redirects. Revalidate each
    redirect and literal IP as aiohttp can bypass resolvers for IP URLs.
    """
    url = safe_url(url)
    connector = aiohttp.TCPConnector(
        resolver=PublicResolver(), use_dns_cache=False, limit=2
    )
    async with aiohttp.ClientSession(
        connector=connector,
        trust_env=False,
        timeout=aiohttp.ClientTimeout(total=timeout),
        auto_decompress=False,
    ) as client:
        for _ in range(4):
            url = safe_url(url)
            async with client.get(
                url,
                allow_redirects=False,
                headers={
                    "Accept": accept,
                    "User-Agent": "DentalAI-Profile/1.0",
                    "Accept-Encoding": "identity",
                },
            ) as response:
                if response.status in (301, 302, 303, 307, 308):
                    url = safe_url(urljoin(url, response.headers.get("Location", "")))
                    continue
                if response.status != 200:
                    raise ValueError("Kaynak şu an kullanılamıyor.")
                if response.headers.get("Content-Encoding", "identity").lower() not in (
                    "",
                    "identity",
                ):
                    raise ValueError("Sıkıştırılmış yanıt desteklenmiyor.")
                if response.content_length and response.content_length > limit:
                    raise ValueError("Kaynak boyut sınırını aşıyor.")
                data = bytearray()
                async for chunk in response.content.iter_chunked(16384):
                    data.extend(chunk)
                    if len(data) > limit:
                        raise ValueError("Kaynak boyut sınırını aşıyor.")
                return bytes(data), response.headers.get("Content-Type", ""), url
    raise ValueError("Çok fazla yönlendirme.")


class Metadata(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta = {}
        self.title = []
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta":
            key = (attrs.get("property") or attrs.get("name") or "").lower()
            if key not in self.meta:
                self.meta[key] = attrs.get("content", "")
        if tag == "title":
            self.in_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title.append(data)


def parse_preview(url, html):
    parser = Metadata()
    parser.feed(html)
    meta = parser.meta
    image = None
    if meta.get("og:image"):
        try:
            image = safe_url(urljoin(url, meta["og:image"]))
        except ValueError:
            pass
    return {
        "url": safe_url(url),
        "domain": urlsplit(url).hostname,
        "site_name": meta.get("og:site_name", "")[:120],
        "title": (meta.get("og:title") or "".join(parser.title))[:300],
        "description": (meta.get("og:description") or meta.get("description", ""))[
            :500
        ],
        "image_url": image,
    }


async def preview(url):
    raw, content_type, final = await fetch_bytes(url)
    if "html" not in content_type:
        raise ValueError("Önizleme bulunamadı.")
    return parse_preview(final, raw.decode("utf-8", errors="replace"))


def clean_image(raw: bytes) -> bytes:
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("Görsel en fazla 8 MB olabilir.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as img:
                if (
                    img.format not in ("JPEG", "PNG", "WEBP")
                    or img.width * img.height > 20_000_000
                ):
                    raise ValueError(
                        "JPEG, PNG veya WebP, en fazla 20 megapiksel kullanın."
                    )
                img.load()
                img = ImageOps.exif_transpose(img)
                img.thumbnail((2048, 2048))
                # Reconstruct pixels: do not copy EXIF, GPS, XMP, ICC or PNG text.
                pixels = Image.new("RGB", img.size, "white")
                if img.mode in ("RGBA", "LA") or (
                    img.mode == "P" and "transparency" in img.info
                ):
                    rgba = img.convert("RGBA")
                    pixels.paste(rgba, mask=rgba.getchannel("A"))
                else:
                    pixels.paste(img.convert("RGB"))
                out = io.BytesIO()
                pixels.save(out, "JPEG", quality=86, optimize=True)
                return out.getvalue()
    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise ValueError("Görsel dosyası okunamadı.") from exc


def moderate(content: str, *, has_images=False):
    """Conservative triage, not a legal/clinical verification or anonymizer."""
    t = (
        unicodedata.normalize("NFKC", content)
        .casefold()
        .replace("ı", "i")
        .replace("\u0307", "")
    )
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Cf")
    if re.search(r"öldürece[ğg]im|seni geber|siktir|orospu|am[iı]na|\bpiç\b", t):
        return "REJECTED", ["ABUSE"]
    reasons = []
    if re.search(
        r"\b\d{11}\b|[\w.+-]+@[\w.-]+\.[a-z]{2,}|(?:\+?90[\s()-]*)?0?5\d{2}[\s()-]*\d{3}[\s()-]*\d{2}[\s()-]*\d{2}|(?:hasta(?:m[iı]z|m|n[iı]n)?|protokol|dosya|reçete|randevu)\s*(?:ad[iı]|no|numara|:)|hastam[iı]z\s+[a-zçğıöşü]+\s+[a-zçğıöşü]+",
        t,
    ):
        reasons.append("PRIVACY")
    if (
        re.search(
            r"\b(?:hasta|hastam|hastamiz|hastanin|olgu|vaka|patient)\b|case report|t\.?c\.?\s*(?:kimlik|no)|kimlik numara",
            t,
        )
        and "PRIVACY" not in reasons
    ):
        reasons.append("PRIVACY")
    if has_images:
        reasons.append("IMAGE_REVIEW")
    if re.search(
        r"garanti|%\s*100|yüzde yüz|kesin (?:tedavi|çözüm)|indirim|kampanya|öncesi.{0,10}sonras[iı]|aptal|salak|gerizekal|nefret|iban|bahis",
        t,
    ):
        reasons.append("CONTENT_REVIEW")
    if len(re.findall(r"https?://", t)) > 4 or re.search(r"(.)\1{15,}", t):
        reasons.append("SPAM")
    return ("PENDING" if reasons else "PUBLISHED"), reasons
