"""Supplement an immutable quality run with a real demo HTTP latency study."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from datetime import datetime, timezone

from pipeline.evaluation import EvaluationError
from pipeline.evaluation.system_contracts import load_system_inputs, verify_input_snapshot
from pipeline.evaluation.system_execution import build_system_dependencies
from pipeline.evaluation.system_performance import measure_system_latency
from pipeline.preparation.utils import compute_sha256


def verify_parent(run_dir: Path) -> dict:
    manifest = json.loads((run_dir / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('status') != 'completed' or not manifest.get('files'):
        raise EvaluationError('Parent run must be completed with checksummed artifacts')
    for key in ('results.jsonl', 'metrics.json', 'config.resolved.json'):
        if key not in manifest['files']:
            raise EvaluationError(f'Missing parent artifact: {key}')
    for meta in manifest['files'].values():
        target = (run_dir / meta['path']).resolve()
        target.relative_to(run_dir.resolve())
        if compute_sha256(target).lower() != meta['sha256'].lower():
            raise EvaluationError(f'Parent checksum mismatch: {target.name}')
    return manifest


def summarize_http_results(results, warmup_count: int, expected_count: int) -> dict:
    times = sorted(r.total_elapsed_ms / 1000 for r in results)
    metrics = {
        'measurement_scope': 'api_total', 'transport': 'loopback HTTP',
        'endpoint': 'POST /api/demo/runs', 'includes': [
            'client HTTP', 'session middleware', 'ML HTTP inference', 'routing',
            'commerce', 'retrieval', 'LLM', 'SQLite persistence', 'response serialization'],
        'excludes': ['model loading', 'warmup', 'browser rendering', 'human review'],
        'requests_count': len(results), 'warmup_count': warmup_count,
        'p50_seconds': (times[(len(times)-1)//2] + times[len(times)//2]) / 2 if times else None,
        'p95_seconds': times[max(0, math.ceil(.95 * len(times))-1)] if times else None,
        'technical_errors': sum(r.execution_status == 'error' for r in results),
        'http_timeouts': sum(r.execution_status == 'timeout' for r in results),
        'server_restarts': sum(bool((r.audit_evidence or {}).get('server_restarted')) for r in results),
        'drafts': sum(bool(r.draft_body) for r in results),
    }
    metrics['latency_target_met'] = bool(times and len(results) == expected_count
        and all(r.execution_status == 'ok' for r in results)
        and not metrics['server_restarts'] and metrics['p95_seconds'] <= 12)
    return metrics


def run_http_study(parent_run: Path, output_dir: Path) -> Path:
    verify_parent(parent_run)
    parent_hash = compute_sha256(parent_run / 'manifest.json')
    root = Path(__file__).resolve().parents[2]
    inputs = load_system_inputs(root, 'data/benchmarks/system/v1/suite_manifest.json',
        'pipeline/configs/system_evaluation.experimental.json', profile='live')
    previous_cost = json.loads((parent_run / 'cost.json').read_text(encoding='utf-8'))
    inputs.config.max_llm_calls = max(0, 200 - previous_cost.get('reserved_calls', 0))
    inputs.config.max_estimated_cost_usd = max(0, 1 - previous_cost.get('total_cost_usd', 0))
    output_dir.mkdir(parents=True, exist_ok=False)
    def write(name, value):
        (output_dir / name).write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')
    write('state.json', {'status': 'running', 'started_at': datetime.now(timezone.utc).isoformat()})
    write('config.resolved.json', inputs.config.model_dump())
    deps = None
    try:
        deps = build_system_dependencies(inputs, 'live', output_dir / 'runtime')
        results = measure_system_latency(inputs, deps)
        metrics = summarize_http_results(results, inputs.config.warmup_requests, inputs.config.latency_requests)
        with (output_dir / 'http_results.jsonl').open('w', encoding='utf-8') as stream:
            for result in results:
                stream.write(result.model_dump_json() + '\n')
        write('http_latency.json', metrics)
        write('http_cost.json', deps.ledger.summary())
        verify_input_snapshot(inputs)
        verify_parent(parent_run)
        if compute_sha256(parent_run / 'manifest.json') != parent_hash:
            raise EvaluationError('Parent manifest changed during HTTP study')
        write('state.json', {'status': 'completed', 'completed_at': datetime.now(timezone.utc).isoformat()})
        write('manifest.json', {
            'status': 'completed', 'evidence_kind': 'live_experimental',
            'parent_manifest_sha256': parent_hash, 'input_hashes': inputs.input_hashes,
            'files': {p.name: {'path': p.name, 'sha256': compute_sha256(p)}
                      for p in output_dir.iterdir() if p.is_file() and p.name != 'manifest.json'},
        })
        print(json.dumps(metrics, indent=2))
        return output_dir
    except Exception as exc:
        write('state.json', {'status': 'failed', 'error_code': type(exc).__name__})
        raise
    finally:
        if deps:
            deps.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--parent-run', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / '.env', override=False)
    run_http_study(args.parent_run, args.output_dir)


if __name__ == '__main__':
    main()
