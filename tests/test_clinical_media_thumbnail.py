from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
import threading
import time

import pytest
from PIL import Image

from app import clinical_media_thumbnail as thumbnails


def _jpeg(path: Path, size=(1200, 600)) -> bytes:
    image = Image.new("RGB", size, (120, 80, 40))
    image.save(path, format="JPEG")
    return path.read_bytes()


def test_thumbnail_reference_is_deterministic_and_preserves_r2_scheme():
    assert thumbnails.thumbnail_reference("uploads/patient_7_abcd.jpg") == "uploads/patient_7_abcd.thumb.jpg"
    assert thumbnails.thumbnail_reference("r2://uploads/patient_7_abcd.jpg") == "r2://uploads/patient_7_abcd.thumb.jpg"
    with pytest.raises(ValueError):
        thumbnails.thumbnail_reference("")


def test_thumbnail_is_bounded_jpeg_and_original_is_unchanged(tmp_path, monkeypatch):
    original = tmp_path / "original.png"
    original_bytes = _jpeg(original)
    derivative = tmp_path / "original.thumb.jpg"
    references = {str(original): original, str(derivative): derivative}
    writes = []

    def ensure_local(reference):
        path = references.get(str(reference))
        if path is None or not path.exists():
            raise FileNotFoundError(str(reference))
        return path

    def write_bytes(reference, payload, *, content_type=None):
        path = Path(reference)
        path.write_bytes(payload)
        references[str(reference)] = path
        writes.append((str(reference), content_type))

    monkeypatch.setattr(thumbnails.object_storage, "ensure_local", ensure_local)
    monkeypatch.setattr(thumbnails.object_storage, "write_bytes", write_bytes)
    result = thumbnails.ensure_thumbnail(original)

    with Image.open(result) as generated:
        assert generated.format == "JPEG"
        assert generated.size == (480, 240)
    assert original.read_bytes() == original_bytes
    assert writes == [(str(derivative), "image/jpeg")]


def test_concurrent_thumbnail_requests_share_one_generation(tmp_path, monkeypatch):
    original = tmp_path / "scan.jpg"
    _jpeg(original)
    derivative = tmp_path / "scan.thumb.jpg"
    references = {str(original): original, str(derivative): derivative}
    writes = []
    guard = threading.Lock()

    def ensure_local(reference):
        path = references.get(str(reference))
        if path is None or not path.exists():
            raise FileNotFoundError(str(reference))
        return path

    def write_bytes(reference, payload, *, content_type=None):
        time.sleep(0.03)
        path = Path(reference)
        path.write_bytes(payload)
        references[str(reference)] = path
        with guard:
            writes.append(str(reference))

    monkeypatch.setattr(thumbnails.object_storage, "ensure_local", ensure_local)
    monkeypatch.setattr(thumbnails.object_storage, "write_bytes", write_bytes)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: thumbnails.ensure_thumbnail(original), range(8)))

    assert len(results) == 8
    assert all(path == derivative for path in results)
    assert writes == [str(derivative)]


def test_storage_failure_is_not_converted_to_missing_media(tmp_path, monkeypatch):
    original = tmp_path / "r2-source.jpg"
    _jpeg(original)

    def ensure_local(reference):
        if str(reference).endswith(".thumb.jpg"):
            raise FileNotFoundError(str(reference))
        return original

    def fail_write(*args, **kwargs):
        raise RuntimeError("synthetic R2 timeout")

    monkeypatch.setattr(thumbnails.object_storage, "ensure_local", ensure_local)
    monkeypatch.setattr(thumbnails.object_storage, "write_bytes", fail_write)
    with pytest.raises(RuntimeError, match="R2 timeout"):
        thumbnails.ensure_thumbnail("r2://uploads/r2-source.jpg")


def test_thumbnail_route_and_gallery_use_private_owner_scoped_derivatives():
    from pathlib import Path

    api = Path("app/mobile_modern_api_v3.py").read_text(encoding="utf-8")
    native = Path("mobile/src/NativePatientMedia.tsx").read_text(encoding="utf-8")
    route = api[api.index("def mobile_media_thumbnail"):api.index("@router.get(\"/patients/{patient_id}/media/{media_id}\")", api.index("def mobile_media_thumbnail"))]
    assert "patient.owner_user_id != user.id" in route
    assert "current_media.file_path == file_path" in route
    assert "_private_clinical_media_error(404" in route
    assert '"Cache-Control": "private, no-store"' in api
    assert '"Vary": "Authorization"' in api
    assert 'item.thumbnail_url||item.url' in native
    assert "preview.url" in native



def test_web_and_native_delete_paths_enqueue_thumbnail_cleanup():
    from pathlib import Path

    main = Path("app/main.py").read_text(encoding="utf-8")
    mobile = Path("app/mobile_api.py").read_text(encoding="utf-8")
    single_delete = main[main.index("def delete_patient_media"):main.index("def delete_all_patient_media")]
    bulk_delete = main[main.index("def delete_all_patient_media"):main.index("@app.get(\"/analyses\"")]
    native_delete = mobile[mobile.index("def mobile_delete_patient_media"):mobile.index("@router.get(\"/patients/{patient_id}/media/{media_id}/file\")")]

    assert "thumbnail_reference(file_path)" in single_delete
    assert "enqueue_patient_media_cleanup(s, thumbnail_path)" in single_delete
    assert "thumbnail_reference(media.file_path)" in bulk_delete
    assert "enqueue_patient_media_cleanup(s, thumbnail_path)" in bulk_delete
    assert "thumbnail_reference(file_path)" in native_delete
    assert "enqueue_patient_media_cleanup(session, thumbnail_path)" in native_delete



