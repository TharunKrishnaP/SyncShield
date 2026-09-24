"""Real-time news feed for the FDR dashboard.

Derives a rolling, timestamped news stream from the platform's own live
signals — official alerts, CWC/NWDP level changes, ingested official
bulletins, verified citizen reports, heavy-rain heads-ups and regional score
moves — so the dashboard always shows *why* the numbers moved.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

_HEAVY_RAIN_MM = 61.0
_HAIL_RAIN_MM = 15.0
_WINDOW = timedelta(hours=6)
_CAP = 40

_TYPE_LABEL = {
    "ALERT": "Official alert",
    "LEVEL_CHANGE": "River level change",
    "BULLETIN": "Official bulletin",
    "CITIZEN": "Verified citizen report",
    "RAIN": "Rain outlook",
    "REGIONAL": "Regional situation",
    "EVACUATION": "Evacuation",
}

_SEVERITY_ORDER = {"LOW": 0, "MODERATE": 1, "HIGH": 2, "VERY_HIGH": 3, "CRITICAL": 4}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _max_severity(rows: List[Any]) -> str:
    best = "LOW"
    for s in rows:
        try:
            tok = str(s or "").upper()
        except Exception:
            continue
        if tok not in _SEVERITY_ORDER:
            try:
                f = float(s or 0)
                tok = "CRITICAL" if f >= 4.5 else "VERY_HIGH" if f >= 3.5 else "HIGH" if f >= 2.5 else "MODERATE" if f >= 1.5 else "LOW"
            except Exception:
                continue
        if _SEVERITY_ORDER.get(tok, 0) > _SEVERITY_ORDER.get(best, 0):
            best = tok
    return best


class NewsFeed:
    def __init__(self):
        self._items: List[Dict[str, Any]] = []
        self._known: set = set()

    def items(self, limit: int = 20) -> List[Dict[str, Any]]:
        return self._items[:limit]

    def build(
        self,
        state: Dict[str, Any],
        prev: Optional[Dict[str, Any]] = None,
        datalake: Any = None,
    ) -> List[Dict[str, Any]]:
        now = _now()
        fresh: List[Dict[str, Any]] = []

        # --- Official / SACHET / NDMA alerts --------------------------------
        for a in state.get("alerts", []) or []:
            aid = a.get("id") or a.get("source_id")
            if not aid:
                continue
            headline = a.get("headline") or a.get("title") or a.get("message") or "Official flood alert"
            body = (
                a.get("description")
                or a.get("summary")
                or f"{a.get('type', 'Alert')} in {a.get('zone_name') or a.get('state') or 'India'}"
            )
            severity = _max_severity([a.get("severity")]) or "HIGH"
            if severity not in _SEVERITY_ORDER:
                severity = "HIGH"
            fresh.append({
                "_key": f"ALERT:{aid}",
                "id": aid,
                "type": "ALERT",
                "headline": headline,
                "body": body,
                "severity": severity,
                "zone_id": a.get("zone_id"),
                "zone_name": a.get("zone_name") or a.get("district"),
                "state": a.get("state"),
                "source": (a.get("source") or "NDMA/SACHET").upper(),
                "published_at": a.get("published_at") or a.get("timestamp") or now.isoformat(),
            })

        # --- River level transitions (NORMAL/ABOVE_NORMAL -> SEVERE/EXTREME) --
        prev_water = {r.get("station_id"): r.get("status") for r in (prev or {}).get("water_levels", []) or []}
        cur_water = {r.get("station_id"): r.get("status") for r in state.get("water_levels", []) or []}
        WATCH = {"ABOVE_NORMAL", "SEVERE", "EXTREME"}
        for wid, status in cur_water.items():
            if status in WATCH and prev_water.get(wid) not in WATCH:
                if status == "EXTREME":
                    head = f"{wid.replace('CWC-','')} at extreme danger level"
                    sev = "CRITICAL"
                elif status == "SEVERE":
                    head = f"{wid.replace('CWC-','')} crossed warning level"
                    sev = "VERY_HIGH"
                else:
                    head = f"{wid.replace('CWC-','')} above normal"
                    sev = "HIGH"
                row = next((r for r in state.get("water_levels", []) if r.get("station_id") == wid), {})
                fresh.append({
                    "_key": f"LEVEL:{wid}:{status}",
                    "id": f"lv-{wid}-{int(now.timestamp())}",
                    "type": "LEVEL_CHANGE",
                    "headline": head,
                    "body": (
                        f"{row.get('water_level')} m in {row.get('river')} ({row.get('state')}) "
                        f"vs warning {row.get('warning_level')} m (danger {row.get('danger_level')} m)."
                    ),
                    "severity": sev,
                    "zone_id": row.get("station_id"),
                    "zone_name": row.get("station") or row.get("station_id"),
                    "state": row.get("state"),
                    "source": "CWC/NWDP",
                    "published_at": now.isoformat(),
                })

        # --- Escalating priority zones ---------------------------------------
        prev_zones = (prev or {}).get("zones", {}) or {}
        cur_zones = state.get("zones", {}) or {}
        for zid, z in cur_zones.items():
            score = float(z.get("overall_score") or 0.0)
            pscore = float((prev_zones.get(zid) or {}).get("overall_score") or 0.0)
            if score >= 60 and pscore < 60:
                fresh.append({
                    "_key": f"ZONE:{zid}:{int(score)}:{int(now.timestamp() // 600)}",
                    "id": f"zone-{zid}-{int(now.timestamp())}",
                    "type": "ALERT",
                    "headline": f"{z.get('district') or z.get('zone_name')} flood situation escalating",
                    "body": f"Risk score now {round(score)}/100 in {z.get('state')} — authorities advised to activate response.",
                    "severity": _max_severity([z.get("severity_level"), "HIGH"]),
                    "zone_id": zid,
                    "zone_name": z.get("district") or z.get("zone_name"),
                    "state": z.get("state"),
                    "source": "SITUATION_SCORER",
                    "published_at": now.isoformat(),
                })
            elif score >= 80 and pscore < 80:
                fresh.append({
                    "_key": f"ZONE-C:{zid}:{int(now.timestamp() // 600)}",
                    "id": f"zonec-{zid}-{int(now.timestamp())}",
                    "type": "ALERT",
                    "headline": f"{z.get('district') or z.get('zone_name')} at critical risk",
                    "body": f"Risk score {round(score)}/100 — immediate evacuation recommended.",
                    "severity": "CRITICAL",
                    "zone_id": zid,
                    "zone_name": z.get("district") or z.get("zone_name"),
                    "state": z.get("state"),
                    "source": "SITUATION_SCORER",
                    "published_at": now.isoformat(),
                })

        # --- Heavy rain outlooks ----------------------------------------------
        for w in state.get("precipitation", []) or []:
            rain24 = float(w.get("next_24h_mm") or 0.0)
            if rain24 >= _HEAVY_RAIN_MM:
                cat = "Extremely heavy" if rain24 >= 250 else "Very heavy" if rain24 >= 121 else "Heavy"
                fresh.append({
                    "_key": f"RAIN:{w.get('zone_id')}:{int(rain24)}:{int(now.timestamp() // 900)}",
                    "id": f"rain-{w.get('zone_id')}-{int(now.timestamp())}",
                    "type": "RAIN",
                    "headline": f"{cat} rain expected — {w.get('name') or w.get('zone_id')}",
                    "body": f"{round(rain24)} mm in next 24 h, {round(float(w.get('rain_now_mm') or 0), 1)} mm falling now.",
                    "severity": "CRITICAL" if rain24 >= 250 else "VERY_HIGH" if rain24 >= 121 else "HIGH",
                    "zone_id": w.get("zone_id"),
                    "zone_name": w.get("name") or w.get("zone_id"),
                    "state": w.get("state"),
                    "source": "IMD/OPEN-METEO",
                    "published_at": now.isoformat(),
                })

        # --- Official bulletins & verified citizen reports -------------------
        if datalake is not None:
            try:
                for inc in datalake.get_incidents(limit=300):
                    stamp = inc.get("submitted_at") or inc.get("timestamp") or ""
                    try:
                        when = datetime.fromisoformat(stamp)
                        if when.tzinfo is None:
                            when = when.replace(tzinfo=timezone.utc)
                    except Exception:
                        continue
                    if now - when > _WINDOW:
                        continue
                    nlp = inc.get("nlp_extracted") or {}
                    src = (inc.get("source") or "").upper()
                    if src == "OFFICIAL_BULLETIN" or nlp.get("official_alert"):
                        fresh.append({
                            "_key": f"BULLETIN:{inc.get('id')}",
                            "id": f"bul-{inc.get('id')}",
                            "type": "BULLETIN",
                            "headline": (inc.get("description") or inc.get("location_name"))[:120],
                            "body": f"{inc.get('location_name')} · {inc.get('category')} ({inc.get('severity') or 'n/a'})",
                            "severity": _max_severity([inc.get("severity") or "", "HIGH"]),
                            "zone_id": inc.get("zone_id"),
                            "zone_name": inc.get("location_name"),
                            "state": inc.get("state"),
                            "source": "OFFICIAL BULLETIN",
                            "published_at": when.isoformat(),
                        })
                    elif inc.get("verified") and src == "CITIZEN_REPORT":
                        fresh.append({
                            "_key": f"CITIZEN:{inc.get('id')}",
                            "id": f"citn-{inc.get('id')}",
                            "type": "CITIZEN",
                            "headline": f"Verified field report — {inc.get('location_name')}",
                            "body": inc.get("description") or inc.get("category") or "Confirmed by district control room.",
                            "severity": _max_severity([inc.get("severity") or "", "MODERATE"]),
                            "zone_id": inc.get("zone_id"),
                            "zone_name": inc.get("location_name"),
                            "state": inc.get("state"),
                            "source": "CITIZEN/EOC",
                            "published_at": when.isoformat(),
                        })
            except Exception:
                pass

        # --- Regional score move ----------------------------------------------
        cur_reg = state.get("regional", {}) or {}
        prev_reg = (prev or {}).get("regional", {}) or {}
        cur_score = float(cur_reg.get("score") or 0.0)
        if abs(cur_score - float(prev_reg.get("score") or 0.0)) >= 2.0:
            direction = "rising" if cur_score > prev_reg.get("score", 0) else "easing"
            fresh.append({
                "_key": f"REG:{int(cur_score)}:{int(now.timestamp() // 900)}",
                "id": f"reg-{int(now.timestamp())}",
                "type": "REGIONAL",
                "headline": f"National flood risk {direction} — now {round(cur_score)}/100",
                "body": f"{cur_reg.get('affected_zones') or 0} zones affected, {cur_reg.get('status') or 'STABLE'}.",
                "severity": _max_severity([cur_reg.get("status"), "LOW"]),
                "zone_id": None,
                "zone_name": "India",
                "state": "All India",
                "source": "REGIONAL SCORER",
                "published_at": now.isoformat(),
            })

        # Merge: keep newest first, dedupe, window/cap.
        seen_now: set = set()
        ordered = sorted(fresh, key=lambda x: x["published_at"], reverse=True)
        for item in ordered:
            key = item["_key"]
            if key in seen_now:
                continue
            seen_now.add(key)
            if key in self._known:
                continue
            self._known.add(key)
            clean = {k: v for k, v in item.items() if not k.startswith("_")}
            clean["label"] = _TYPE_LABEL.get(clean["type"], clean["type"])
            self._items.append(clean)

        cutoff = now - _WINDOW
        self._items = [i for i in self._items if _parse_ts(i.get("published_at")) >= cutoff][:_CAP]
        self._items.sort(key=lambda i: i.get("published_at") or "", reverse=True)
        return self.items(_CAP)


def _parse_ts(ts: Optional[str]) -> datetime:
    if not ts:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(ts)
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


news_feed = NewsFeed()