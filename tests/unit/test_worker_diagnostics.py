"""M10 워커 1사이클 Python 할당 메모리 측정 계약."""

from app.worker.diagnostics import measure_worker_cycle


def test_워커_사이클의_피크_할당량을_바이트와_megabyte로_반환한다() -> None:
    measurement = measure_worker_cycle(lambda: bytearray(128 * 1024))

    assert measurement.peak_bytes >= 128 * 1024
    assert measurement.peak_megabytes > 0
