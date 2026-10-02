"""Best-effort whole-container CPU and memory measurement for a worker run."""

from __future__ import annotations

import resource
import os
import sys
import threading
import time
from pathlib import Path


class ContainerResourceSampler:
    """Sample Linux cgroup usage, including the audit subprocess and parent."""

    def __init__(
        self,
        *,
        cgroup_root="/sys/fs/cgroup",
        proc_root="/proc",
        interval_seconds=1.0,
    ):
        self.cgroup_root = Path(cgroup_root)
        self.proc_root = Path(proc_root)
        self.interval_seconds = interval_seconds
        self.started_at = None
        self.peak_memory_bytes = 0
        self._cpu_start_usec = None
        self._cpu_end_usec = None
        self._child_usage_start = None
        self._stop_event = threading.Event()
        self._thread = None
        self._sampled_memory_peak_bytes = None
        self._proc_sample_count = 0
        self._proc_peak_memory_bytes = 0
        self._proc_peak_cpu_cores = None
        self._proc_tree_cpu_seconds = 0.0
        self._proc_samples = []
        self._previous_proc_sample = None
        self._page_size = os.sysconf("SC_PAGE_SIZE")
        self._clock_ticks = os.sysconf("SC_CLK_TCK")

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
        sample_time = time.monotonic()
        current_memory = self._read_int(self.cgroup_root / "memory.current")
        if current_memory is not None:
            self.peak_memory_bytes = max(self.peak_memory_bytes, current_memory)
        self._cpu_end_usec = self._read_cpu_usec()
        process_tree = self._read_process_tree()
        if process_tree is not None:
            self._record_process_sample(sample_time, *process_tree)

    @staticmethod
    def _parse_proc_stat(contents):
        """Return (parent pid, CPU ticks, resident pages) from /proc/PID/stat."""
        try:
            fields = contents.rsplit(")", 1)[1].split()
            return (
                int(fields[1]),
                int(fields[11]) + int(fields[12]),
                max(0, int(fields[21])),
            )
        except (IndexError, ValueError):
            return None

    def _read_process_tree(self):
        """Read the current worker and all visible descendants from /proc."""
        try:
            entries = list(self.proc_root.iterdir())
        except OSError:
            return None
        processes = {}
        for entry in entries:
            if not entry.name.isdigit():
                continue
            try:
                contents = (entry / "stat").read_text(encoding="ascii")
            except OSError:
                continue
            parsed = self._parse_proc_stat(contents)
            if parsed is not None:
                processes[int(entry.name)] = parsed
        root_pid = os.getpid()
        if root_pid not in processes:
            return None
        children = {}
        for pid, (parent_pid, _cpu_ticks, _rss_pages) in processes.items():
            children.setdefault(parent_pid, []).append(pid)
        pids = {root_pid}
        pending = [root_pid]
        while pending:
            for child_pid in children.get(pending.pop(), ()):
                if child_pid not in pids:
                    pids.add(child_pid)
                    pending.append(child_pid)
        cpu_ticks = sum(processes[pid][1] for pid in pids)
        rss_bytes = sum(processes[pid][2] for pid in pids) * self._page_size
        return rss_bytes, cpu_ticks

    def _record_process_sample(self, sample_time, rss_bytes, cpu_ticks):
        self._proc_sample_count += 1
        self._proc_peak_memory_bytes = max(self._proc_peak_memory_bytes, rss_bytes)
        cpu_cores = None
        previous = self._previous_proc_sample
        if previous is not None:
            previous_time, previous_ticks = previous
            elapsed = max(0.001, sample_time - previous_time)
            cpu_cores = max(
                0.0,
                (cpu_ticks - previous_ticks) / self._clock_ticks / elapsed,
            )
            self._proc_peak_cpu_cores = max(
                self._proc_peak_cpu_cores or 0.0, cpu_cores,
            )
            self._proc_tree_cpu_seconds += cpu_cores * elapsed
        self._previous_proc_sample = (sample_time, cpu_ticks)
        self._proc_samples.append(
            {
                "elapsed_seconds": round(sample_time - self.started_at, 1),
                "rss_bytes": rss_bytes,
                "cpu_cores": round(cpu_cores, 3) if cpu_cores is not None else None,
            }
        )

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
        elif self._proc_peak_memory_bytes:
            self._sampled_memory_peak_bytes = self._proc_peak_memory_bytes
            memory_source = "proc_process_tree_1s"
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
            "peak_cpu_cores_1s": round(self._proc_peak_cpu_cores, 3)
            if self._proc_peak_cpu_cores is not None else None,
            "process_tree_cpu_seconds_1s": round(self._proc_tree_cpu_seconds, 3),
            "sample_interval_seconds": self.interval_seconds,
            "sample_count": self._proc_sample_count,
            "samples": self._proc_samples,
            "measurement_source": memory_source,
            "cpu_measurement_source": cpu_source,
        }
