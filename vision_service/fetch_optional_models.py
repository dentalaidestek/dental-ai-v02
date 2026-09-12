from __future__ import annotations

import argparse
import hashlib
import shutil
from pathlib import Path

from vision_service.model_sources import OPTIONAL_MODEL_SOURCES, optional_model_path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify(path: Path, expected: str | None) -> None:
    if not expected:
        return
    actual = _sha256(path)
    if actual.lower() != expected.lower():
        raise RuntimeError(f"SHA256 uyuşmuyor: expected={expected} actual={actual}")


def fetch_one(key: str) -> Path:
    from huggingface_hub import hf_hub_download

    source = OPTIONAL_MODEL_SOURCES[key]
    dest = optional_model_path(key)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 1024 * 1024:
        try:
            _verify(dest, source.sha256)
            return dest
        except Exception:
            dest.unlink(missing_ok=True)

    errors = []
    for repo in source.repo_candidates:
        try:
            cached = Path(
                hf_hub_download(
                    repo_id=repo,
                    filename=source.filename,
                    revision=source.revision,
                )
            )
            _verify(cached, source.sha256)
            shutil.copy2(cached, dest)
            _verify(dest, source.sha256)
            return dest
        except Exception as exc:
            dest.unlink(missing_ok=True)
            errors.append(f"{repo}@{source.revision or 'main'}: {type(exc).__name__}: {exc}")

    raise RuntimeError(f"{key} indirilemedi: " + " | ".join(errors))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("keys", nargs="*", help="Boş bırakılırsa bütün optional kaynaklar indirilir.")
    args = parser.parse_args()
    keys = args.keys or list(OPTIONAL_MODEL_SOURCES)
    unknown = sorted(set(keys) - set(OPTIONAL_MODEL_SOURCES))
    if unknown:
        raise SystemExit(f"Bilinmeyen model key: {unknown}")

    for key in keys:
        source = OPTIONAL_MODEL_SOURCES[key]
        print(f"[{key}] {source.purpose}")
        path = fetch_one(key)
        digest = _sha256(path)
        print(f"MODEL_READY={key}:{path} SIZE_MB={path.stat().st_size / 1024 / 1024:.1f} SHA256={digest}")


if __name__ == "__main__":
    main()
