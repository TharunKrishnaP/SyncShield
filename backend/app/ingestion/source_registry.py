"""Central registry recording the live health of every external data source.

The dashboard uses this to tell citizens and officials, in plain terms, which
feeds are genuinely live right now, which are degraded, and which are only
reference links. Every ingestion client reports into this registry so the
``/api/data-sources`` endpoint is always an honest, timestamped picture.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

LIVE = "LIVE"
DEGRADED = "DEGRADED"
UNAVAILABLE = "UNAVAILABLE"
NEEDS_KEY = "NEEDS_KEY"
REFERENCE = "REFERENCE"
SIMULATED = "SIMULATED"
UNKNOWN = "UNKNOWN"


class SourceRegistry:
    def __init__(self):
        self._sources: Dict[str, Dict[str, Any]] = {}

    def register(
        self,
        key: str,
        name: str,
        url: str,
        category: str = "official_govt",
        coverage: str = "India",
        kind: str = "api",
        requires_key: bool = False,
        status: str = UNKNOWN,
        plain_name: Optional[str] = None,
        what_it_gives: Optional[str] = None,
        is_indian_govt: bool = False,
        realtime: bool = False,
    ) -> Dict[str, Any]:
        """Register a data source.

        ``realtime`` marks feeds that are actually polled live and drive the
        dashboard numbers (vs reference portals, key-gated APIs and modelled
        estimates that can never be "streaming").
        """
        entry = {
            "key": key,
            "name": name,
            "plain_name": plain_name or name,
            "url": url,
            "category": category,
            "coverage": coverage,
            "kind": kind,
            "requires_key": requires_key,
            "is_indian_govt": is_indian_govt,
            "realtime": bool(realtime),
            "what_it_gives": what_it_gives or "",
            "status": status,
            "last_success": None,
            "last_attempt": None,
            "latency_ms": None,
            "records": 0,
            "error": None,
        }
        self._sources[key] = entry
        return entry

    def record(
        self,
        key: str,
        ok: bool,
        latency_ms: Optional[float] = None,
        records: int = 0,
        error: Optional[str] = None,
        degraded: bool = False,
    ) -> None:
        s = self._sources.get(key)
        if not s:
            return
        s["last_attempt"] = datetime.now().isoformat()
        if latency_ms is not None:
            s["latency_ms"] = round(float(latency_ms), 1)
        if ok:
            previous_ok = s.get("last_success") is not None
            s["status"] = DEGRADED if degraded else LIVE
            s["last_success"] = datetime.now().isoformat()
            s["records"] = records
            s["error"] = None
            if not previous_ok:
                s["recovered_at"] = datetime.now().isoformat()
        else:
            s["status"] = DEGRADED if s.get("last_success") else UNAVAILABLE
            s["error"] = (str(error)[:200] if error else None)

    def set_status(self, key: str, status: str, note: Optional[str] = None, records: Optional[int] = None) -> None:
        s = self._sources.get(key)
        if not s:
            return
        s["status"] = status
        if records is not None:
            s["records"] = records
        if note:
            s["error"] = note[:200] if status in (UNAVAILABLE, DEGRADED, NEEDS_KEY) else None

    def snapshot(self) -> List[Dict[str, Any]]:
        return [dict(s) for s in self._sources.values()]

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        s = self._sources.get(key)
        return dict(s) if s else None

    def summary(self) -> Dict[str, Any]:
        live = [s for s in self._sources.values() if s["status"] == LIVE]
        streaming = [s for s in live if s.get("realtime")]
        return {
            "total": len(self._sources),
            "live": len(live),
            "live_names": [s["plain_name"] for s in live],
            "streaming": len(streaming),
            "streaming_names": [s["plain_name"] for s in streaming],
            "indian_govt": sum(1 for s in self._sources.values() if s["is_indian_govt"]),
        }


registry = SourceRegistry()
