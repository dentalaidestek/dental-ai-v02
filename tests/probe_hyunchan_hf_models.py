from __future__ import annotations

import json

from huggingface_hub import HfApi


REPOS = [
    "chemahc94/Dental_003_Model",
    "chemahc94/Dental_012",
    "chemahc94/Dental_013",
    "chemahc94/Dental-AI-Models",
    "chemahc94/dentex-tooth-segmentation",
]


def main():
    api = HfApi()
    rows = {}
    for repo in REPOS:
        try:
            info = api.model_info(repo, files_metadata=True)
            rows[repo] = {
                "sha": info.sha,
                "siblings": [
                    {"name": s.rfilename, "size": getattr(s, "size", None)}
                    for s in (info.siblings or [])
                    if s.rfilename.lower().endswith((".pt", ".pth", ".onnx", ".json", ".yaml", ".yml"))
                ],
            }
        except Exception as exc:
            rows[repo] = {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(rows, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
