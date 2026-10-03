"""Minimal stdlib runner for Academic V2 function-style tests."""
from __future__ import annotations
import importlib.util
import inspect
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
TEST_DIR = ROOT / "tests" / "academic_v2"

def _load(path: Path):
    name = f"_academic_v2_{path.stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

def main() -> int:
    failures = []
    executed = 0
    selected = (
        "test_dental_graph.py",
        "test_dental_intent.py",
        "test_intent_benchmark_15k.py",
        "test_dental_semantics.py",
        "test_academic_scope.py",
        "test_academic_coverage.py",
        "test_academic_generation.py",
        "test_academic_generation_jobs.py",
        "test_adversarial_benchmark.py",
        "test_retrieval_behavior.py",
        "test_static_invariants.py",
    )
    for filename in selected:
        path = TEST_DIR / filename
        try:
            module = _load(path)
        except Exception as exc:
            failures.append(f"{path.name}::<module>: {type(exc).__name__}: {exc}\n{traceback.format_exc()}")
            continue
        for name, fn in inspect.getmembers(module, inspect.isfunction):
            if not name.startswith("test_") or inspect.signature(fn).parameters:
                continue
            executed += 1
            try:
                fn()
            except Exception as exc:
                failures.append(f"{path.name}::{name}: {type(exc).__name__}: {exc}\n{traceback.format_exc()}")
    print(f"Academic V2 tests executed: {executed}")
    if failures:
        print("FAILURES:")
        for failure in failures:
            print(f" - {failure}")
        return 1
    print("Academic V2 function tests: OK")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
