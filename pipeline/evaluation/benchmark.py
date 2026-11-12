"""Inference latency and throughput benchmarking with hardware control and injectable clock."""

from __future__ import annotations

import contextlib
import os
import time
from typing import Any, Callable, Generator, Sequence

import numpy as np

from pipeline.evaluation import EvaluationError


def _set_direct_openblas_threads(n_threads: int) -> list[tuple[Any, int]]:
    """Directly locate and lock OpenBLAS runtime threads via ctypes."""
    restorations: list[tuple[Any, int]] = []
    import ctypes
    import glob
    import sys

    candidate_dirs: set[str] = set()
    for mod_name in ("numpy", "scipy"):
        if mod_name in sys.modules:
            mod = sys.modules[mod_name]
            base = os.path.dirname(getattr(mod, "__file__", ""))
            candidate_dirs.add(os.path.join(base, "..", f"{mod_name}.libs"))
            candidate_dirs.add(os.path.join(base, ".."))

    for c_dir in candidate_dirs:
        if os.path.exists(c_dir):
            for dll_p in glob.glob(os.path.join(c_dir, "*openblas*.dll")):
                try:
                    dll = ctypes.CDLL(os.path.abspath(dll_p))
                    if hasattr(dll, "openblas_get_num_threads") and hasattr(dll, "openblas_set_num_threads"):
                        prev = dll.openblas_get_num_threads()
                        dll.openblas_set_num_threads(n_threads)
                        restorations.append((dll, prev))
                except Exception:
                    pass
    return restorations


@contextlib.contextmanager
def scoped_num_threads(num_threads: int | None) -> Generator[None, None, None]:
    """Scoped context manager to temporarily lock CPU thread count across PyTorch and BLAS."""
    if num_threads is None or num_threads <= 0:
        yield
        return

    prev_torch_threads = None
    try:
        import torch

        prev_torch_threads = torch.get_num_threads()
        torch.set_num_threads(num_threads)
    except Exception:
        pass

    tp_context = None
    try:
        import threadpoolctl

        tp_context = threadpoolctl.threadpool_limits(limits=num_threads)
        tp_context.__enter__()
    except Exception:
        tp_context = None

    blas_restorations = _set_direct_openblas_threads(num_threads)

    env_vars = ["OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"]
    prev_env: dict[str, str | None] = {}
    for var in env_vars:
        prev_env[var] = os.environ.get(var)
        os.environ[var] = str(num_threads)

    try:
        yield
    finally:
        if prev_torch_threads is not None:
            try:
                import torch

                torch.set_num_threads(prev_torch_threads)
            except Exception:
                pass

        if tp_context is not None:
            try:
                tp_context.__exit__(None, None, None)
            except Exception:
                pass

        for dll, prev_t in blas_restorations:
            try:
                dll.openblas_set_num_threads(prev_t)
            except Exception:
                pass

        for var, prev_val in prev_env.items():
            if prev_val is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = prev_val



def benchmark_classifier(
    bundle: Any,
    texts: Sequence[str],
    config: dict[str, Any],
    clock: Callable[[], float] = time.perf_counter,
    sync_fn: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Measure inference latency (batch=1) and throughput (batch=256) strictly isolating warmup.

    Supports optional hardware synchronization hook (e.g. for CUDA or adapter models).
    """
    if not texts:
        raise EvaluationError("Texts sequence for benchmarking must not be empty")

    timing_cfg = config.get("timing", {})
    warmup_requests = timing_cfg.get("warmup_requests", 20)
    benchmark_requests = timing_cfg.get("benchmark_requests", 1000)
    latency_batch_size = timing_cfg.get("latency_batch_size", 1)
    throughput_batch_size = timing_cfg.get("throughput_batch_size", 256)

    text_list = [str(t) for t in texts if str(t).strip()]
    if not text_list:
        raise EvaluationError("All texts provided for benchmarking were blank or empty")

    n_samples = len(text_list)

    # Resolve synchronization callback
    if sync_fn is None and hasattr(bundle, "synchronize") and callable(getattr(bundle, "synchronize")):
        sync_fn = getattr(bundle, "synchronize")

    # 1. Warm-up runs (not recorded in percentiles)
    for i in range(warmup_requests):
        sample = [text_list[i % n_samples]]
        try:
            bundle.predict(sample)
        except Exception as exc:
            raise EvaluationError(f"Warm-up prediction failed: {exc}") from exc
        if sync_fn:
            sync_fn()

    # 2. Latency benchmark runs (batch=1)
    durations: list[float] = []
    for i in range(benchmark_requests):
        sample = [text_list[i % n_samples]]
        if sync_fn:
            sync_fn()
        t0 = clock()
        try:
            bundle.predict(sample)
        except Exception as exc:
            raise EvaluationError(f"Benchmark prediction failed: {exc}") from exc
        if sync_fn:
            sync_fn()
        t1 = clock()
        dur = t1 - t0
        if not np.isfinite(dur) or dur <= 0:
            raise EvaluationError(f"Invalid duration observed: {dur}")
        durations.append(float(dur))

    durations_sorted = sorted(durations)
    latency_stats = {
        "requests_measured": len(durations),
        "batch_size": latency_batch_size,
        "mean_seconds": float(np.mean(durations)),
        "min_seconds": float(durations_sorted[0]),
        "max_seconds": float(durations_sorted[-1]),
        "p50": float(np.percentile(durations, 50)),
        "p90": float(np.percentile(durations, 90)),
        "p95": float(np.percentile(durations, 95)),
        "p99": float(np.percentile(durations, 99)),
        "durations_seconds": durations,
    }

    # 3. Throughput run (batch=throughput_batch_size)
    tp_batch = [text_list[i % n_samples] for i in range(throughput_batch_size)]
    if sync_fn:
        sync_fn()
    t0_tp = clock()
    try:
        bundle.predict(tp_batch)
    except Exception as exc:
        raise EvaluationError(f"Throughput prediction failed: {exc}") from exc
    if sync_fn:
        sync_fn()
    t1_tp = clock()
    tp_dur = t1_tp - t0_tp
    if not np.isfinite(tp_dur) or tp_dur <= 0:
        raise EvaluationError(f"Invalid throughput duration observed: {tp_dur}")
    items_per_sec = float(throughput_batch_size / tp_dur)

    device_str = getattr(bundle, "device", config.get("device", "cpu"))
    num_threads = config.get("num_threads", os.cpu_count() or 1)

    return {
        "latency": latency_stats,
        "throughput": {
            "batch_size": throughput_batch_size,
            "duration_seconds": float(tp_dur),
            "items_per_second": items_per_sec,
        },
        "metadata": {
            "device": str(device_str),
            "precision": "fp32",
            "num_threads": num_threads,
            "cpu_count": os.cpu_count() or 1,
            "unique_samples": len(set(text_list)),
            "warmup_requests": warmup_requests,
            "benchmark_requests": benchmark_requests,
        },
    }
