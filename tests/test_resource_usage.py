import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from hosted.resource_usage import ContainerResourceSampler


class ContainerResourceSamplerTests(unittest.TestCase):
    @staticmethod
    def _proc_stat(pid, parent_pid, cpu_ticks, rss_pages):
        fields = ["0"] * 22
        fields[0] = "S"
        fields[1] = str(parent_pid)
        fields[11] = str(cpu_ticks // 2)
        fields[12] = str(cpu_ticks - cpu_ticks // 2)
        fields[21] = str(rss_pages)
        return f"{pid} (audit runner (worker)) " + " ".join(fields)

    def test_process_tree_sampling_sums_visible_descendants(self):
        with tempfile.TemporaryDirectory() as root:
            proc_root = Path(root)
            for pid, parent, cpu, rss in (
                (100, 1, 10, 10),
                (101, 100, 15, 20),
                (102, 101, 25, 30),
                (200, 1, 100, 200),
            ):
                process_dir = proc_root / str(pid)
                process_dir.mkdir()
                (process_dir / "stat").write_text(
                    self._proc_stat(pid, parent, cpu, rss), encoding="ascii",
                )
            sampler = ContainerResourceSampler(
                proc_root=proc_root, cgroup_root=proc_root / "missing",
            )
            sampler._page_size = 4096
            with patch("hosted.resource_usage.os.getpid", return_value=100):
                sample = sampler._read_process_tree()

        self.assertEqual(sample, (60 * 4096, 50))

    def test_one_second_samples_capture_peak_rss_and_cpu_cores(self):
        sampler = ContainerResourceSampler(interval_seconds=1.0)
        sampler.started_at = 100.0
        sampler._clock_ticks = 100
        sampler._record_process_sample(100.0, 1000, 100)
        sampler._record_process_sample(101.0, 2000, 150)
        sampler._record_process_sample(102.0, 1500, 250)

        self.assertEqual(sampler._proc_peak_memory_bytes, 2000)
        self.assertEqual(sampler._proc_peak_cpu_cores, 1.0)
        self.assertEqual(sampler._proc_tree_cpu_seconds, 1.5)
        self.assertEqual(sampler._proc_sample_count, 3)

    def test_reads_cgroup_peak_memory_and_cpu_time(self):
        with tempfile.TemporaryDirectory() as root:
            cgroup = Path(root)
            (cgroup / "memory.current").write_text("100\n", encoding="ascii")
            (cgroup / "memory.peak").write_text("250\n", encoding="ascii")
            (cgroup / "cpu.stat").write_text(
                "usage_usec 100000\nuser_usec 70000\nsystem_usec 30000\n",
                encoding="ascii",
            )
            sampler = ContainerResourceSampler(
                cgroup_root=cgroup, interval_seconds=0.01,
            ).start()
            (cgroup / "memory.current").write_text("200\n", encoding="ascii")
            (cgroup / "cpu.stat").write_text(
                "usage_usec 2100000\nuser_usec 1700000\nsystem_usec 400000\n",
                encoding="ascii",
            )
            result = sampler.stop()

        self.assertEqual(result["peak_memory_bytes"], 250)
        self.assertEqual(result["cpu_seconds"], 2.0)
        self.assertEqual(result["measurement_source"], "cgroup_v2")
        self.assertEqual(result["cpu_measurement_source"], "cgroup_v2")
        self.assertGreaterEqual(result["elapsed_seconds"], 0)

    def test_missing_cgroup_files_falls_back_without_failing(self):
        with tempfile.TemporaryDirectory() as root:
            usage_before = SimpleNamespace(ru_utime=1.0, ru_stime=0.5, ru_maxrss=100)
            usage_after = SimpleNamespace(ru_utime=9.0, ru_stime=2.5, ru_maxrss=250)
            with patch(
                "hosted.resource_usage.resource.getrusage",
                side_effect=[usage_before, usage_after, usage_after],
            ):
                sampler = ContainerResourceSampler(
                    cgroup_root=Path(root), interval_seconds=0.01,
                ).start()
                time.sleep(0.01)
                result = sampler.stop()

        self.assertGreater(result["peak_memory_bytes"], 0)
        self.assertEqual(result["measurement_source"], "child_process_rusage")
        self.assertEqual(result["cpu_measurement_source"], "child_process_rusage")
        self.assertEqual(result["cpu_seconds"], 10.0)


if __name__ == "__main__":
    unittest.main()
