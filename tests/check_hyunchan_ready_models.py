from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import onnx
from huggingface_hub import hf_hub_download


SPECS = {
    "bone_loss": {
        "repo": "chemahc94/Dental-AI-Models",
        "revision": "05b496bc104c77601f5f472eb00b0fa646b75895",
        "file": "Dental_003/weights/best.onnx",
    },
    "periapical": {
        "repo": "chemahc94/Dental_012",
        "revision": "53ef2e5396e065d7d4371fc0c208d90830c5cdb6",
        "file": "best.onnx",
    },
}


def _parse(raw: str | None):
    if not raw:
        return None
    for parser in (json.loads, ast.literal_eval):
        try:
            value = parser(raw)
            if isinstance(value, dict):
                return {int(k): str(v) for k, v in value.items()}
            if isinstance(value, (list, tuple)):
                return {i: str(v) for i, v in enumerate(value)}
        except Exception:
            pass
    return raw


def main():
    output = {}
    for key, spec in SPECS.items():
        path = Path(hf_hub_download(repo_id=spec["repo"], filename=spec["file"], revision=spec["revision"]))
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        model = onnx.load(str(path), load_external_data=False)
        metadata = {item.key: item.value for item in model.metadata_props}
        output[key] = {
            "bytes": path.stat().st_size,
            "sha256": digest,
            "names": _parse(metadata.get("names")),
            "metadata_keys": sorted(metadata),
            "inputs": [x.name for x in model.graph.input],
            "outputs": [x.name for x in model.graph.output],
        }
        if path.stat().st_size < 1_000_000:
            raise AssertionError(f"{key} checkpoint unexpectedly small")
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
