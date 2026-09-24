import json
import os
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..config import settings


class DataLake:
    """File-persisted, in-memory JSON/GeoJSON datalake partitioned by modality.

    Partitions mirror the FDR architecture:
      satellite/  - SAR flood extents at discrete timestamps
      weather/    - precipitation, temperature, forecast history
      river/      - station sensor readings (water_level, danger_level, rate_of_rise)
      incidents/  - raw and NLP-processed citizen/field reports
      infrastructure/ - hospitals, bases, shelters, vulnerable roads
      zones/      - zone registry and dynamic scores
      timeline/   - append-only event log
    """

    def __init__(self, path: Optional[str] = None):
        self.path = path or settings.DATA_LAKE_PATH
        os.makedirs(self.path, exist_ok=True)
        self._lock = threading.RLock()
        self._store: Dict[str, Any] = {
            "satellite": {},
            "weather": {},
            "river": {},
            "incidents": [],
            "infrastructure": {},
            "zones": {},
            "timeline": [],
            "routes": {},
        }
        self._dirty = False
        self._last_persist = time.time()

    # ---- lifecycle ----
    def load(self):
        index_file = os.path.join(self.path, "index.json")
        if os.path.exists(index_file):
            with self._lock:
                with open(index_file, "r", encoding="utf-8") as fh:
                    self._store = json.load(fh)
        return self

    def persist(self, force: bool = False) -> bool:
        """Persist to disk, throttled by settings interval unless forced."""
        now = time.time()
        with self._lock:
            if not force and now - self._last_persist < settings.DATA_LAKE_PERSIST_INTERVAL:
                return False
            tmp = os.path.join(self.path, "index.json.tmp")
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._store, fh, default=str)
            os.replace(tmp, os.path.join(self.path, "index.json"))
            self._last_persist = now
            self._dirty = False
        return True

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._store, default=str))

    # ---- generic helpers ----
    def _partition(self, key: str) -> Dict[str, Any]:
        return self._store.setdefault(key, {})

    def put(self, partition: str, item_key: str, value: Any):
        with self._lock:
            self._partition(partition)[item_key] = value
            self._dirty = True

    def get(self, partition: str, item_key: str, default: Any = None):
        with self._lock:
            return self._partition(partition).get(item_key, default)

    def list(self, partition: str) -> Dict[str, Any]:
        with self._lock:
            return dict(self._partition(partition))

    # ---- satellite ----
    def put_satellite_extent(self, item: Dict[str, Any]):
        key = item.get("id") or f"extent_{item.get('timestamp', datetime.now().isoformat())}"
        self.put("satellite", key, item)

    def get_satellite_extents(self) -> List[Dict[str, Any]]:
        items = list(self.list("satellite").values())
        items.sort(
            key=lambda x: x.get("timestamp", "") if isinstance(x.get("timestamp", ""), str) else str(x.get("timestamp", "")),
        )
        latest_by_zone = {}
        for item in items:
            latest_by_zone[item.get("zone_id", item.get("id"))] = item
        return list(latest_by_zone.values())

    # ---- weather ----
    def put_weather(self, location_id: str, record: Dict[str, Any]):
        bucket = self._partition("weather").setdefault(location_id, {"records": [], "latest": None})
        bucket["records"].append(record)
        bucket["latest"] = record
        bucket["records"] = bucket["records"][-720:]  # keep ~30 days of hourly records
        self._dirty = True

    def get_weather(self, location_id: str) -> Dict[str, Any]:
        return self._partition("weather").get(location_id, {"records": [], "latest": None})

    def weather_latest_all(self) -> Dict[str, Dict[str, Any]]:
        return {k: v["latest"] for k, v in self.list("weather").items() if v.get("latest")}

    # ---- river ----
    def put_river_reading(self, station_id: str, record: Dict[str, Any]):
        bucket = self._partition("river").setdefault(station_id, {"records": [], "latest": None, "metadata": {}})
        bucket["records"].append(record)
        bucket["latest"] = record
        bucket["records"] = bucket["records"][-240:]
        self._dirty = True

    def put_river_metadata(self, station_id: str, metadata: Dict[str, Any]):
        self._partition("river").setdefault(station_id, {"records": [], "latest": None, "metadata": {}})[
            "metadata"
        ] = metadata
        self._dirty = True

    def get_river(self, station_id: str) -> Dict[str, Any]:
        return self._partition("river").get(station_id, {"records": [], "latest": None, "metadata": {}})

    def river_latest_all(self) -> Dict[str, Dict[str, Any]]:
        return {k: v["latest"] for k, v in self.list("river").items() if v.get("latest")}

    # ---- incidents ----
    def add_incident(self, incident: Dict[str, Any]):
        with self._lock:
            self._store["incidents"].append(incident)
            self._dirty = True
        return incident

    def get_incidents(self, limit: Optional[int] = None, zone: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self._store["incidents"])
        if zone:
            items = [i for i in items if i.get("zone_id") == zone]
        items.sort(key=lambda i: i.get("timestamp", ""), reverse=True)
        return items[:limit] if limit else items

    # ---- zones ----
    def put_zone(self, zone: Dict[str, Any]):
        self.put("zones", zone["id"], zone)

    def get_zone(self, zone_id: str) -> Optional[Dict[str, Any]]:
        return self.get("zones", zone_id)

    def zones_all(self) -> List[Dict[str, Any]]:
        return list(self.list("zones").values())

    # ---- timeline ----
    def log_event(self, event: Dict[str, Any]):
        with self._lock:
            self._store["timeline"].append(event)
            self._dirty = True

    def timeline(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self._store["timeline"])
        items.sort(key=lambda i: i.get("timestamp", ""), reverse=True)
        return items[:limit] if limit else items