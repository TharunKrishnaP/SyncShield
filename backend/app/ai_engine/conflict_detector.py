"""Cross-modal data conflict detector.

Detects cases where different data modalities (satellite, weather, river,
incidents) disagree significantly about the state of a zone. These conflicts
signal sensor latency, processing lag, or real phenomena like tidal backflow
that don't correlate with upstream rainfall.
"""
from datetime import datetime
from typing import Any, Dict, List
import uuid


class ConflictDetector:
    def __init__(self):
        self._conflicts: List[Dict[str, Any]] = []

    def detect(
        self,
        zone_scores: Dict[str, Dict[str, Any]],
        weather_map: Dict[str, Dict[str, Any]],
        river_map: Dict[str, Dict[str, Any]],
        satellite_map: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        conflicts = []
        for zid, zs in zone_scores.items():
            sat_raw = zs.get("evidence_breakdown", {}).get("satellite_raw", 0)
            wxt_raw = zs.get("evidence_breakdown", {}).get("weather_raw", 0)
            riv_raw = zs.get("evidence_breakdown", {}).get("river_raw", 0)

            # Conflict 1: High satellite flood extent but no rainfall / normal rivers
            if sat_raw > 60 and wxt_raw < 15 and riv_raw < 25:
                c = self._make(
                    zid, "SATELLITE_NO_RAIN",
                    "Satellite detects significant flood surface, but rainfall is low and river levels are normal.",
                    "Sentinel-1 SAR", "Open-Meteo / CWC",
                    0.20,
                    "Possible tidal backflow, urban drainage bottleneck, or delayed satellite response to earlier rainfall. Verify ground conditions.",
                )
                conflicts.append(c)

            # Conflict 2: High rainfall but no river rise
            if wxt_raw > 70 and riv_raw < 20:
                c = self._make(
                    zid, "RAIN_NO_RIVER_RISE",
                    "Heavy rainfall reported but river gauge shows no water level rise.",
                    "Open-Meteo", "CWC Telemetry",
                    0.15,
                    "Rainfall may be too recent to produce runoff, or upstream dam is retaining flow. Monitor for delayed river response.",
                )
                conflicts.append(c)

            # Conflict 3: River above danger but satellite shows dry
            if riv_raw > 70 and sat_raw < 15:
                c = self._make(
                    zid, "RIVER_HIGH_SATELLITE_DRY",
                    "River water level above danger mark, but satellite flood extent is minimal.",
                    "CWC Telemetry", "Sentinel-1 SAR",
                    0.18,
                    "River may be elevated but not yet overflowing banks, or satellite pass is outdated. Ground truth recommended.",
                )
                conflicts.append(c)

            # Conflict 4: Multiple high sources but very different magnitudes
            high_sources = sum(1 for x in [sat_raw, wxt_raw, riv_raw] if x > 50)
            if high_sources >= 2:
                spread = max(sat_raw, wxt_raw, riv_raw) - min(sat_raw, wxt_raw, riv_raw)
                if spread > 60:
                    c = self._make(
                        zid, "MODALITY_DIVERGENCE",
                        "Multiple high-severity signals with large magnitude differences across modalities.",
                        "Mixed sources", "Mixed sources",
                        0.12,
                        "One or more data sources may be stale or experiencing sensor issues. Cross-validate before dispatching resources.",
                    )
                    conflicts.append(c)

        self._conflicts = conflicts
        return conflicts

    @staticmethod
    def _make(
        zone_id: str,
        conflict_type: str,
        description: str,
        modality_a: str,
        modality_b: str,
        confidence_penalty: float,
        diagnosis: str,
    ) -> Dict[str, Any]:
        return {
            "id": f"CF-{uuid.uuid4().hex[:8]}",
            "zone_id": zone_id,
            "timestamp": datetime.now().isoformat(),
            "conflict_type": conflict_type,
            "description": description,
            "modality_a": modality_a,
            "modality_b": modality_b,
            "confidence_penalty": confidence_penalty,
            "diagnosis": diagnosis,
            "resolved": False,
        }

    def get_all(self) -> List[Dict[str, Any]]:
        return self._conflicts