import platform
import subprocess
from typing import Any, Dict, List

try:
    import torch
except Exception:
    torch = None


def _query_nvidia_smi() -> Dict[str, Any]:
    info: Dict[str, Any] = {}
    try:
        cp = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=2,
        )
        if cp.returncode != 0 or not cp.stdout:
            return info
        lines = [x.strip() for x in cp.stdout.splitlines() if x.strip()]
        gpus: List[Dict[str, Any]] = []
        for idx, line in enumerate(lines):
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 3:
                name = parts[0]
                driver = parts[1]
                mem_str = parts[2].split()[0]
                try:
                    total_mb = int(mem_str)
                except Exception:
                    total_mb = 0
                gpus.append(
                    {
                        "index": idx,
                        "name": name,
                        "driver_version": driver,
                        "total_memory_mb": total_mb,
                    }
                )
        if gpus:
            info["gpus"] = gpus
    except Exception:
        return {}
    return info


def get_gpu_status() -> Dict[str, Any]:
    status: Dict[str, Any] = {
        "platform": platform.system(),
        "available": False,
        "device": "cpu",
        "backends": [],
        "gpus": [],
        "frameworks": {},
    }
    frameworks: Dict[str, Any] = {}
    gpus: List[Dict[str, Any]] = []
    device = "cpu"
    available = False
    backends: List[str] = []

    if torch is not None:
        frameworks["torch"] = {"version": getattr(torch, "__version__", None)}

        cuda_info: Dict[str, Any] = {}
        try:
            cuda_available = bool(torch.cuda.is_available())
        except Exception:
            cuda_available = False
        cuda_info["available"] = cuda_available
        cuda_version = getattr(getattr(torch, "version", None), "cuda", None)
        if cuda_version:
            cuda_info["version"] = cuda_version
        cudnn_available = False
        try:
            cudnn_available = bool(torch.backends.cudnn.is_available())
        except Exception:
            cudnn_available = False
        cuda_info["cudnn_available"] = cudnn_available

        if cuda_available:
            available = True
            device = "cuda"
            backends.append("cuda")
            try:
                count = torch.cuda.device_count()
            except Exception:
                count = 0
            for idx in range(count):
                try:
                    props = torch.cuda.get_device_properties(idx)
                    capability = (
                        str(getattr(props, "major", 0))
                        + "."
                        + str(getattr(props, "minor", 0))
                    )
                    total_mem = int(getattr(props, "total_memory", 0) // (1024 * 1024))
                    gpus.append(
                        {
                            "index": idx,
                            "name": getattr(props, "name", ""),
                            "total_memory_mb": total_mem,
                            "compute_capability": capability,
                        }
                    )
                except Exception:
                    continue

        frameworks["cuda"] = cuda_info

        mps_available = False
        try:
            if hasattr(torch.backends, "mps"):
                mps_available = bool(torch.backends.mps.is_available())
        except Exception:
            mps_available = False
        if mps_available:
            if not available:
                device = "mps"
            available = True
            backends.append("mps")

        hip_version = getattr(getattr(torch, "version", None), "hip", None)
        if hip_version:
            frameworks["rocm"] = {"version": hip_version}

    smi = _query_nvidia_smi()
    if smi.get("gpus"):
        if not gpus:
            gpus = smi["gpus"]
        frameworks["nvidia_smi"] = {"gpus": smi["gpus"]}

    status["frameworks"] = frameworks
    status["gpus"] = gpus
    status["available"] = available
    status["device"] = device
    status["backends"] = backends
    return status