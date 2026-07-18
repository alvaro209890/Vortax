"""Observabilidade leve do Vortax — métricas em memória por processo.

Registra tempo por etapa, tokens aproximados, custos estimados e falhas por provider.
Não persiste em SQLite (reinicia com o processo); suficiente para /api/providers/metrics
e para embutir snapshot no export da sessão.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Any


# Preços aproximados USD / 1M tokens (DeepSeek V4 Flash — ordem de grandeza)
_PRICE_INPUT_PER_M = 0.14
_PRICE_OUTPUT_PER_M = 0.28


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._started_at = time.time()
        self._counters: dict[str, int] = defaultdict(int)
        self._timings_ms: dict[str, list[float]] = defaultdict(list)
        self._provider_errors: dict[str, int] = defaultdict(int)
        self._token_usage: dict[str, dict[str, int]] = defaultdict(
            lambda: {"prompt": 0, "completion": 0, "total": 0}
        )
        self._task_stats: dict[str, dict[str, Any]] = {}

    def incr(self, key: str, amount: int = 1) -> None:
        with self._lock:
            self._counters[key] += amount

    def observe_ms(self, key: str, duration_ms: float) -> None:
        with self._lock:
            bucket = self._timings_ms[key]
            bucket.append(float(duration_ms))
            if len(bucket) > 500:
                del bucket[:250]

    def record_provider_error(self, provider: str) -> None:
        with self._lock:
            self._provider_errors[provider or "unknown"] += 1
            self._counters[f"provider_error:{provider or 'unknown'}"] += 1

    def record_usage(self, provider: str, usage: dict[str, Any] | None) -> None:
        if not usage:
            return
        prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        completion = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
        total = int(usage.get("total_tokens") or (prompt + completion))
        with self._lock:
            bag = self._token_usage[provider or "unknown"]
            bag["prompt"] += prompt
            bag["completion"] += completion
            bag["total"] += total
            self._counters[f"tokens:{provider or 'unknown'}"] += total

    def task_mark(self, task_id: str, **fields: Any) -> None:
        with self._lock:
            entry = self._task_stats.setdefault(
                task_id,
                {"started_at": time.time(), "steps_ms": {}, "events": 0, "tools": 0, "errors": 0},
            )
            for key, value in fields.items():
                if key == "steps_ms" and isinstance(value, dict):
                    entry["steps_ms"].update(value)
                elif key in {"events", "tools", "errors"} and isinstance(value, int):
                    entry[key] = int(entry.get(key, 0)) + value
                else:
                    entry[key] = value

    def task_step_ms(self, task_id: str, step_label: str, duration_ms: float) -> None:
        with self._lock:
            entry = self._task_stats.setdefault(
                task_id,
                {"started_at": time.time(), "steps_ms": {}, "events": 0, "tools": 0, "errors": 0},
            )
            entry["steps_ms"][step_label] = float(duration_ms)

    def estimate_cost_usd(self, provider: str = "deepseek") -> float:
        with self._lock:
            bag = self._token_usage.get(provider) or {"prompt": 0, "completion": 0}
            prompt = bag["prompt"]
            completion = bag["completion"]
        return (prompt / 1_000_000.0) * _PRICE_INPUT_PER_M + (completion / 1_000_000.0) * _PRICE_OUTPUT_PER_M

    def snapshot(self, *, task_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            timings: dict[str, dict[str, float]] = {}
            for key, samples in self._timings_ms.items():
                if not samples:
                    continue
                timings[key] = {
                    "count": len(samples),
                    "avg_ms": round(sum(samples) / len(samples), 2),
                    "p95_ms": round(sorted(samples)[max(0, int(len(samples) * 0.95) - 1)], 2),
                    "max_ms": round(max(samples), 2),
                }
            token_usage = {k: dict(v) for k, v in self._token_usage.items()}
            provider_errors = dict(self._provider_errors)
            counters = dict(self._counters)
            task = dict(self._task_stats.get(task_id) or {}) if task_id else None
            tasks_count = len(self._task_stats)
            uptime = time.time() - self._started_at

        costs = {
            provider: round(
                (bag["prompt"] / 1_000_000.0) * _PRICE_INPUT_PER_M
                + (bag["completion"] / 1_000_000.0) * _PRICE_OUTPUT_PER_M,
                6,
            )
            for provider, bag in token_usage.items()
        }
        return {
            "uptime_seconds": round(uptime, 1),
            "counters": counters,
            "timings": timings,
            "token_usage": token_usage,
            "estimated_cost_usd": costs,
            "provider_errors": provider_errors,
            "tasks_tracked": tasks_count,
            "task": task,
        }


metrics = MetricsRegistry()
