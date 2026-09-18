"""Host resource snapshots for the play-server HUD (CPU, RAM, GPU)."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
import sys
import time
from typing import Any

psutil: Any | None = None
try:
    import psutil as _psutil
except ImportError:
    pass
else:
    psutil = _psutil

RESOURCE_PERIOD_S = 1.0
_NVML_SUCCESS = 0
_NVML_NAME_MAX = 96


class _NvmlUtilization(ctypes.Structure):
    _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]


class _NvmlMemory(ctypes.Structure):
    _fields_ = [
        ("total", ctypes.c_ulonglong),
        ("free", ctypes.c_ulonglong),
        ("used", ctypes.c_ulonglong),
    ]


def _mb(nbytes: float) -> float:
    return round(float(nbytes) / (1024.0 * 1024.0), 1)


def _clamp_pct(value: float) -> float:
    return round(min(100.0, max(0.0, float(value))), 1)


def _gpu_index() -> int:
    raw = os.environ.get("CUDA_VISIBLE_DEVICES", "").strip()
    if not raw or raw == "-1":
        return 0
    first = raw.split(",")[0].strip()
    return int(first) if first.isdigit() else 0


def _load_nvml() -> Any | None:
    names = ("nvml.dll",) if sys.platform == "win32" else ("libnvidia-ml.so.1", "libnvidia-ml.so")
    for name in names:
        try:
            lib = ctypes.WinDLL(name) if sys.platform == "win32" else ctypes.CDLL(name)
        except OSError:
            continue
        lib.nvmlInit_v2.restype = ctypes.c_int
        lib.nvmlShutdown.restype = ctypes.c_int
        lib.nvmlDeviceGetCount_v2.restype = ctypes.c_int
        lib.nvmlDeviceGetCount_v2.argtypes = [ctypes.POINTER(ctypes.c_uint)]
        lib.nvmlDeviceGetHandleByIndex_v2.restype = ctypes.c_int
        lib.nvmlDeviceGetHandleByIndex_v2.argtypes = [
            ctypes.c_uint,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        lib.nvmlDeviceGetUtilizationRates.restype = ctypes.c_int
        lib.nvmlDeviceGetUtilizationRates.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_NvmlUtilization),
        ]
        lib.nvmlDeviceGetMemoryInfo.restype = ctypes.c_int
        lib.nvmlDeviceGetMemoryInfo.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_NvmlMemory),
        ]
        lib.nvmlDeviceGetName.restype = ctypes.c_int
        lib.nvmlDeviceGetName.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        return lib
    return None


class _Nvml:
    def __init__(self) -> None:
        self._lib = _load_nvml()
        self._ok = False
        if self._lib is None:
            return
        if self._lib.nvmlInit_v2() != _NVML_SUCCESS:
            self._lib = None
            return
        self._ok = True

    def sample(self) -> tuple[float | None, float | None, float | None, str | None]:
        if not self._ok or self._lib is None:
            return None, None, None, None
        count = ctypes.c_uint(0)
        if self._lib.nvmlDeviceGetCount_v2(ctypes.byref(count)) != _NVML_SUCCESS:
            return None, None, None, None
        if count.value == 0:
            return None, None, None, None
        index = min(_gpu_index(), count.value - 1)
        handle = ctypes.c_void_p()
        if self._lib.nvmlDeviceGetHandleByIndex_v2(index, ctypes.byref(handle)) != _NVML_SUCCESS:
            return None, None, None, None
        util = _NvmlUtilization()
        mem = _NvmlMemory()
        name_buf = ctypes.create_string_buffer(_NVML_NAME_MAX)
        gpu_pct: float | None = None
        used_mb: float | None = None
        total_mb: float | None = None
        name: str | None = None
        if self._lib.nvmlDeviceGetUtilizationRates(handle, ctypes.byref(util)) == _NVML_SUCCESS:
            gpu_pct = _clamp_pct(util.gpu)
        if self._lib.nvmlDeviceGetMemoryInfo(handle, ctypes.byref(mem)) == _NVML_SUCCESS:
            used_mb = _mb(mem.used)
            total_mb = _mb(mem.total)
        if self._lib.nvmlDeviceGetName(handle, name_buf, _NVML_NAME_MAX) == _NVML_SUCCESS:
            raw = name_buf.value.decode("utf-8", errors="replace").strip()
            name = raw[:64] if raw else None
        return gpu_pct, used_mb, total_mb, name

    def close(self) -> None:
        if self._ok and self._lib is not None:
            self._lib.nvmlShutdown()
        self._ok = False
        self._lib = None


def _win_rss_bytes() -> int | None:
    class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    counters = PROCESS_MEMORY_COUNTERS()
    counters.cb = ctypes.sizeof(counters)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [
        ctypes.wintypes.HANDLE,
        ctypes.c_void_p,
        ctypes.wintypes.DWORD,
    ]
    psapi.GetProcessMemoryInfo.restype = ctypes.wintypes.BOOL
    ok = psapi.GetProcessMemoryInfo(
        ctypes.windll.kernel32.GetCurrentProcess(),
        ctypes.byref(counters),
        counters.cb,
    )
    if not ok:
        return None
    return int(counters.WorkingSetSize)


def _win_ram() -> tuple[float, float] | None:
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_uint64),
            ("ullAvailPhys", ctypes.c_uint64),
            ("ullTotalPageFile", ctypes.c_uint64),
            ("ullAvailPageFile", ctypes.c_uint64),
            ("ullTotalVirtual", ctypes.c_uint64),
            ("ullAvailVirtual", ctypes.c_uint64),
            ("ullAvailExtendedVirtual", ctypes.c_uint64),
        ]

    status = MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(status)
    kernel32 = ctypes.windll.kernel32
    kernel32.GlobalMemoryStatusEx.argtypes = [ctypes.c_void_p]
    kernel32.GlobalMemoryStatusEx.restype = ctypes.wintypes.BOOL
    if not kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    used = status.ullTotalPhys - status.ullAvailPhys
    return _mb(used), _mb(status.ullTotalPhys)


def _filetime_int(ft: Any) -> int:
    return (int(ft.dwHighDateTime) << 32) | int(ft.dwLowDateTime)


def _win_system_times() -> tuple[int, int] | None:
    idle = ctypes.wintypes.FILETIME()
    kernel = ctypes.wintypes.FILETIME()
    user = ctypes.wintypes.FILETIME()
    kernel32 = ctypes.windll.kernel32
    kernel32.GetSystemTimes.argtypes = [
        ctypes.POINTER(ctypes.wintypes.FILETIME),
        ctypes.POINTER(ctypes.wintypes.FILETIME),
        ctypes.POINTER(ctypes.wintypes.FILETIME),
    ]
    kernel32.GetSystemTimes.restype = ctypes.wintypes.BOOL
    if not kernel32.GetSystemTimes(
        ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
    ):
        return None
    idle_t = _filetime_int(idle)
    total_t = _filetime_int(kernel) + _filetime_int(user)
    return idle_t, total_t


def _linux_rss_bytes() -> int | None:
    if sys.platform == "win32":
        return None
    sysconf = getattr(os, "sysconf", None)
    if sysconf is None:
        return None
    try:
        with open("/proc/self/statm", encoding="ascii") as fh:
            parts = fh.read().split()
        rss_pages = int(parts[1])
        page = sysconf("SC_PAGE_SIZE")
        return rss_pages * int(page)
    except (OSError, IndexError, ValueError, TypeError):
        return None


def _linux_ram() -> tuple[float, float] | None:
    try:
        data: dict[str, int] = {}
        with open("/proc/meminfo", encoding="ascii") as fh:
            for line in fh:
                key, rest = line.split(":", 1)
                data[key] = int(rest.strip().split()[0])
        total_kb = data["MemTotal"]
        avail_kb = data.get("MemAvailable", data.get("MemFree", 0))
        used_kb = max(0, total_kb - avail_kb)
        return round(used_kb / 1024.0, 1), round(total_kb / 1024.0, 1)
    except (OSError, KeyError, ValueError, IndexError):
        return None


def _linux_cpu_times() -> tuple[int, int] | None:
    try:
        with open("/proc/stat", encoding="ascii") as fh:
            parts = fh.readline().split()
        nums = [int(x) for x in parts[1:8]]
        idle = nums[3] + nums[4]
        total = sum(nums)
        return idle, total
    except (OSError, IndexError, ValueError):
        return None


class ResourceMonitor:
    """Delta CPU sampler plus RSS/RAM/GPU. First cpu_pct after prime is meaningful."""

    def __init__(self) -> None:
        self._ncpu = max(1, os.cpu_count() or 1)
        self._proc_t = time.process_time()
        self._wall_t = time.perf_counter()
        self._sys_idle_total: tuple[int, int] | None = None
        self._psutil_proc = None
        if psutil is not None:
            self._psutil_proc = psutil.Process()
            self._psutil_proc.cpu_percent(None)
            psutil.cpu_percent(None)
        elif sys.platform == "win32":
            self._sys_idle_total = _win_system_times()
        else:
            self._sys_idle_total = _linux_cpu_times()
        self._nvml = _Nvml()

    def sample(self) -> dict[str, Any]:
        cpu_pct, sys_cpu_pct = self._cpu()
        rss_mb, ram_used_mb, ram_total_mb = self._ram()
        gpu_pct, vram_used_mb, vram_total_mb, gpu_name = self._nvml.sample()
        gpu_pct, vram_used_mb, vram_total_mb, gpu_name = self._torch_gpu_fill(
            gpu_pct, vram_used_mb, vram_total_mb, gpu_name
        )
        return {
            "cpu_pct": cpu_pct,
            "sys_cpu_pct": sys_cpu_pct,
            "rss_mb": rss_mb,
            "ram_used_mb": ram_used_mb,
            "ram_total_mb": ram_total_mb,
            "gpu_pct": gpu_pct,
            "vram_used_mb": vram_used_mb,
            "vram_total_mb": vram_total_mb,
            "gpu_name": gpu_name,
        }

    def close(self) -> None:
        self._nvml.close()

    def _cpu(self) -> tuple[float, float | None]:
        if self._psutil_proc is not None and psutil is not None:
            # Process.cpu_percent is 100 per core; Task Manager uses / n_cpus.
            raw = float(self._psutil_proc.cpu_percent(None))
            cpu_pct = _clamp_pct(raw / self._ncpu)
            sys_cpu_pct = _clamp_pct(float(psutil.cpu_percent(None)))
            return cpu_pct, sys_cpu_pct

        now_proc = time.process_time()
        now_wall = time.perf_counter()
        dt_proc = now_proc - self._proc_t
        dt_wall = now_wall - self._wall_t
        self._proc_t = now_proc
        self._wall_t = now_wall
        if dt_wall <= 0:
            cpu_pct = 0.0
        else:
            cpu_pct = _clamp_pct((dt_proc / dt_wall) * 100.0 / self._ncpu)

        times = _win_system_times() if sys.platform == "win32" else _linux_cpu_times()
        host_cpu_pct: float | None = None
        if times is not None and self._sys_idle_total is not None:
            idle, total = times
            prev_idle, prev_total = self._sys_idle_total
            d_total = total - prev_total
            d_idle = idle - prev_idle
            if d_total > 0:
                host_cpu_pct = _clamp_pct((1.0 - d_idle / d_total) * 100.0)
        self._sys_idle_total = times
        return cpu_pct, host_cpu_pct

    def _ram(self) -> tuple[float, float | None, float | None]:
        if self._psutil_proc is not None and psutil is not None:
            rss_mb = _mb(self._psutil_proc.memory_info().rss)
            vm = psutil.virtual_memory()
            used_mb = _mb(vm.total - vm.available)
            return rss_mb, used_mb, _mb(vm.total)

        rss_bytes: int | None
        ram: tuple[float, float] | None
        if sys.platform == "win32":
            rss_bytes = _win_rss_bytes()
            ram = _win_ram()
        else:
            rss_bytes = _linux_rss_bytes()
            ram = _linux_ram()
        rss_mb = _mb(rss_bytes) if rss_bytes else 0.0
        if ram is None:
            return rss_mb, None, None
        return rss_mb, ram[0], ram[1]

    def _torch_gpu_fill(
        self,
        gpu_pct: float | None,
        vram_used_mb: float | None,
        vram_total_mb: float | None,
        gpu_name: str | None,
    ) -> tuple[float | None, float | None, float | None, str | None]:
        if gpu_pct is not None and vram_used_mb is not None:
            return gpu_pct, vram_used_mb, vram_total_mb, gpu_name
        torch = sys.modules.get("torch")
        if torch is None:
            return gpu_pct, vram_used_mb, vram_total_mb, gpu_name
        try:
            cuda = torch.cuda
            if not cuda.is_available():
                return gpu_pct, vram_used_mb, vram_total_mb, gpu_name
            if vram_used_mb is None and hasattr(cuda, "mem_get_info"):
                free_b, total_b = cuda.mem_get_info()
                vram_total_mb = _mb(total_b)
                vram_used_mb = _mb(total_b - free_b)
            if gpu_pct is None and hasattr(cuda, "utilization"):
                gpu_pct = _clamp_pct(float(cuda.utilization()))
            if gpu_name is None and hasattr(cuda, "get_device_name"):
                gpu_name = str(cuda.get_device_name(0))[:64]
        except Exception:
            return gpu_pct, vram_used_mb, vram_total_mb, gpu_name
        return gpu_pct, vram_used_mb, vram_total_mb, gpu_name
