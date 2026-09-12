from __future__ import annotations

import ast
import hashlib
import json

import onnx

from vision_service.fetch_optional_models import fetch_one
from vision_service.model_sources import OPTIONAL_MODEL_SOURCES


EXPECTED = {0: "caries", 1: "periapical_lesion", 2: "impacted_tooth"}


def _parse_names(raw: str):
    for parser in (json.loads, ast.literal_eval):
        try:
            value = parser(raw)
            if isinstance(value, dict):
                return {int(k): str(v) for k, v in value.items()}
            if isinstance(value, (list, tuple)):
                return {i: str(v) for i, v in enumerate(value)}
        except Exception:
            pass
    return None


def main():
    source = OPTIONAL_MODEL_SOURCES["liodon3"]
    path = fetch_one("liodon3")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != source.sha256:
        raise AssertionError(f"Liodon hash mismatch after fetch: {digest}")
    model = onnx.load(str(path), load_external_data=False)
    metadata = {item.key: item.value for item in model.metadata_props}
    names = _parse_names(metadata.get("names", ""))
    if names != EXPECTED:
        raise AssertionError(f"Unexpected Liodon class metadata: {names!r}; metadata keys={sorted(metadata)}")
    print(json.dumps({"file": path.name, "bytes": path.stat().st_size, "sha256": digest, "names": names}, sort_keys=True))


if __name__ == "__main__":
    main()
