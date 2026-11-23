"""Import the real application in a fresh process so router startup errors fail CI."""
import os
import subprocess
import sys
from pathlib import Path


def test_mobile_router_boots_and_registers_analysis_history(tmp_path):
    root = Path(__file__).resolve().parents[1]
    script = """
from app.main import app
from fastapi.testclient import TestClient
client = TestClient(app)
for path in ['/api/mobile/v1/patients', '/api/mobile/v1/analyses']:
    response = client.get(path)
    assert response.status_code == 401, (path, response.status_code)
    assert isinstance(response.json()['detail'], str)
"""
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=root,
        env={**os.environ, "DATABASE_URL": "sqlite:///" + str(tmp_path / "boot.db")},
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
