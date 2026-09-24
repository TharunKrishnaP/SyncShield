"""Append-only time-series lake persisted to SQLite.

Every refresh cycle appends three compact streams so the dashboard can show
history and trends without keeping gigabytes in RAM:

  water_levels   — per monitoring station: water level vs warning/danger, rise rate
  precipitation  — per zone: observed rain, next-6h / next-24h forecast totals
  zone_risk      — per zone: AI overall score and severity level

Records are pruned past ``HISTORY_RETENTION_HOURS``. Thread-safe by opening a
fresh connection per write/read (writes are tiny and infrequent).
"""
import os
import sqlite3
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from ..config import settings


class HistoryLake:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.HISTORY_DB_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_lock = threading.Lock()
        self._init_schema()

    # ---- schema ----
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._init_lock:
            conn = self._connect()
            try:
                conn.executescript(
                    """
                    PRAGMA journal_mode=WAL;
                    CREATE TABLE IF NOT EXISTS water_levels(
                        station_id TEXT NOT NULL,
                        ts TEXT NOT NULL,
                        water_level REAL,
                        warning_level REAL,
                        danger_level REAL,
                        rate_of_rise REAL,
                        status TEXT,
                        PRIMARY KEY (station_id, ts)
                    );
                    CREATE TABLE IF NOT EXISTS precipitation(
                        zone_id TEXT NOT NULL,
                        ts TEXT NOT NULL,
                        rain_now_mm REAL,
                        next_6h_mm REAL,
                        next_24h_mm REAL,
                        PRIMARY KEY (zone_id, ts)
                    );
                    CREATE TABLE IF NOT EXISTS zone_risk(
                        zone_id TEXT NOT NULL,
                        ts TEXT NOT NULL,
                        score REAL,
                        level TEXT,
                        PRIMARY KEY (zone_id, ts)
                    );
                    CREATE INDEX IF NOT EXISTS idx_wl_ts ON water_levels(ts);
                    CREATE INDEX IF NOT EXISTS idx_pc_ts ON precipitation(ts);
                    CREATE INDEX IF NOT EXISTS idx_zr_ts ON zone_risk(ts);
                    """
                )
                conn.commit()
            finally:
                conn.close()

    # ---- append ----
    def append(self, state: Dict[str, Any]) -> Dict[str, int]:
        """Append one refresh cycle's snapshot. Returns counts appended."""
        now = datetime.now().isoformat(timespec="seconds")
        counts = {"water": 0, "precip": 0, "risk": 0}
        conn = self._connect()
        try:
            with conn:
                conn.executemany(
                    "INSERT OR REPLACE INTO water_levels(station_id, ts, water_level, warning_level, danger_level, rate_of_rise, status) "
                    "VALUES (?,?,?,?,?,?,?)",
                    [
                        (
                            r.get("station_id"),
                            now,
                            r.get("water_level"),
                            r.get("warning_level"),
                            r.get("danger_level"),
                            r.get("rate_of_rise"),
                            r.get("status"),
                        )
                        for r in state.get("water_levels", [])
                        if r.get("station_id")
                    ],
                )
                counts["water"] = len(state.get("water_levels", []))
                conn.executemany(
                    "INSERT OR REPLACE INTO precipitation(zone_id, ts, rain_now_mm, next_6h_mm, next_24h_mm) "
                    "VALUES (?,?,?,?,?)",
                    [
                        (
                            r.get("zone_id"),
                            now,
                            r.get("rain_now_mm"),
                            r.get("next_6h_mm"),
                            r.get("next_24h_mm"),
                        )
                        for r in state.get("precipitation", [])
                        if r.get("zone_id")
                    ],
                )
                counts["precip"] = len(state.get("precipitation", []))
                conn.executemany(
                    "INSERT OR REPLACE INTO zone_risk(zone_id, ts, score, level) VALUES (?,?,?,?)",
                    [
                        (zid, now, z.get("overall_score"), z.get("severity_level"))
                        for zid, z in state.get("zones", {}).items()
                    ],
                )
                counts["risk"] = len(state.get("zones", {}))
                conn.execute(
                    "DELETE FROM water_levels WHERE ts < ?",
                    ((datetime.now() - timedelta(hours=settings.HISTORY_RETENTION_HOURS)).isoformat(),),
                )
                conn.execute(
                    "DELETE FROM precipitation WHERE ts < ?",
                    ((datetime.now() - timedelta(hours=settings.HISTORY_RETENTION_HOURS)).isoformat(),),
                )
                conn.execute(
                    "DELETE FROM zone_risk WHERE ts < ?",
                    ((datetime.now() - timedelta(hours=settings.HISTORY_RETENTION_HOURS)).isoformat(),),
                )
        finally:
            conn.close()
        return counts

    # ---- backfill from the in-memory datalake (only newer rows) ----
    def backfill_from_datalake(self, datalake) -> Dict[str, int]:
        """Seed history from datalake ring buffers so trends exist before the
        first full hour of refreshes has elapsed. Idempotent: only records
        newer than the last stored ts are inserted."""
        counts = {"water": 0, "precip": 0}
        last_ts = {"water": None, "precip": None}
        conn = self._connect()
        try:
            with conn:
                row = conn.execute("SELECT MAX(ts) t FROM water_levels").fetchone()
                last_ts["water"] = row["t"]
                row = conn.execute("SELECT MAX(ts) t FROM precipitation").fetchone()
                last_ts["precip"] = row["t"]
        finally:
            conn.close()

        water_rows, precip_rows = [], []
        for sid, bucket in datalake.list("river").items():
            for rec in bucket.get("records", []):
                ts = rec.get("timestamp") or rec.get("ts")
                if not ts:
                    continue
                if last_ts["water"] and ts <= last_ts["water"]:
                    continue
                water_rows.append(
                    (
                        sid, ts, rec.get("water_level"), rec.get("warning_level"),
                        rec.get("danger_level"), rec.get("rate_of_rise"), rec.get("status"),
                    )
                )
        for zid, bucket in datalake.list("weather").items():
            for rec in bucket.get("records", []):
                ts = rec.get("timestamp") or rec.get("ts")
                if not ts:
                    continue
                if last_ts["precip"] and ts <= last_ts["precip"]:
                    continue
                cur = rec.get("rain")
                if cur is None:
                    cur = rec.get("precipitation", 0.0)
                fc = rec.get("forecast_precipitation") or []
                precip_rows.append(
                    (
                        zid, ts, float(cur or 0.0),
                        round(sum(x for x in fc[:6] if isinstance(x, (int, float))), 1),
                        round(sum(x for x in fc[:24] if isinstance(x, (int, float))), 1),
                    )
                )
        if water_rows or precip_rows:
            conn = self._connect()
            try:
                with conn:
                    if water_rows:
                        conn.executemany(
                            "INSERT OR REPLACE INTO water_levels(station_id, ts, water_level, warning_level, danger_level, rate_of_rise, status) "
                            "VALUES (?,?,?,?,?,?,?)", water_rows,
                        )
                    if precip_rows:
                        conn.executemany(
                            "INSERT OR REPLACE INTO precipitation(zone_id, ts, rain_now_mm, next_6h_mm, next_24h_mm) "
                            "VALUES (?,?,?,?,?)", precip_rows,
                        )
            finally:
                conn.close()
            counts["water"] = len(water_rows)
            counts["precip"] = len(precip_rows)
        return counts

    # ---- queries ----
    @staticmethod
    def _ts_limit(hours: int) -> str:
        return (datetime.now() - timedelta(hours=hours)).isoformat()

    def water_history(self, station_id: str, hours: int = 24, limit: int = 96) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT station_id, ts, water_level, warning_level, danger_level, rate_of_rise, status "
                "FROM water_levels WHERE station_id = ? AND ts >= ? "
                "ORDER BY ts LIMIT ?",
                (station_id, self._ts_limit(hours), limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def water_history_many(self, station_ids: List[str], hours: int = 24, limit: int = 96) -> Dict[str, List[Dict]]:
        out: Dict[str, List[Dict]] = {}
        for sid in station_ids:
            out[sid] = self.water_history(sid, hours=hours, limit=limit)
        return out

    def precip_history(self, zone_id: str, hours: int = 24, limit: int = 96) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT zone_id, ts, rain_now_mm, next_6h_mm, next_24h_mm "
                "FROM precipitation WHERE zone_id = ? AND ts >= ? "
                "ORDER BY ts LIMIT ?",
                (zone_id, self._ts_limit(hours), limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def precip_history_many(self, zone_ids: List[str], hours: int = 24, limit: int = 96) -> Dict[str, List[Dict]]:
        out: Dict[str, List[Dict]] = {}
        for zid in zone_ids:
            out[zid] = self.precip_history(zid, hours=hours, limit=limit)
        return out

    def risk_history(self, zone_id: str, hours: int = 24, limit: int = 96) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT zone_id, ts, score, level FROM zone_risk "
                "WHERE zone_id = ? AND ts >= ? ORDER BY ts LIMIT ?",
                (zone_id, self._ts_limit(hours), limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def summary(self) -> Dict[str, Any]:
        conn = self._connect()
        try:
            oldest = conn.execute("SELECT MIN(ts) t FROM water_levels").fetchone()
            newest = conn.execute("SELECT MAX(ts) t FROM water_levels").fetchone()
            w = conn.execute("SELECT COUNT(DISTINCT station_id) c FROM water_levels").fetchone()
            p = conn.execute("SELECT COUNT(DISTINCT zone_id) c FROM precipitation").fetchone()
            r = conn.execute("SELECT COUNT(DISTINCT zone_id) c FROM zone_risk").fetchone()
            return {
                "db": os.path.basename(self.db_path),
                "water_stations": w["c"],
                "precip_zones": p["c"],
                "risk_zones": r["c"],
                "oldest": oldest["t"],
                "newest": newest["t"],
            }
        finally:
            conn.close()


history_lake = HistoryLake()