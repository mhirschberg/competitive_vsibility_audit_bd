"""Measure an offline notebook/service parity fixture without provider calls.

Run from the service-first repository root with the project interpreter:
    python scripts/measure_offline_audit_resources.py [repetitions]

The measured unittest process exercises the synthetic end-to-end parity fixture
with Reddit both disabled and enabled. Its adapters are all local fakes.
"""

import resource
import statistics
import subprocess
import sys
import time


REPETITIONS = int(sys.argv[1]) if len(sys.argv) > 1 else 5
COMMAND = [
    sys.executable,
    "-m",
    "unittest",
    "tests.test_audit_pipeline.AuditPipelineTests.test_fixture_result_matches_notebook_orchestration",
]


def resident_set_bytes(value):
    # macOS reports bytes; Linux and the BSDs used in CI report KiB.
    return value if sys.platform == "darwin" else value * 1024


durations = []
for attempt in range(REPETITIONS):
    started = time.monotonic()
    process = subprocess.Popen(
        COMMAND,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    output, _ = process.communicate()
    durations.append(time.monotonic() - started)
    if process.returncode:
        print(output)
        raise SystemExit(process.returncode)
    print(f"run {attempt + 1}: elapsed={durations[-1]:.3f}s")

# RUSAGE_CHILDREN reports the maximum RSS among waited-for direct children.
# This fixture does not spawn worker processes; each measured tree is the one
# Python unittest process. The resource counter is cumulative across runs.
peak_bytes = resident_set_bytes(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)
print(f"median elapsed: {statistics.median(durations):.3f}s")
print(f"max resident set: {peak_bytes / (1024 * 1024):.1f} MiB")
print("fixture: synthetic notebook/service parity; Reddit off/on; no provider calls")
