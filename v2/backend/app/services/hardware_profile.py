"""Détection légère des capacités de la machine pour choisir le moteur ASR."""

from __future__ import annotations

import os
import platform
import subprocess
from dataclasses import asdict, dataclass


def _memory_gb() -> float:
    try:
        if platform.system() == "Darwin":
            raw = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip()
            return round(int(raw) / (1024**3), 1)
        if os.path.exists("/proc/meminfo"):
            with open("/proc/meminfo", "r", encoding="ascii") as handle:
                for line in handle:
                    if line.startswith("MemTotal:"):
                        return round(int(line.split()[1]) / (1024**2), 1)
    except Exception:
        return 0.0
    return 0.0


def _cuda_available() -> bool:
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


@dataclass(frozen=True)
class HardwareProfile:
    system: str
    architecture: str
    cpu_count: int
    memory_gb: float
    cuda: bool
    apple_silicon: bool
    tier: str
    recommended_local_engine: str
    recommended_whisper_model: str

    def to_dict(self) -> dict:
        return asdict(self)


def detect_hardware_profile() -> HardwareProfile:
    system = platform.system().lower() or "unknown"
    architecture = platform.machine().lower() or "unknown"
    cpu_count = os.cpu_count() or 1
    memory_gb = _memory_gb()
    cuda = _cuda_available()
    apple_silicon = system == "darwin" and architecture in {"arm64", "aarch64"}

    if cuda and memory_gb >= 12:
        tier = "accelerated"
        local_engine = "whisper"
        whisper_model = "turbo"
    elif apple_silicon or cpu_count >= 8 or memory_gb >= 12:
        tier = "standard"
        local_engine = "whisper"
        whisper_model = "small"
    else:
        tier = "lightweight"
        local_engine = "vosk"
        whisper_model = "base"

    return HardwareProfile(
        system=system,
        architecture=architecture,
        cpu_count=cpu_count,
        memory_gb=memory_gb,
        cuda=cuda,
        apple_silicon=apple_silicon,
        tier=tier,
        recommended_local_engine=local_engine,
        recommended_whisper_model=whisper_model,
    )
