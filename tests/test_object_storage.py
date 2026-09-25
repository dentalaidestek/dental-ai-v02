from pathlib import Path

from app import object_storage


class FakeR2Client:
    def __init__(self):
        self.objects = {}

    def list_objects_v2(self, *, Bucket, MaxKeys):
        return {"Name": Bucket, "MaxKeys": MaxKeys}

    def upload_file(self, filename, bucket, key, ExtraArgs=None):
        self.objects[(bucket, key)] = Path(filename).read_bytes()

    def head_object(self, *, Bucket, Key):
        value = self.objects[(Bucket, Key)]
        return {"ContentLength": len(value)}

    def download_file(self, bucket, key, filename):
        Path(filename).write_bytes(self.objects[(bucket, key)])

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
    assert object_storage.ensure_local(reference).read_bytes() == b"radiograph"
    object_storage.check_connection()

    object_storage.delete(reference)
    assert not object_storage.exists(reference)
