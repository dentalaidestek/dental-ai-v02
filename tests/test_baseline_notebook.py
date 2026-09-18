from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def test_baseline_notebook_is_valid_python():
    nb=json.loads((ROOT/"training"/"DentalAI_Baseline_AutoTest.ipynb").read_text(encoding="utf-8"))
    assert nb["nbformat"]==4
    code="\n\n".join("".join(c.get("source",[])) for c in nb["cells"] if c.get("cell_type")=="code")
    compile(code,"DentalAI_Baseline_AutoTest.ipynb","exec")
    assert "structured_vision_payload" in code
    assert "TEST_DATA_INSUFFICIENT" in code
    assert "wilson_lower" in code
    assert ">=13" in code
    assert "annotation_exhaustive" in code
    assert "pan_targets=list(REGISTRY48)" in code

def test_harness_has_leakage_guards():
    text=(ROOT/"training"/"baseline_test_harness.py").read_text(encoding="utf-8")
    assert "sha256_file" in text
    assert "assert_training_pool_clean" in text
    assert "TEST LEAKAGE" in text
    assert "validate_locked_pool" in text
    assert "duplicate_key" in text
    assert "duplicate target hash" in text
