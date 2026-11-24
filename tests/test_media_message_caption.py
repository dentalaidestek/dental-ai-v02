"""Text+attachment single-message (caption) contract tests.

Native clients may send text together with an attachment through the shared
media-message handler. The optional caption must stay backward compatible:
legacy (captionless) receipt payload hashes stay byte-identical, and the web
template renders captions for IMAGE/VOICE bubbles.
"""
import ast
import re
from pathlib import Path

import pytest

from app.main import _consultation_message_payload_hash

MAIN = Path("app/main.py").read_text(encoding="utf-8")
MOBILE_API = Path("app/mobile_api.py").read_text(encoding="utf-8")
ROOM = Path("app/templates/expert_case_room.html").read_text(encoding="utf-8")
STYLE = Path("app/static/style.css").read_text(encoding="utf-8")


def test_captionless_media_hash_stays_identical_for_replay():
    raw = b"binary-image-bytes"
    legacy_payload = {
        "case_id": 7, "sender_user_id": 3, "message_type": "IMAGE",
        "content": "", "reply_to_message_id": None,
        "media_sha256": __import__("hashlib").sha256(raw).hexdigest(),
    }
    import hashlib, json
    legacy = hashlib.sha256(json.dumps(legacy_payload, ensure_ascii=False, sort_keys=True,
                                       separators=(",", ":")).encode("utf-8")).hexdigest()
    assert _consultation_message_payload_hash(7, 3, "IMAGE", "x.jpg", None, raw) == legacy
    assert _consultation_message_payload_hash(7, 3, "IMAGE", "x.jpg", None, raw, caption=None) == legacy
    assert _consultation_message_payload_hash(7, 3, "IMAGE", "x.jpg", None, raw, caption="   ") == legacy


def test_captioned_media_hash_is_distinct_and_length_capped():
    raw = b"binary-image-bytes"
    plain = _consultation_message_payload_hash(7, 3, "IMAGE", "x.jpg", None, raw)
    captioned = _consultation_message_payload_hash(7, 3, "IMAGE", "x.jpg", None, raw, caption="Merhaba, 2. görselde kırık var.")
    assert captioned != plain
    # A caption longer than the 4000 cap hashes like its capped prefix.
    long_caption = "m" * 5000
    assert (_consultation_message_payload_hash(7, 3, "IMAGE", "x.jpg", None, raw, caption=long_caption)
            == _consultation_message_payload_hash(7, 3, "IMAGE", "x.jpg", None, raw, caption="m" * 4000))


def _handler_params(source: str):
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "expert_support_media_message":
            return [a.arg for a in node.args.args]
    raise AssertionError("expert_support_media_message handler not found")


def test_media_message_handler_takes_optional_content_field():
    params = _handler_params(MAIN)
    assert "content" in params
    assert "content: Optional[str] = Form(None)" in MAIN
    # Caption is normalized before any storage work and enforces the same
    # limits as the text endpoint.
    assert 'caption_text = (content or "").strip()' in MAIN
    assert 'len(caption_text) > 4000' in MAIN
    assert '_contains_profanity(caption_text)' in MAIN


def test_both_payload_hash_calls_receive_caption():
    calls = [n for n in ast.walk(ast.parse(MAIN))
             if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == "_consultation_message_payload_hash"
             and any(kw.arg == "caption" for kw in n.keywords)]
    assert len(calls) == 2, "pre-upload and post-upload replay checks must both hash the caption"


def test_media_message_content_prefers_caption_over_filename():
    assert "content=caption_text or safe_filename" in MAIN


def test_mobile_adapter_accepts_and_forwards_caption():
    assert "content: Optional[str] = Form(None)" in MOBILE_API
    dispatch = re.search(r"_mobile_chat_dispatch\(\s*web\.expert_support_media_message[^)]*client_key, content,\s*\)", MOBILE_API)
    assert dispatch, "mobile attachment adapter must forward the optional caption"


def test_web_template_renders_media_captions():
    assert "mediaCaption(" in ROOM
    # Server-rendered IMAGE and VOICE bubbles show the caption only when the
    # content is not a bare filename (legacy rows store the filename there).
    assert ROOM.count('not m.content.lower().endswith(') >= 2
    assert "chat-media-caption" in STYLE
