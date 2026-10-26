"""The local benchmark must exercise the current Claude extraction contract offline."""
import importlib.util
from pathlib import Path

from app import voice_exam_core as core


def benchmark_module():
    path = Path(__file__).parents[1] / 'scripts/benchmark_voice_flow.py'
    spec = importlib.util.spec_from_file_location('voice_benchmark', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_simulated_benchmark_runs_actual_extraction_without_real_credentials(monkeypatch):
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    benchmark = benchmark_module()
    _, text = benchmark.dialogue()
    with benchmark.simulated_transport() as stats:
        result = core.extract(transcript=text)
    assert result['transcript'] == text
    assert result['fields']['age']['value'] == '32'
    assert 'medical_history' in result['fields']
    assert 'medications' in result['fields']
    assert stats['calls'] == 1
    assert stats['inflight'] == 0
