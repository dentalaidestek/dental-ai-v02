"""Legal document suite: community rules, function usage guidance, contact.

The 2026-11-25 round adds the Topluluk ve İletişim Kuralları document plus
Hakkımızda/İletişim pages, and folds a lawful-usage guide for every platform
function into the terms. These are product rule texts: they must stay free of
invented facts (no fabricated company details or SLA promises) and must point
at the real support channels (in-app support tickets, destek@dentalai.tr).
"""
from pathlib import Path

from app.legal_texts import LEGAL_TEXTS, LEGAL_VERSION

COMMUNITY = LEGAL_TEXTS["community"]
TERMS = LEGAL_TEXTS["terms"]
PRIVACY = LEGAL_TEXTS["privacy"]


def test_new_documents_are_registered_and_version_bumped():
    assert LEGAL_VERSION >= "2026.11.25"
    for key in ("community", "about", "contact"):
        assert key in LEGAL_TEXTS
    assert LEGAL_TEXTS["community"]["title"] == "Topluluk ve İletişim Kuralları"
    assert LEGAL_TEXTS["about"]["title"] == "Hakkımızda"
    assert LEGAL_TEXTS["contact"]["title"] == "İletişim"


def test_community_rules_cover_harassment_abusive_language_and_enforcement():
    content = COMMUNITY["content"]
    for keyword in (
        "Hakaret", "küfür", "Taciz", "Spam", "Uygunsuz",
        "Yaptırım", "Sorun Bildir", "Destek Talepleri",
        "hastanın kimliğine ilişkin", "nefret söylemi",
    ):
        assert keyword in content, f"community rules must mention {keyword}"
    # Reporting reasons mirror the conversation-row menu contract.
    for reason in ("Taciz, Hakaret veya", "Spam", "Diğer"):
        assert reason in content


def test_terms_explain_every_function_within_legal_boundaries():
    content = TERMS["content"]
    for section in (
        "Platformun İşlevleri ve Doğru Kullanımı",
        "<b>AI Analiz:", "<b>Hasta Kayıtları ve Diş Şeması:", "<b>Sesli Muayene:",
        "<b>Uzmandan Destek", "<b>Akademik AI:", "<b>Foto Fikir", "<b>Dental Akış:",
    ):
        assert section in content
    # The abusive-language rule set is cross-referenced from the terms.
    assert "Topluluk ve İletişim Kuralları" in content
    # No invented identity facts: the placeholder wording stays explicit.
    assert "ticari kullanıma açılmadan önce" in content


def test_privacy_covers_messaging_attachments_and_voice_transcription():
    content = PRIVACY["content"]
    assert "Platform İçi İletişimler, Mesajlar ve Ekler" in content
    assert "yalnızca görüşmenin tarafları" in content
    assert "ham ses ve tam konuşma dökümü hasta dosyasına otomatik" in content.lower()


def test_contact_page_uses_real_channels_only():
    contact = LEGAL_TEXTS["contact"]["content"]
    assert "destek@dentalai.tr" in contact
    assert "Destek Talebi Oluştur" in contact
    assert "Sorun Bildir" in contact


def test_web_index_links_the_new_documents():
    page = Path("app/templates/info_page.html").read_text(encoding="utf-8")
    for href in ("/legal/community", "/legal/about", "/legal/contact"):
        assert f'href="{href}"' in page
