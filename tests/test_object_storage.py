from pathlib import Path
import pytest

from app import object_storage


class FakeR2Client:
    def __init__(self):
        self.objects = {}

    def list_objects_v2(self, *, Bucket, MaxKeys):
        return {"Name": Bucket, "MaxKeys": MaxKeys}

    def upload_file(self, filename, bucket, key, ExtraArgs=None, Config=None):
        self.objects[(bucket, key)] = Path(filename).read_bytes()

    def head_object(self, *, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            from botocore.exceptions import ClientError
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        value = self.objects[(Bucket, Key)]
        return {"ContentLength": len(value)}

    def get_object(self, *, Bucket, Key):
        from io import BytesIO
        return {"Body": BytesIO(self.objects[(Bucket, Key)])}

    def delete_object(self, *, Bucket, Key):
        self.objects.pop((Bucket, Key), None)


def test_local_fallback_writes_plain_upload_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("R2_ENABLED", raising=False)

    reference = object_storage.write_bytes("uploads/example.txt", b"hello")

    assert reference == "uploads/example.txt"
    assert object_storage.exists(reference)
    assert object_storage.ensure_local(reference).read_bytes() == b"hello"


def test_r2_round_trip_restores_missing_local_cache(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("R2_ENABLED", "1")
    fake = FakeR2Client()
    monkeypatch.setattr(object_storage, "_settings", lambda: ("dental-ai-prod", "endpoint", "key", "secret"))
    monkeypatch.setattr(object_storage, "_client", lambda: fake)

    reference = object_storage.write_bytes(
        "uploads/images/panorama.jpg",
        b"radiograph",
        content_type="image/jpeg",
    )
    Path(reference).unlink()

    assert object_storage.exists(reference)
    assert object_storage.size(reference) == len(b"radiograph")
    from app.object_cache import scope
    monkeypatch.setenv("R2_CACHE_DIR", str(tmp_path / "cache"))
    with scope():
        assert object_storage.ensure_local(reference).read_bytes() == b"radiograph"
    object_storage.check_connection()

    object_storage.delete(reference)
    assert not object_storage.exists(reference)


def test_r2_cache_hit_does_not_issue_a_second_head(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("R2_ENABLED", "1")
    monkeypatch.setenv("R2_CACHE_DIR", str(tmp_path / "cache"))
    fake = FakeR2Client()
    fake.objects[("dental-ai-prod", "uploads/example.pdf")] = b"pdf"
    heads = 0
    original_head = fake.head_object

    def counted_head(**kwargs):
        nonlocal heads
        heads += 1
        return original_head(**kwargs)

    fake.head_object = counted_head
    monkeypatch.setattr(object_storage, "_settings", lambda: ("dental-ai-prod", "endpoint", "key", "secret"))
    monkeypatch.setattr(object_storage, "_client", lambda: fake)
    from app.object_cache import scope
    with scope():
        assert object_storage.ensure_local("uploads/example.pdf").read_bytes() == b"pdf"
    with scope():
        assert object_storage.ensure_local("uploads/example.pdf").read_bytes() == b"pdf"
    assert heads == 1


def test_r2_materialization_distinguishes_missing_from_outage(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("R2_ENABLED", "1")
    monkeypatch.setenv("R2_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(object_storage, "_settings", lambda: ("dental-ai-prod", "endpoint", "key", "secret"))
    from app.object_cache import scope

    missing = FakeR2Client()
    monkeypatch.setattr(object_storage, "_client", lambda: missing)
    with scope(), pytest.raises(FileNotFoundError):
        object_storage.ensure_local("uploads/missing.pdf")

    class Outage:
        def head_object(self, **kwargs):
            raise OSError("unavailable")

    monkeypatch.setattr(object_storage, "_client", lambda: Outage())
    with scope(), pytest.raises(object_storage.ObjectStorageError):
        object_storage.ensure_local("uploads/unavailable.pdf")


def test_r2_size_metadata_is_bounded_and_invalidated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("R2_ENABLED", "1")
    fake = FakeR2Client()
    fake.objects[("dental-ai-prod", "uploads/size.pdf")] = b"12345"
    heads = 0
    original_head = fake.head_object

    def counted_head(**kwargs):
        nonlocal heads
        heads += 1
        return original_head(**kwargs)

    fake.head_object = counted_head
    monkeypatch.setattr(object_storage, "_settings", lambda: ("dental-ai-prod", "endpoint", "key", "secret"))
    monkeypatch.setattr(object_storage, "_client", lambda: fake)
    object_storage._forget_size("uploads/size.pdf")
    assert object_storage.size("uploads/size.pdf") == 5
    assert object_storage.size("uploads/size.pdf") == 5
    assert heads == 1
    object_storage.delete("uploads/size.pdf")
    assert object_storage._cached_size("uploads/size.pdf") is None
