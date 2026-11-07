import io
import pytest
from PIL import Image
from app import expert_social_safety as safety
from app import expert_publications as publications


@pytest.mark.parametrize(
    "url",
    [
        "http://example.org",
        "https://127.0.0.1",
        "https://[::1]",
        "https://169.254.169.254/latest",
        "https://user:pass@example.org",
        "https://example.org:8000",
        "https://localhost",
        "javascript:alert(1)",
        "https://example.org\\@127.0.0.1",
    ],
)
def test_unsafe_urls_rejected(url):
    with pytest.raises(ValueError):
        safety.safe_url(url)


@pytest.mark.parametrize(
    "address",
    [
        "10.0.0.1",
        "127.0.0.1",
        "169.254.169.254",
        "::1",
        "::ffff:127.0.0.1",
        "100.64.0.1",
    ],
)
def test_dns_cannot_return_private_addresses(address):
    with pytest.raises(ValueError):
        safety.public_addresses([address])


def test_preview_parses_html_without_executing_it():
    p = safety.parse_preview(
        "https://example.org/p",
        '<title>Fallback</title><meta property="og:title" content="Makale &amp; çalışma"><meta property="og:image" content="/cover.png"><meta name="description" content="Bilimsel özet">',
    )
    assert p["title"] == "Makale & çalışma"
    assert p["image_url"] == "https://example.org/cover.png"
    assert p["description"] == "Bilimsel özet"


@pytest.mark.parametrize(
    "content,expected",
    [
        ("Bilimsel görüşe katılmıyorum; nekroz riski tartışılmalı.", "PUBLISHED"),
        ("Hastamız Ayşe Yılmaz, telefon 0532 123 45 67", "PENDING"),
        ("iletişim: hasta@example.org", "PENDING"),
        ("T.C. 12345678901", "PENDING"),
        ("Protokol no: 82764", "PENDING"),
        ("Seni öldüreceğim", "REJECTED"),
        ("Bu bir aptal yorumu", "PENDING"),
        ("%100 kesin tedavi garantisi", "PENDING"),
    ],
)
def test_moderation(content, expected):
    assert safety.moderate(content)[0] == expected


def test_any_image_requires_review():
    assert safety.moderate("Konferans afişi", has_images=True)[0] == "PENDING"


def test_reencode_strips_exif_and_limits_dimensions():
    img = Image.new("RGB", (3000, 800))
    exif = img.getexif()
    exif[270] = "Patient Name"
    b = io.BytesIO()
    img.save(b, format="JPEG", exif=exif)
    clean = safety.clean_image(b.getvalue())
    output = Image.open(io.BytesIO(clean))
    assert max(output.size) <= 2048
    assert not output.getexif()


def test_svg_is_not_an_image_upload():
    with pytest.raises(ValueError):
        safety.clean_image(b'<svg onload="alert(1)"/>')


def test_orcid_checksum_and_doi_normalization():
    assert (
        publications.normalize_orcid("https://orcid.org/0000-0002-1825-0097")
        == "0000-0002-1825-0097"
    )
    with pytest.raises(ValueError):
        publications.normalize_orcid("0000-0002-1234-5678")
    assert publications.normalize_doi("https://doi.org/10.1000/AbC") == "10.1000/abc"


def test_orcid_grouped_summary_missing_fields_not_fabricated():
    data = {
        "group": [
            {
                "work-summary": [
                    {
                        "put-code": 17,
                        "visibility": "public",
                        "title": {"title": {"value": "Bir çalışma"}},
                        "external-ids": {
                            "external-id": [
                                {
                                    "external-id-type": "doi",
                                    "external-id-value": "10.1000/ABC",
                                    "external-id-relationship": "self",
                                }
                            ]
                        },
                        "publication-date": {"year": {"value": "2025"}},
                        "journal-title": {"value": "Dergi"},
                    }
                ]
            },
            {"work-summary": []},
        ]
    }
    rows = publications.parse_orcid(data)
    assert len(rows) == 1
    assert rows[0]["title"] == "Bir çalışma"
    assert rows[0]["year"] == 2025
    assert rows[0]["doi"] == "10.1000/abc"
    assert rows[0]["authors"] == ""


@pytest.mark.parametrize(
    "text", ["SİKTİR", "Hasta Ahmet Yılmaz 34 yaşında", "Ha\u200bstamız: Örnek"]
)
def test_turkish_case_and_invisible_characters_cannot_bypass_triage(text):
    assert safety.moderate(text)[0] != "PUBLISHED"


def test_dns_rebinding_and_mixed_public_private_answers_are_rejected(monkeypatch):
    import asyncio, socket

    async def run():
        async def answers(*args, **kwargs):
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
            ]

        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", answers)
        with pytest.raises(ValueError):
            await safety.PublicResolver().resolve("example.org", 443)

    asyncio.run(run())
