"""Minimal stdlib runner for Academic V2 function-style tests."""
from __future__ import annotations
import importlib.util
import inspect
from pathlib import Path
import sys

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
    for path in sorted(TEST_DIR.glob("test_*.py")):
        try:
            module = _load(path)
        except Exception as exc:
            failures.append(f"{path.name}::<module>: {type(exc).__name__}: {exc}")
            continue
        for name, fn in inspect.getmembers(module, inspect.isfunction):
            if not name.startswith("test_") or inspect.signature(fn).parameters:
                continue
            executed += 1
            try:
                fn()
            except Exception as exc:
                failures.append(f"{path.name}::{name}: {type(exc).__name__}: {exc}")
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
