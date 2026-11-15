"""Focused upload byte/format checks, without booting production services."""
import ast
import io
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from PIL import Image


def _validator():
    source = Path(__file__).resolve().parents[1] / "app" / "mobile_analysis_api.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_copy_validated_analysis_image")
    module = ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))
    scope = {
        "Path": Path,
        "Image": Image,
        "HTTPException": HTTPException,
        "MOBILE_MAX_ANALYSIS_BYTES": 15 * 1024 * 1024,
        "MOBILE_MAX_ANALYSIS_PIXELS": 40_000_000,
    }
    exec(compile(module, str(source), "exec"), scope)
    return scope[node.name]


def _image(fmt):
    stream = io.BytesIO()
    Image.new("RGB", (4, 4)).save(stream, format=fmt)
    stream.seek(0)
    return SimpleNamespace(file=stream)


@pytest.mark.parametrize("fmt,extension", [("JPEG", ".jpg"), ("JPEG", ".jpeg"), ("PNG", ".png"), ("WEBP", ".webp")])
def test_valid_clinical_image_format(fmt, extension):
    with TemporaryDirectory() as temp:
        destination = Path(temp) / ("upload" + extension)
        _validator()(_image(fmt), destination)
        assert destination.exists()


@pytest.mark.parametrize("fmt,extension", [("PNG", ".jpg"), ("JPEG", ".png"), ("WEBP", ".jpeg"), ("PNG", ".webp")])
def test_mismatched_clinical_image_bytes_are_rejected_and_deleted(fmt, extension):
    with TemporaryDirectory() as temp:
        destination = Path(temp) / ("upload" + extension)
        with pytest.raises(HTTPException) as error:
            _validator()(_image(fmt), destination)
        assert error.value.status_code == 422
        assert not destination.exists()


def test_analysis_batch_rejects_missing_filename_before_creating_record():
    source = Path(__file__).resolve().parents[1] / "app" / "mobile_analysis_api.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    endpoint = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "create_mobile_analysis")
    checks = [node for node in ast.walk(endpoint) if isinstance(node, ast.If)]
    filename_guards = [node for node in checks if "image.filename" in ast.unparse(node.test) and "any(" in ast.unparse(node.test)]
    assert filename_guards, "Malformed image parts must be rejected rather than filtered out"
    guard = filename_guards[0]
    assert any(isinstance(node, ast.Raise) for node in guard.body)
    analysis_creation = next(node.lineno for node in ast.walk(endpoint) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Analysis")
    assert guard.lineno < analysis_creation


def test_corrupt_clinical_image_is_rejected_and_removed():
    with TemporaryDirectory() as temp:
        destination = Path(temp) / "upload.png"
        with pytest.raises(HTTPException) as error:
            _validator()(SimpleNamespace(file=io.BytesIO(b"not an image")), destination)
        assert error.value.status_code == 422
        assert not destination.exists()


def test_oversize_clinical_image_is_rejected_and_removed():
    source = Path(__file__).resolve().parents[1] / "app" / "mobile_analysis_api.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_copy_validated_analysis_image")
    scope = {"Path": Path, "Image": Image, "HTTPException": HTTPException,
             "MOBILE_MAX_ANALYSIS_BYTES": 3, "MOBILE_MAX_ANALYSIS_PIXELS": 40_000_000}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), str(source), "exec"), scope)
    with TemporaryDirectory() as temp:
        destination = Path(temp) / "upload.png"
        with pytest.raises(HTTPException) as error:
            scope[node.name](_image("PNG"), destination)
        assert error.value.status_code == 413
        assert not destination.exists()
