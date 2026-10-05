import ast
from pathlib import Path


def test_modal_indexer_is_scale_to_zero_and_bounded():
    source = Path("modal_academic_indexer.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert "min_containers=0" in source
    assert "max_containers=8" in source
    assert 'STUDY_V2_OCR_BATCH_PAGES", "16"' in source
    assert "drain_index_queue.spawn()" in source
    assert "run_one_slice" in source
    # Modal must reuse the durable worker rather than inventing a second queue.
    assert "StudyIndexJob(" not in source
    assert "Queue.from_name" not in source
    assert tree is not None


def test_modal_indexer_does_not_disable_generation_fencing():
    source = Path("modal_academic_indexer.py").read_text(encoding="utf-8")
    forbidden = (
        "publish_index_version(",
        "active_index_version =",
        "building_index_version =",
        "lease_token =",
    )
    assert not any(item in source for item in forbidden)
