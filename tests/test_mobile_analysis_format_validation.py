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
