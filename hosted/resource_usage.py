"""Best-effort whole-container CPU and memory measurement for a worker run."""

from __future__ import annotations

import resource
import sys
import threading
import time
from pathlib import Path


class ContainerResourceSampler:
    """Sample Linux cgroup usage, including the audit subprocess and parent."""

    def __init__(self, *, cgroup_root="/sys/fs/cgroup", interval_seconds=0.25):
        self.cgroup_root = Path(cgroup_root)
        self.interval_seconds = interval_seconds
        self.started_at = None
        self.peak_memory_bytes = 0
        self._cpu_start_usec = None
        self._cpu_end_usec = None
        self._child_usage_start = None
        self._stop_event = threading.Event()
        self._thread = None
        self._sampled_memory_peak_bytes = None

    def _read_int(self, path):
        try:
            return int(path.read_text(encoding="ascii").strip())
        except (OSError, ValueError):
            return None

    def _read_cpu_usec(self):
        try:
            for line in (self.cgroup_root / "cpu.stat").read_text(
                encoding="ascii"
            ).splitlines():
                key, value = line.split(maxsplit=1)
                if key == "usage_usec":
                    return int(value)
        except (OSError, ValueError):
            pass
        return None

    def _sample_once(self):
        current_memory = self._read_int(self.cgroup_root / "memory.current")
        if current_memory is not None:
            self.peak_memory_bytes = max(self.peak_memory_bytes, current_memory)
        self._cpu_end_usec = self._read_cpu_usec()

    def _sample_loop(self):
        while not self._stop_event.wait(self.interval_seconds):
            self._sample_once()

    def start(self):
        self.started_at = time.monotonic()
        self._cpu_start_usec = self._read_cpu_usec()
        self._child_usage_start = resource.getrusage(resource.RUSAGE_CHILDREN)
        self._sample_once()
        self._thread = threading.Thread(
            target=self._sample_loop,
            name="container-resource-sampler",
            daemon=True,
        )
        self._thread.start()
        return self

    def stop(self):
        if self.started_at is None:
            raise RuntimeError("Resource sampler was not started")
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self.interval_seconds * 4))
        self._sample_once()
        # cgroup v2's memory.peak is more accurate than periodic sampling.
        cgroup_peak = self._read_int(self.cgroup_root / "memory.peak")
        if cgroup_peak is not None:
            self._sampled_memory_peak_bytes = cgroup_peak
            memory_source = "cgroup_v2"
        else:
            child_peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
            if child_peak:
                self._sampled_memory_peak_bytes = (
                    child_peak if sys.platform == "darwin"
                    else child_peak * 1024
                )
                memory_source = "child_process_rusage"
            elif self.peak_memory_bytes:
                self._sampled_memory_peak_bytes = self.peak_memory_bytes
                memory_source = "cgroup_v2_sampled"
            else:
                self._sampled_memory_peak_bytes = None
                memory_source = "unavailable"
        elapsed = max(0.0, time.monotonic() - self.started_at)
        cpu_seconds = None
        cpu_source = "unavailable"
        if self._cpu_start_usec is not None and self._cpu_end_usec is not None:
            cpu_seconds = max(
                0.0, (self._cpu_end_usec - self._cpu_start_usec) / 1_000_000,
            )
            cpu_source = "cgroup_v2"
        else:
            usage = resource.getrusage(resource.RUSAGE_CHILDREN)
            baseline = self._child_usage_start
            cpu_seconds = max(
                0.0,
                (usage.ru_utime + usage.ru_stime)
                - (baseline.ru_utime + baseline.ru_stime if baseline else 0.0),
            )
            cpu_source = "child_process_rusage"
        return {
            "elapsed_seconds": round(elapsed, 3),
            "peak_memory_bytes": self._sampled_memory_peak_bytes,
            "cpu_seconds": round(cpu_seconds, 3),
            "measurement_source": memory_source,
            "cpu_measurement_source": cpu_source,
        }
