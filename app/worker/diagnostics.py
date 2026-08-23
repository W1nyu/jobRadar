"""워커 한 사이클의 메모리 예산을 재현 가능하게 측정하는 도구."""

from __future__ import annotations

import tracemalloc
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WorkerMemoryMeasurement:
    """`tracemalloc`이 관측한 워커 사이클의 Python 할당량."""

    current_bytes: int
    peak_bytes: int

    @property
    def peak_megabytes(self) -> float:
        """운영 메모리 예산과 비교하기 쉬운 MiB 단위 피크를 반환한다."""
        return self.peak_bytes / (1024 * 1024)


def measure_worker_cycle(operation: Callable[[], object]) -> WorkerMemoryMeasurement:
    """수집·저장·알림 등 한 워커 사이클의 추가 Python 할당 피크를 측정한다."""
    started_here = not tracemalloc.is_tracing()
    if started_here:
        tracemalloc.start()
    tracemalloc.reset_peak()
    try:
        operation()
        current_bytes, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        if started_here:
            tracemalloc.stop()
    return WorkerMemoryMeasurement(current_bytes=current_bytes, peak_bytes=peak_bytes)
