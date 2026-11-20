from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def _concurrency_block(workflow_name: str) -> str:
    source = (ROOT / ".github" / "workflows" / workflow_name).read_text(encoding="utf-8")
    match = re.search(
        r"(?ms)^concurrency:\\s*\\n(?P<body>(?:^[ \\t]+.*\\n|^\\s*\\n)+)",
        source,
    )
    assert match, f"{workflow_name} must declare a concurrency policy"
    return match.group("body")


def test_mobile_android_ci_does_not_cancel_an_in_flight_build():
    block = _concurrency_block("mobile-android.yml")
    assert re.search(r"(?m)^\\s+cancel-in-progress:\\s*false\\s*(?:#.*)?$", block)
    assert not re.search(r"(?m)^\\s+cancel-in-progress:\\s*true\\s*(?:#.*)?$", block)


def test_security_recovery_does_not_cancel_an_in_flight_security_suite():
    block = _concurrency_block("security-recovery.yml")
    assert re.search(r"(?m)^\\s+cancel-in-progress:\\s*false\\s*(?:#.*)?$", block)
    assert not re.search(r"(?m)^\\s+cancel-in-progress:\\s*true\\s*(?:#.*)?$", block)
