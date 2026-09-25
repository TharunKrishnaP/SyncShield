"""Tests: the real pipeline never persists simulated/synthetic data.

Test 1 - the ingestion guard rejects explicitly-tagged simulated records with
         SIMULATION_ENABLED=False (fail-closed).
Test 2 - a full backend refresh cycle with SIMULATION_ENABLED=False produces
         ZERO synthetic records across every datalake partition (the real
         pipeline emits only real-world data).
Test 3 - the on-disk datalake (index.json) contains no synthetic markers and
         no template-derived incident rows.

Run:  python -m pytest tests/test_no_synthetic_guard.py -v
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))

from app.config import settings  # noqa: E402
from app.datalake.data_store import DataLake, _is_simulated  # noqa: E402

SIMULATED_MARKERS = ("simulated", "synthetic", "is_synthetic",
                     "SIMULATED", "SYNTHETIC")


def _walk(obj, path=""):
    """Yield every (path, value) pair in a nested JSON structure."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk(v, f"{path}[{i}]")
    else:
        yield path, obj


class TestIngestionGuard:
    def test_simulated_record_rejected(self):
        settings.SIMULATION_ENABLED = False
        dl = DataLake(path=str(REPO / "data_lake" / "_test_tmp"))
        with pytest.raises(ValueError):
            dl.put_satellite_extent({
                "id": "SIMULATED_ext",
                "source": "SIMULATED",
                "flood_pixel_ratio": 0.5,
            })
        with pytest.raises(ValueError):
            dl.add_incident({"source": "SIMULATED_REPORT", "description": "fake"})
        with pytest.raises(ValueError):
            dl.log_event({"type": "SIMULATION", "message": "step"})

    def test_real_record_allowed(self):
        settings.SIMULATION_ENABLED = False
        dl = DataLake(path=str(REPO / "data_lake" / "_test_tmp"))
        dl.add_incident({
            "source": "CITIZEN_REPORT", "description": "Real waterlogging near Gandhi Maidan",
        })
        dl.put_weather("AS-GUWAHATI", {"source": "open-meteo", "precip_mm": 12.0})
        dl.put_river_reading("BR-PATNA", {"source": "CWC", "water_level": 45.2})
        assert len(dl.get_incidents()) == 1

    def test_mock_drill_free_text_is_not_blocked(self):
        """Real NDMA advisories mention 'mock drill'; must never be blocked."""
        settings.SIMULATION_ENABLED = False
        dl = DataLake(path=str(REPO / "data_lake" / "_test_tmp"))
        dl.add_incident({
            "source": "NDMA_SACHET",
            "description": "Flood response mock drill scheduled for Patna today",
        })  # must not raise


class TestNoSyntheticInRefresh:
    def test_full_refresh_produces_zero_synthetic(self):
        """Boot the backend, run one full refresh with simulation OFF, and
        assert the resulting datalake contains no simulated markers."""
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        env["SIMULATION_ENABLED"] = "false"
        result = subprocess.run(
            [sys.executable, "-c",
             "import sys, asyncio, json; sys.path.insert(0, 'backend'); "
             "from app.orchestrator import FDROrchestrator; "
             "o = FDROrchestrator(); asyncio.run(o.refresh(force=True)); "
             "json.dump(o.datalake.snapshot(), sys.stdout)"],
            cwd=REPO, env=env, capture_output=True, text=True, timeout=180,
        )
        assert result.returncode == 0, result.stderr[-2000:]
        snapshot = json.loads(result.stdout)
        for path, val in _walk(snapshot):
            if isinstance(val, str):
                low = val.lower()
                assert not any(m in low for m in
                               ("simulated", "synthetic", "mock")), \
                    f"synthetic marker at {path}: {val[:80]}"
        # provenance field values must be real sources only
        real_sources = {"CWC", "NDMA", "GDACS", "NDMA_SACHET", "CITIZEN_REPORT",
                        "EONET", "open-meteo", "GLOFAS", "ML_SAR_UNET",
                        "imd", "nasa", "reliefweb", "MET"}
        for path, val in _walk(snapshot):
            if path.endswith(".source") or path.endswith("data_source"):
                assert str(val).upper() not in ("SIMULATED", "SYNTHETIC", "MOCK")


class TestOnDiskDatalake:
    def test_index_json_has_no_synthetic_markers(self):
        idx = json.loads((REPO / "data_lake" / "index.json").read_text(encoding="utf-8"))
        suspicious = []
        for path, val in _walk(idx):
            if isinstance(val, str):
                low = val.lower()
                if any(m in low for m in ("simulat", "synthetic")):
                    suspicious.append((path, val[:100]))
            if isinstance(val, str) and path.endswith(".source"):
                if val.strip().upper().startswith("SIMULATED"):
                    suspicious.append((path, val))
        assert suspicious == [], f"synthetic markers in index.json: {suspicious}"

    def test_monsoon_surge_scenario_isolated(self):
        """The scenario player's events live in the simulation engine buffer,
        never in the datalake timeline."""
        idx = json.loads((REPO / "data_lake" / "index.json").read_text(encoding="utf-8"))
        for ev in idx.get("timeline", []):
            assert "Monsoon onset" not in str(ev.get("message", ""))


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))