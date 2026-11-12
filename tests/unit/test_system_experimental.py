"""Explicit exploratory live runs keep draft suites unapproved."""
import json
from pathlib import Path

import pytest

from pipeline.evaluation import EvaluationError
from pipeline.evaluation.system_contracts import SystemConfig, load_system_inputs
from pipeline.evaluation.system_metrics import evaluate_system_gates


def test_draft_suite_requires_explicit_experimental_opt_in(tmp_path):
    root = Path(__file__).resolve().parents[2]
    suite = root / 'data/benchmarks/system/v1/suite_manifest.json'
    config = json.loads((root / 'pipeline/configs/system_evaluation.json').read_text(encoding='utf8'))
    path = tmp_path / 'experimental.json'
    path.write_text(json.dumps(config), encoding='utf8')
    with pytest.raises(EvaluationError, match='draft'):
        load_system_inputs(root, suite, path, profile='live')
    config['allow_draft_suite'] = True
    path.write_text(json.dumps(config), encoding='utf8')
    inputs = load_system_inputs(root, suite, path, profile='live')
    assert inputs.manifest['status'] == 'draft'


def test_experimental_live_evidence_cannot_certify_acceptance():
    metrics = {
        'routing': {'must_escalate_total': 1, 'guardrail_passed': True},
        'ml': {'macro_f1': .95, 'model_type': 'distilbert', 'status': 'verified'},
    }
    config = SystemConfig(mandatory_gates=['routing_guardrails'])
    assert evaluate_system_gates(metrics, config, 'live')['all_mandatory_passed']
    result = evaluate_system_gates(metrics, config, 'live_experimental')
    assert result['all_mandatory_passed'] is False
    assert 'experimental' in result['summary_reason'].lower()
