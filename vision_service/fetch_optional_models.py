from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from vision_service.model_sources import OPTIONAL_MODEL_SOURCES, optional_model_path


def fetch_one(key: str) -> Path:
    from huggingface_hub import hf_hub_download

    source = OPTIONAL_MODEL_SOURCES[key]
    dest = optional_model_path(key)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 1024 * 1024:
        return dest

    errors = []
    for repo in source.repo_candidates:
        try:
            cached = Path(hf_hub_download(repo_id=repo, filename=source.filename))
            shutil.copy2(cached, dest)
            return dest
        except Exception as exc:
            errors.append(f"{repo}: {type(exc).__name__}: {exc}")

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
        print(f"MODEL_READY={key}:{path} SIZE_MB={path.stat().st_size / 1024 / 1024:.1f}")


if __name__ == "__main__":
    main()
