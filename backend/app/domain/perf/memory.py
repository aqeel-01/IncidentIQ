"""Process memory sampling helpers for performance runs."""

from __future__ import annotations

import sys
import threading
import time
import tracemalloc
from dataclasses import dataclass, field


def process_rss_mb() -> float | None:
    """Best-effort current process RSS in mebibytes."""

    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                    ("PrivateUsage", ctypes.c_size_t),
                ]

            GetCurrentProcess = ctypes.windll.kernel32.GetCurrentProcess
            GetCurrentProcess.restype = wintypes.HANDLE
            psapi = ctypes.WinDLL("psapi")
            GetProcessMemoryInfo = psapi.GetProcessMemoryInfo
            GetProcessMemoryInfo.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(PROCESS_MEMORY_COUNTERS_EX),
                wintypes.DWORD,
            ]
            GetProcessMemoryInfo.restype = wintypes.BOOL

            counters = PROCESS_MEMORY_COUNTERS_EX()
            counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS_EX)
            ok = GetProcessMemoryInfo(
                GetCurrentProcess(),
                ctypes.byref(counters),
                counters.cb,
            )
            if not ok:
                return None
            return float(counters.WorkingSetSize) / (1024 * 1024)
        except Exception:  # noqa: BLE001
            return None

    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # Linux reports KB; macOS reports bytes.
        if sys.platform == "darwin":
            return usage / (1024 * 1024)
        return usage / 1024.0
    except Exception:  # noqa: BLE001
        return None


@dataclass
class MemoryTracker:
    """Sample RSS while a stage runs; also tracks tracemalloc peaks."""

    interval_seconds: float = 0.05
    _peak_rss_mb: float | None = None
    _python_peak_mb: float | None = None
    _stop: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = None
    _tracemalloc_started: bool = False

    def __enter__(self) -> MemoryTracker:
        if not tracemalloc.is_tracing():
            tracemalloc.start()
            self._tracemalloc_started = True
        self._peak_rss_mb = process_rss_mb()
        self._stop.clear()
        self._thread = threading.Thread(target=self._sample_loop, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *args: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        rss = process_rss_mb()
        if rss is not None:
            self._peak_rss_mb = (
                rss if self._peak_rss_mb is None else max(self._peak_rss_mb, rss)
            )
        if tracemalloc.is_tracing():
            _current, peak = tracemalloc.get_traced_memory()
            self._python_peak_mb = peak / (1024 * 1024)
        self.stop_tracemalloc()

    def _sample_loop(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            rss = process_rss_mb()
            if rss is None:
                continue
            self._peak_rss_mb = (
                rss if self._peak_rss_mb is None else max(self._peak_rss_mb, rss)
            )

    @property
    def peak_rss_mb(self) -> float | None:
        return self._peak_rss_mb

    @property
    def python_peak_mb(self) -> float | None:
        if self._python_peak_mb is not None:
            return self._python_peak_mb
        if not tracemalloc.is_tracing():
            return None
        _current, peak = tracemalloc.get_traced_memory()
        return peak / (1024 * 1024)

    def stop_tracemalloc(self) -> None:
        if self._tracemalloc_started and tracemalloc.is_tracing():
            tracemalloc.stop()
            self._tracemalloc_started = False


def timed_stage(name: str):
    """Decorator-style context: ``with timed_stage('parse') as ctx``."""

    @dataclass
    class _Ctx:
        name: str
        started: float = 0.0
        duration_seconds: float = 0.0
        tracker: MemoryTracker | None = None

        def __enter__(self) -> _Ctx:
            self.tracker = MemoryTracker()
            self.tracker.__enter__()
            self.started = time.perf_counter()
            return self

        def __exit__(self, *args: object) -> None:
            self.duration_seconds = time.perf_counter() - self.started
            if self.tracker is not None:
                self.tracker.__exit__(*args)

    return _Ctx(name=name)
