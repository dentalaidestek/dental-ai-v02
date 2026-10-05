"""Audit a frozen JSONL benchmark without changing its cases or scoring rules.

These are necessary lexical consistency checks, not semantic validation. Passing
this audit does NOT make a case a trustworthy semantic oracle.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import unicodedata


def normalized(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold().replace("ı", "i"))
    return "".join(c for c in value if not unicodedata.combining(c))


def defects(case: dict) -> dict[str, list[str]]:
    must = {normalized(term) for term in case["must"]}
    forbidden = {normalized(term) for term in case["must_not"]}
    visible = normalized(" ".join(text for _, text in case["history"]) + " " + case["query"])
    result = {}
    if must & forbidden:
        result["required_and_forbidden_same_term"] = sorted(must & forbidden)
    missing = sorted(term for term in must if term not in visible)
    if missing:
        result["required_term_not_visible_anywhere"] = missing
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    counts = Counter()
    examples = {}
    digest = hashlib.sha256()
    with args.input.open("rb") as stream:
        for line in stream:
            digest.update(line)
            case = json.loads(line)
            counts["total"] += 1
            found = defects(case)
            if found:
                counts["at_least_one_lexical_gold_defect"] += 1
            for reason, details in found.items():
                counts[reason] += 1
                if len(examples.setdefault(reason, [])) < 5:
                    examples[reason].append({"case": case, "details": details})
    report = {
        "input_sha256": digest.hexdigest(), "counts": dict(counts), "examples": examples,
        "limitations": "Lexical necessary conditions only; no cases removed or relabelled. "
                        "Missing terms may include spelling variants; contradictory required/forbidden "
                        "terms are unsatisfiable under the original substring scorer.",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"sha256": digest.hexdigest(), "counts": dict(counts)}))


if __name__ == "__main__":
    main()
