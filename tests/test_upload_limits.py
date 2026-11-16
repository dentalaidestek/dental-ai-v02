from io import BytesIO
from pathlib import Path

import pytest
from starlette.exceptions import HTTPException

from app.upload_io import copy_image, upload_size, validate_path_batch, validate_upload_batch
from app.request_limits import RequestLimits, request_body_limit
from app.upload_limits import (
    MAX_ANALYSIS_BATCH_BYTES,
    MAX_ANALYSIS_IMAGE_BYTES,
    MAX_PATIENT_MEDIA_BATCH_BYTES,
    MAX_PATIENT_MEDIA_FILE_BYTES,
)


class FakeUpload:
    def __init__(self, payload: bytes):
        self.file = BytesIO(payload)
        self.size = len(payload)
        self.headers = {"content-length": "1"}  # Deliberately untrusted.


def test_shared_contract_values_are_bounded_and_binary():
    assert MAX_PATIENT_MEDIA_FILE_BYTES == 12 * 1024 * 1024
    assert MAX_PATIENT_MEDIA_BATCH_BYTES == 96 * 1024 * 1024
    assert MAX_ANALYSIS_IMAGE_BYTES == 15 * 1024 * 1024
    assert MAX_ANALYSIS_BATCH_BYTES == 48 * 1024 * 1024


def test_upload_size_uses_actual_parser_count_not_content_length():
    upload = FakeUpload(b"x" * 4096)
    assert upload_size(upload) == 4096


def test_upload_batch_accepts_exact_file_and_total_boundaries():
    uploads = [FakeUpload(b"a" * MAX_ANALYSIS_IMAGE_BYTES),
               FakeUpload(b"b" * (MAX_ANALYSIS_BATCH_BYTES - MAX_ANALYSIS_IMAGE_BYTES))]
    assert validate_upload_batch(
        uploads, maximum_file=MAX_ANALYSIS_BATCH_BYTES,
        maximum_total=MAX_ANALYSIS_BATCH_BYTES,
    ) == MAX_ANALYSIS_BATCH_BYTES


def test_upload_batch_rejects_per_file_and_aggregate_overflow():
    with pytest.raises(HTTPException) as per_file:
        validate_upload_batch([FakeUpload(b"x" * 5)], maximum_file=4, maximum_total=20)
    assert per_file.value.status_code == 413

    with pytest.raises(HTTPException) as aggregate:
        validate_upload_batch([FakeUpload(b"x" * 6), FakeUpload(b"y" * 5)],
                              maximum_file=10, maximum_total=10)
    assert aggregate.value.status_code == 413


def test_path_batch_counts_real_private_file_sizes(tmp_path: Path):
    first, second = tmp_path / "one.jpg", tmp_path / "two.jpg"
    first.write_bytes(b"a" * 5)
    second.write_bytes(b"b" * 7)
    assert validate_path_batch([first, second], maximum_file=7, maximum_total=12) == 12
    with pytest.raises(HTTPException) as exc:
        validate_path_batch([first, second], maximum_file=7, maximum_total=11)
    assert exc.value.status_code == 413


def test_bounded_copy_removes_partial_destination_on_overflow(tmp_path: Path):
    destination = tmp_path / "partial.jpg"
    with pytest.raises(HTTPException) as exc:
        copy_image(BytesIO(b"x" * 9), destination, maximum=8)
    assert exc.value.status_code == 413
    assert not destination.exists()


def test_raw_http_body_limits_cover_multipart_overhead_and_respect_global_cap():
    global_limit = 128 * 1024 * 1024
    archive = request_body_limit({"method": "POST", "path": "/patients/12/media"}, global_limit)
    analysis = request_body_limit({"method": "POST", "path": "/analysis/new/12"}, global_limit)
    mobile_analysis = request_body_limit({"method": "POST", "path": "/api/mobile/v1/analyses"}, global_limit)
    mobile_archive = request_body_limit({"method": "POST", "path": "/api/mobile/v1/patients/12/media"}, global_limit)
    assert archive == MAX_PATIENT_MEDIA_BATCH_BYTES + 256 * 1024
    assert analysis == MAX_ANALYSIS_BATCH_BYTES + 256 * 1024
    assert mobile_analysis == analysis
    assert mobile_archive == MAX_PATIENT_MEDIA_FILE_BYTES + 256 * 1024
    assert request_body_limit({"method": "POST", "path": "/analysis/new/12"}, 32 * 1024 * 1024) == 32 * 1024 * 1024
    assert request_body_limit({"method": "GET", "path": "/patients/12/media"}, global_limit) == global_limit


@pytest.mark.asyncio
async def test_asgi_body_counter_rejects_chunked_or_understated_multipart_body():
    from app.upload_limits import MAX_PATIENT_MEDIA_FILE_BYTES

    sent = []
    async def downstream(scope, receive, send):
        await receive()

    async def receive():
        return {"type": "http.request", "body": b"x" * (MAX_PATIENT_MEDIA_FILE_BYTES + 300 * 1024), "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http", "method": "POST", "path": "/api/mobile/v1/patients/1/media",
        "headers": [
            (b"content-type", b"multipart/form-data; boundary=test"),
            (b"content-length", b"1"),
        ],
    }
    middleware = RequestLimits(downstream, max_bytes=128 * 1024 * 1024)
    with pytest.raises(HTTPException) as exc:
        await middleware(scope, receive, send)
    assert exc.value.status_code == 413