def test_single_flight_lock_registry_is_released_after_waiters_finish(tmp_path, monkeypatch):
    original = tmp_path / "lock.jpg"
    _jpeg(original)
    derivative = tmp_path / "lock.thumb.jpg"

    def ensure_local(reference):
        path = Path(reference)
        if not path.exists():
            raise FileNotFoundError(str(reference))
        return path

    def write_bytes(reference, payload, *, content_type=None):
        Path(reference).write_bytes(payload)

    monkeypatch.setattr(thumbnails.object_storage, "ensure_local", ensure_local)
    monkeypatch.setattr(thumbnails.object_storage, "write_bytes", write_bytes)
    thumbnails.ensure_thumbnail(original)
    assert str(derivative) not in thumbnails._locks


def test_thumbnail_endpoint_rechecks_owner_after_generation():
    from pathlib import Path

    api = Path("app/mobile_modern_api_v3.py").read_text(encoding="utf-8")
    start = api.index("def mobile_media_thumbnail")
    end = api.index("@router.get(\"/patients/{patient_id}/media/{media_id}\")", start)
    block = api[start:end]
    assert "still_owned = bool(" in block
    assert "_cleanup_orphan_thumbnail(delete_thumbnail, file_path, media_id)" in block
    assert "current_media.file_path == file_path" in block


def test_web_patient_gallery_uses_private_thumbnail_route_and_bounded_cursor_pages():
    from pathlib import Path

    main = Path("app/main.py").read_text(encoding="utf-8")
    template = Path("app/templates/patient_detail.html").read_text(encoding="utf-8")
    detail = main[main.index('def patient_detail('):main.index('MAX_PATIENT_MEDIA_UPLOAD_FILES')]
    page = main[main.index('def patient_media_gallery_page'):main.index('@app.get("/patients/{patient_id}/media/{media_id}/thumbnail")')]
    thumbnail = main[main.index('def patient_media_thumbnail'):main.index('@app.post("/patients/{patient_id}/media/{media_id}/delete")')]

    assert "CLINICAL_MEDIA_GALLERY_PAGE_SIZE + 1" in detail
    assert "patient_media_total" in detail
    assert "patient_media_next_before" in detail
    assert "get_current_user(request)" in page
    assert "PatientMedia.owner_user_id == media_owner_id" in page
    assert "PatientMedia.id < before_id" in page
    assert "order_by(PatientMedia.id.desc())" in page
    assert "serialize_media_page(rows, patient_id" in page
    assert '"Cache-Control": "private, no-store"' in page
    assert '"Vary": "Cookie"' in page

    assert "get_current_user(request)" in thumbnail
    assert "ensure_thumbnail(reference)" in thumbnail
    assert "current_media.file_path == reference" in thumbnail
    assert "delete_thumbnail(reference)" in thumbnail
    assert '"Cache-Control": "private, no-store"' in thumbnail
    assert '"Vary": "Cookie"' in thumbnail

    assert 'data-src="/patients/{{ patient.id }}/media/{{ media.id }}/file"' in template
    assert 'src="/patients/{{ patient.id }}/media/{{ media.id }}/thumbnail"' in template
    assert 'data-url="/patients/{{ patient.id }}/media/page"' in template
    assert 'patient_media_total - 3' in template

def test_native_media_list_and_metadata_responses_are_private_after_route_deduplication():
    from pathlib import Path

    mobile = Path("app/mobile_api.py").read_text(encoding="utf-8")
    api = Path("app/mobile_modern_api_v3.py").read_text(encoding="utf-8")
    main = Path("app/main.py").read_text(encoding="utf-8")

    list_start = mobile.index('@router.get("/patients/{patient_id}/media")')
    list_end = mobile.index('@router.delete("/patients/{patient_id}/media/{media_id}")', list_start)
    active_list_route = mobile[list_start:list_end]

    meta_start = api.index('@router.get("/patients/{patient_id}/media/{media_id}")')
    meta_end = api.index('@router.get("/notifications")', meta_start)
    active_meta_route = api[meta_start:meta_end]

    assert "_mobile_private_no_store(response)" in active_list_route
    assert "patient.owner_user_id != user.id" in active_list_route
    assert "PatientMedia.owner_user_id == user.id" in active_list_route
    assert "response.headers.update(_PRIVATE_CLINICAL_MEDIA_HEADERS)" in active_meta_route
    assert "_user_owned_patient(s,user,patient_id)" in active_meta_route
    assert "row.owner_user_id!=user.id" in active_meta_route

    # The primary mobile_api router is mounted first. The registry removes
    # colliding methods from the v3 candidate router, not from the primary.
    assert main.index("app.include_router(mobile_router)") < main.index(
        "_remove_shadowed_mobile_routes((mobile_router, mobile_analysis_router), mobile_modern_router)"
    ) < main.index("app.include_router(mobile_modern_router)")

    for header in (
        '"Cache-Control": "private, no-store"',
        '"Pragma": "no-cache"',
        '"Vary": "Authorization"',
        '"X-Content-Type-Options": "nosniff"',
    ):
        assert header in api
    assert "_mobile_private_no_store" in mobile

