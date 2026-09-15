from __future__ import annotations

import json
import re
from pathlib import Path

import requests

SOURCES = {
    "dentalopg1550": "https://data.mendeley.com/datasets/rtt726b26d/1",
    "hanoi_periapical": "https://data.mendeley.com/datasets/kx52tk2ddj/3",
}

API_CANDIDATES = {
    "dentalopg1550": [
        "https://api.mendeley.com/datasets/rtt726b26d?version=1",
        "https://data.mendeley.com/public-api/datasets/rtt726b26d/versions/1",
    ],
    "hanoi_periapical": [
        "https://api.mendeley.com/datasets/kx52tk2ddj?version=3",
        "https://data.mendeley.com/public-api/datasets/kx52tk2ddj/versions/3",
    ],
}


def probe(name: str, url: str) -> dict:
    out = {"name": name, "page_url": url, "page": {}, "apis": []}
    headers = {"User-Agent": "Vision48-Gold-Benchmark/1.0"}
    r = requests.get(url, headers=headers, timeout=60)
    out["page"] = {
        "status": r.status_code,
        "final_url": r.url,
        "content_type": r.headers.get("content-type"),
        "length": len(r.content),
    }
    text = r.text
    pats = [
        r'https?://[^"\'<> ]+(?:download|file|dataset)[^"\'<> ]*',
        r'https?://downloads\.mendeley\.com/[^"\'<> ]+',
        r'https?://data\.mendeley\.com/public-files/[^"\'<> ]+',
    ]
    urls = []
    for pat in pats:
        urls.extend(re.findall(pat, text, flags=re.I))
    out["page"]["candidate_urls"] = sorted(set(u.replace("&amp;", "&") for u in urls))[:100]
    for api in API_CANDIDATES[name]:
        try:
            ar = requests.get(api, headers={**headers, "Accept": "application/json, application/vnd.mendeley-public-dataset.1+json"}, timeout=60)
            entry = {
                "url": api,
                "status": ar.status_code,
                "content_type": ar.headers.get("content-type"),
                "length": len(ar.content),
                "text_head": ar.text[:1000],
            }
            if ar.ok:
                try:
                    data = ar.json()
                    entry["json_keys"] = sorted(data.keys()) if isinstance(data, dict) else []
                    entry["files"] = data.get("files") if isinstance(data, dict) else None
                except Exception:
                    pass
            out["apis"].append(entry)
        except Exception as exc:
            out["apis"].append({"url": api, "error": repr(exc)})
    return out


def main():
    outdir = Path("benchmark-results/source-probe")
    outdir.mkdir(parents=True, exist_ok=True)
    result = {name: probe(name, url) for name, url in SOURCES.items()}
    (outdir / "probe.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
