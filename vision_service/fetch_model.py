from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import quote


REPO = os.getenv(
    "DENTAL_VISION_MODEL_REPO",
    "dentalaidestek/dental-ai-v02",
)

TAG = os.getenv(
    "DENTAL_VISION_MODEL_TAG",
    "vision-model-v1",
)

ASSET_NAME = os.getenv(
    "DENTAL_VISION_MODEL_ASSET",
    "YOLOv11x-seg.pt",
)

TOKEN = os.getenv("GITHUB_MODEL_TOKEN", "").strip()

DEST = (
    Path(__file__).resolve().parent.parent
    / "models"
    / "vision"
    / ASSET_NAME
)


def request(url: str, *, binary: bool = False):
    headers = {
        "User-Agent": "Dental-AI-Vision",
        "Accept": (
            "application/octet-stream"
            if binary
            else "application/vnd.github+json"
        ),
        "X-GitHub-Api-Version": "2022-11-28",
    }

    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"

    return urllib.request.Request(url, headers=headers)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)

    return h.hexdigest()


def main():
    if not TOKEN:
        raise RuntimeError(
            "GITHUB_MODEL_TOKEN environment variable bulunamadı."
        )

    release_url = (
        f"https://api.github.com/repos/{REPO}"
        f"/releases/tags/{quote(TAG)}"
    )

    print(f"Release aranıyor: {TAG}")

    with urllib.request.urlopen(request(release_url), timeout=60) as response:
        release = json.load(response)

    asset = next(
        (
            item
            for item in release.get("assets", [])
            if item.get("name") == ASSET_NAME
        ),
        None,
    )

    if asset is None:
        raise RuntimeError(
            f"Release asset bulunamadı: {ASSET_NAME}"
        )

    DEST.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_name = tempfile.mkstemp(
        prefix="dental-vision-",
        suffix=".pt",
        dir=DEST.parent,
    )
    os.close(fd)

    temp_path = Path(temp_name)

    try:
        print(
            f"Model indiriliyor: "
            f"{asset.get('size', 0) / 1024 / 1024:.2f} MiB"
        )

        with urllib.request.urlopen(
            request(asset["url"], binary=True),
            timeout=300,
        ) as response, temp_path.open("wb") as output:
            shutil.copyfileobj(response, output)

        if temp_path.stat().st_size < 10 * 1024 * 1024:
            raise RuntimeError(
                "İndirilen model dosyası beklenenden çok küçük."
            )

        actual_sha256 = sha256_file(temp_path)
        digest = asset.get("digest") or ""

        if digest.startswith("sha256:"):
            expected_sha256 = digest.split(":", 1)[1].lower()

            if actual_sha256.lower() != expected_sha256:
                raise RuntimeError(
                    "Model SHA256 doğrulaması başarısız."
                )

            print("SHA256 doğrulandı.")

        temp_path.replace(DEST)

        print(f"MODEL_READY={DEST}")
        print(
            f"MODEL_SIZE_MB="
            f"{DEST.stat().st_size / 1024 / 1024:.2f}"
        )

    finally:
        temp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
