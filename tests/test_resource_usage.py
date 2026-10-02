import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from hosted.resource_usage import ContainerResourceSampler


class ContainerResourceSamplerTests(unittest.TestCase):
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
