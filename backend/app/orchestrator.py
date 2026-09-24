"""Orchestrates the full ingest → datalake → AI intelligence → broadcast cycle.

Owns shared singletons for DataLake, weather/river/satellite ingestion,
live GloFAS river discharge, official GDACS/EONET alerts, situation scoring,
conflict detection, explainability, rescue prioritization, routing, decision
recommendations and the plain-language citizen brief.
"""
import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

from .config import settings
from .datalake.data_store import DataLake
from .ingestion.weather_client import WeatherClient, IMDClient
from .ingestion.river_gauges import RiverGaugeService, NWDP_KEY
from .ingestion.flood_forecast import FloodForecastClient
from .ingestion.official_alerts import OfficialAlertsClient
from .ingestion.source_registry import registry, REFERENCE, NEEDS_KEY, UNAVAILABLE, SIMULATED
from .ingestion.official_connectors import official_connectors, auto_register_bulletin_source
from .ingestion.map_tiles import map_tiles
from .ingestion.sar_satellite import SARProcessor, BhoonidhiClient, NDMPortalClient
from .ai_engine.situation_scorer import SituationScorer
from .ai_engine.conflict_detector import ConflictDetector
from .ai_engine.explainability import ExplainabilityEngine
from .ai_engine.rescue_prioritizer import compute_rescue_priorities
from .ai_engine.flood_routing import compute_route_risk, precompute_zone_routes
from .ai_engine.decision_recommender import DecisionRecommender
from .ai_engine.nlp_extractor import extract_incident
from .ai_engine.plain_language import build_brief
from .history.history_lake import HistoryLake
from .news.feed import news_feed
from .models.india_data import ZONES, ZONE_INDEX, INFRASTRUCTURE, VULNERABLE_ROADS
from .models.emergency_data import contacts_payload
from .simulation import SimulationEngine

_RAIN_CATEGORIES = [
    (250, "Extremely heavy"),
    (121, "Very heavy"),
    (61, "Heavy"),
    (31, "Rather heavy"),
    (11, "Moderate"),
    (1, "Light"),
    (0, "No rain"),
]

_WIND_GRID_POINTS = [
    (lat, lon)
    for lat in (9.0, 14.5, 20.0, 25.5, 31.0)
    for lon in (70.0, 76.0, 82.0, 88.0, 94.0)
]


def _rain_category(mm: float) -> str:
    for threshold, label in _RAIN_CATEGORIES:
        if mm >= threshold:
            return label
    return "No rain"


_STATUS_ORDER = {"EXTREME": 0, "SEVERE": 1, "ABOVE_NORMAL": 2, "NORMAL": 3}


def _water_flood_relevance(r: Dict[str, Any]) -> float:
    """0..10 flood relevance for a river gauge row.

    Severity band anchors the score; danger proximity (how close the water
    level is to warning/danger), rate of rise and the live GloFAS flow
    anomaly push it higher. Used to order the water-level panel within the
    severity ranking.
    """
    base = {"EXTREME": 2.5, "SEVERE": 1.6, "ABOVE_NORMAL": 0.8, "NORMAL": 0.0}.get(
        r.get("status", "NORMAL"), 0.0
    )
    wl = float(r.get("water_level") or 0.0)
    warn = float(r.get("warning_level") or 0.0)
    dl = float(r.get("danger_level") or max(warn + 0.1, 1.0))
    span = max(dl - warn, 0.1)
    proximity = min(max((wl - warn) / span, 0.0), 2.0)
    rise = max(float(r.get("rate_of_rise") or 0.0), 0.0)
    rise_score = min(rise / 15.0, 1.5)  # cm/h -> up to +1.5
    ratio = float(r.get("flow_ratio") or 1.0)
    flow_score = min(max((ratio - 1.0) / 2.0, 0.0), 1.5)  # live flow anomaly -> up to +1.5
    return round(min(base + proximity + rise_score + flow_score, 10.0), 2)


def _precip_flood_relevance(w: Dict[str, Any]) -> float:
    """0..10 flood relevance for a district rainfall row.

    Rank = rainfall intensity (now + 6h + 24h forecast) × the district's
    flood exposure, so heavy rain on a flood-prone district outranks the
    same rain on a dry interior district.
    """
    zone = ZONE_INDEX.get(w.get("location_id")) or {}
    flood_prone = bool(zone.get("flood_prone"))
    cur = float(w.get("rain") if w.get("rain") is not None else (w.get("precipitation") or 0.0))
    fc = w.get("forecast_precipitation") or []
    next6 = sum(x for x in fc[:6] if isinstance(x, (int, float)))
    next24 = sum(x for x in fc[:24] if isinstance(x, (int, float)))
    intensity = (
        min(cur / 30.0, 1.0) * 0.4
        + min(next6 / 60.0, 1.0) * 0.3
        + min(next24 / 150.0, 1.0) * 0.3
    )
    risk = 1.4 if flood_prone else 0.8
    return round(min(intensity * risk * 10.0, 10.0), 2)


class FDROrchestrator:
    def __init__(self):
        self.datalake = DataLake().load()
        self.weather = WeatherClient()
        self.imd = IMDClient()
        self.flood_forecast = FloodForecastClient()
        self.alerts_client = OfficialAlertsClient()
        self.river_service = RiverGaugeService(simulate=settings.SIMULATION_ENABLED)
        self.sar = SARProcessor()
        self.bhoonidhi = BhoonidhiClient()
        self.ndem = NDMPortalClient()
        self.scorer = SituationScorer()
        self.conflict_detector = ConflictDetector()
        self.explainer = ExplainabilityEngine()
        self.recommender = DecisionRecommender()
        self.simulation = SimulationEngine()
        self.history = HistoryLake()
        self.official = official_connectors
        self.news = news_feed
        auto_register_bulletin_source()

        self._current: Dict[str, Any] = {}
        self._last_state: Dict[str, Any] = {}
        self._lock = asyncio.Lock()
        self._subscribers: List[asyncio.Queue] = []
        self._incident_seed_step = -1
        self._ingested_alerts: set = set()
        self._official_alerts: List[Dict[str, Any]] = []
        self._wind_grid: List[Dict[str, Any]] = []
        self._register_platform_sources()

        self._seed_incidents = [
            ("AS-Kamrup Metropolitan", "Water surging above NH-27 embankment near Pandu, Guwahati, boats needed for 30 families"),
            ("AS-Dhubri", "Brahmaputra breach at Fakirganj, Dhubri, water entering 3 villages"),
            ("BR-Patna", "Heavy waterlogging in Patna near Gandhi Ghat, 6 people stranded on rooftop"),
            ("BR-Bhagalpur", "Ganga overtopping embankment at Nathnagar, Bhagalpur, rescue boat requested"),
            ("WB-Murshidabad", "Severe waterlogging in Murshidabad near Lalbagh, 12 families trapped"),
            ("WB-Kolkata", "Street flooding in central Kolkata at Bowbazar, commuters stranded"),
            ("WB-Murshidabad", "Farakka barrage release raising water in neighbouring low-lying villages"),
            ("OD-Cuttack", "Flood wall overflow near Cuttack Ring Road, godown submerged, 25 people on terrace"),
            ("KL-Ernakulam", "Periyar flood water entering residential area in Aluva near the bridge, need evacuation"),
            ("AP-NTR", "Rising water near Sivaji Nagar Vijayawada, boats needed for 45 families"),
            ("MH-Sangli", "Krishna backwater flooding Sangli lowlands, 20 families evacuated to higher ground"),
            ("UP-Varanasi", "Ganga level rising at Assi Ghat, Varanasi, steps submerged, boat ops underway"),
            ("UP-Prayagraj", "Yamuna inflow at Sangam bund, Prayagraj, minor breach, sandbagging in progress"),
            ("DL-East Delhi", "Yamuna at warning level near Akshardham, Delhi, low-lying colonies at risk"),
            ("GJ-Ahmedabad", "Sabarmati overflow into Naroda Gam, Ahmedabad, relief material dispatched"),
            ("TG-Hyderabad", "Musi river surge near Osmania University, Hyderabad, 3 colonies waterlogged"),
            ("AS-Sonitpur", "Brahmaputra rising at Tezpur, erosion at Kolabari, sandbag walls requested"),
            ("BR-Darbhanga", "Kamala river breach near Laheriasarai, Darbhanga, paddy fields inundated"),
        ]

    # ------------------------------------------------------------------
    # Source registration
    # ------------------------------------------------------------------
    def _register_platform_sources(self) -> None:
        """Register the Indian government feeds this platform draws on.

        Feeds that require accreditation are surfaced honestly as reference
        links rather than being presented as if they were being polled.
        """
        registry.register(
            "open_meteo_weather",
            "Open-Meteo Weather Forecast",
            "https://api.open-meteo.com/",
            category="international",
            coverage="Every Indian district (gridded)",
            plain_name="Rain and weather readings",
            what_it_gives="Live rainfall, temperature, humidity and wind for every zone",
            realtime=True,
        )
        registry.register(
            "imd",
            "India Meteorological Department (IMD)",
            "https://api.imd.gov.in/",
            category="official_govt",
            coverage="All India",
            is_indian_govt=True,
            requires_key=True,
            plain_name="IMD weather warnings",
            what_it_gives="IMD rainfall warnings and district forecasts",
        )
        registry.set_status("imd", NEEDS_KEY, "IMD issues API keys only to accredited agencies. Rainfall is mirrored from the same Open-Meteo model IMD uses for public forecasts.")
        registry.register(
            "cwc_ffs",
            "CWC Flood Forecasting Portal (FFS / 7-day advisory / C-Floods)",
            "https://ffs.india-water.gov.in/",
            category="official_govt",
            coverage="360 flood forecasting stations, 20 river basins",
            is_indian_govt=True,
            kind="portal",
            plain_name="CWC flood forecasts",
            what_it_gives="Official flood forecasts for 360 stations on 20 river basins",
        )
        registry.set_status("cwc_ffs", REFERENCE, "Official portal; station thresholds are used directly and live flow is supplied by GloFAS.")
        registry.register(
            "bhuvan",
            "ISRO Bhuvan Flood Early Warning (FEWS)",
            "https://bhuvan-app1.nrsc.gov.in/fews/",
            category="official_govt",
            coverage="All India",
            is_indian_govt=True,
            kind="portal",
            plain_name="ISRO flood maps",
            what_it_gives="ISRO satellite-based flood inundation maps",
        )
        registry.set_status("bhuvan", REFERENCE, "ISRO portal; SAR extents are modelled until Bhoonidhi credentials are supplied.")
        registry.register(
            "bhoonidhi",
            "ISRO Bhoonidhi (Sentinel-1 SAR archive)",
            "https://bhoonidhi.nrsc.gov.in/",
            category="official_govt",
            coverage="All India",
            is_indian_govt=True,
            requires_key=True,
            plain_name="ISRO satellite radar",
            what_it_gives="Sentinel-1 radar imagery for flood mapping",
        )
        registry.set_status("bhoonidhi", NEEDS_KEY, "Requires a Bhoonidhi account for programmatic downloads.")
        registry.register(
            "sachet",
            "NDMA SACHET Alert Portal",
            "https://sachet.ndma.gov.in/",
            category="official_govt",
            coverage="All India, state-wise CAP alerts",
            is_indian_govt=True,
            kind="portal",
            plain_name="NDMA alerts",
            what_it_gives="Official disaster alerts issued through NDMA's SACHET system",
        )
        registry.set_status("sachet", REFERENCE, "SACHET publishes alerts through its web portal; GDACS alerts are ingested programmatically.")
        registry.register(
            "ndem",
            "NDEM Disaster Portal (NRSC)",
            "https://ndem.nrsc.gov.in/",
            category="official_govt",
            coverage="All India",
            is_indian_govt=True,
            kind="portal",
            plain_name="NDEM disaster portal",
            what_it_gives="India's national disaster management portal",
        )
        registry.set_status("ndem", REFERENCE, "Portal access requires institutional login.")
        registry.register(
            "india_wris",
            "India-WRIS Water Resources Information System",
            "https://indiawris.gov.in/",
            category="official_govt",
            coverage="All India",
            is_indian_govt=True,
            kind="portal",
            plain_name="India water data portal",
            what_it_gives="Reservoir and water resource data for India",
        )
        registry.set_status("india_wris", REFERENCE, "Public portal; no key-free machine API.")
        registry.register(
            "rainviewer",
            "RainViewer Weather Radar",
            "https://www.rainviewer.com/",
            category="international",
            coverage="Global radar coverage, India included",
            plain_name="Live rain radar",
            what_it_gives="Real-time rain radar imagery on the map",
            realtime=True,
        )
        registry.register(
            "gibs",
            "NASA GIBS (IMERG precipitation + VIIRS imagery)",
            "https://gibs.earthdata.nasa.gov/",
            category="international",
            coverage="Global, India included",
            plain_name="NASA satellite precipitation",
            what_it_gives="Satellite precipitation and daily imagery tiles",
            realtime=True,
        )
        registry.register(
            "sentinel1_sar",
            "Sentinel-1 SAR flood extents (ISRO Bhoonidhi)",
            "https://bhuvan-app1.nrsc.gov.in/fews/",
            category="official_govt",
            coverage="Zones with rivers above warning level",
            kind="model",
            plain_name="Flood extent estimates",
            what_it_gives="Flooded area mapped from satellite radar once Bhoonidhi credentials are supplied",
        )

    # ------------------------------------------------------------------
    # Registration / seed data
    # ------------------------------------------------------------------
    async def bootstrap(self):
        for z in ZONES:
            self.datalake.put_zone(z)
        self.datalake.put("infrastructure", "hospitals", INFRASTRUCTURE["hospitals"])
        self.datalake.put("infrastructure", "rescue_bases", INFRASTRUCTURE["rescue_bases"])
        self.datalake.put("infrastructure", "shelters", INFRASTRUCTURE["shelters"])
        self.datalake.put("infrastructure", "roads", VULNERABLE_ROADS)
        self.datalake.log_event({
            "timestamp": datetime.now().isoformat(),
            "type": "SYSTEM",
            "message": "FDR DataLake bootstrapped: {} zones, {} basins registered.".format(len(ZONES), len(settings.MAJOR_BASINS)),
        })
        try:
            self.history.backfill_from_datalake(self.datalake)
        except Exception:
            pass
        await self.refresh(force=True)

    async def _safe(self, coro, default):
        try:
            return await coro
        except Exception:
            return default

    # ------------------------------------------------------------------
    # Public refresh cycle
    # ------------------------------------------------------------------
    async def refresh(self, force: bool = False) -> Dict[str, Any]:
        """Pull live data, run the AI engine, persist, broadcast."""
        async with self._lock:
            step = self.simulation.step
            surge = self.simulation.surge_factor()

            weather_live, live_flow, alerts, wind_grid, _map_cfg = await asyncio.gather(
                self._safe(self.weather.refresh_all_zones(), []),
                self._safe(self.flood_forecast.refresh_all(), {}),
                self._safe(self.alerts_client.refresh(), []),
                self._safe(self.weather.fetch_wind_grid(_WIND_GRID_POINTS), []),
                self._safe(map_tiles.config(), {}),
            )
            self._wind_grid = wind_grid
            self._official_alerts = alerts

            weather_map: Dict[str, Dict[str, Any]] = {}
            for w in weather_live:
                weather_map[w["location_id"]] = w
                self.datalake.put_weather(w["location_id"], w)

            try:
                await self.official.fetch_all(weather_map)
            except Exception:
                pass

            river_live = (
                self.river_service.advance(surge_factor=surge, live_map=live_flow)
                if settings.SIMULATION_ENABLED
                else self.river_service.read_all(live_map=live_flow)
            )
            river_map: Dict[str, Dict[str, Any]] = {}
            for r in river_live:
                if r.get("station_id"):
                    self.datalake.put_river_reading(r["station_id"], r)
                    river_map[r["station_id"]] = r

            # Real official CWC gauges (when NWDP_API_KEY is set) replace the
            # scenario levels for those stations.
            for sid, reading in {r["station_id"]: r for r in self.official.cwc_readings if r.get("station_id")}.items():
                river_map[sid] = reading

            zone_river_map = self._map_rivers_to_zones(river_map)

            if settings.SIMULATION_ENABLED:
                # Demo-only flood extents — never shown in real-time mode.
                # Zones with a real ML U-Net prediction (ingested via
                # /api/ai/sar/ingest) are excluded from the simulation so the
                # ingested extent stays the latest for that zone.
                ml_zones: set = set()
                try:
                    ml_zones = {
                        e["zone_id"] for e in self.datalake.get_satellite_extents()
                        if (e.get("data_source") or "").startswith("ML_SAR") and e.get("zone_id")
                    }
                except Exception:
                    pass
                self.sar.set_phase(step, surge)
                satellite_live = self.sar.generate_all()
                satellite_map: Dict[str, Dict[str, Any]] = {}
                for s in satellite_live:
                    zid = s["zone_id"]
                    riv = zone_river_map.get(zid)
                    keep = bool(
                        zid not in ml_zones
                        and riv
                        and riv.get("water_level", 0) >= riv.get("warning_level", 0)
                    )
                    if keep:
                        self.datalake.put_satellite_extent(s)
                        satellite_map[zid] = s
                # Real ML U-Net predictions take precedence over the modelled
                # extent for the zones they cover — live ML output inside the
                # demo (the sim above skipped those zones).
                try:
                    ml_extents = [
                        e for e in self.datalake.get_satellite_extents()
                        if (e.get("data_source") or "").startswith("ML_SAR")
                        and e.get("zone_id")
                    ]
                except Exception:
                    ml_extents = []
                for e in ml_extents:
                    satellite_map[e["zone_id"]] = e
                ml_note = " U-Net (real inference) covers {} zones.".format(len(ml_extents)) if ml_extents else ""
                registry.set_status(
                    "sentinel1_sar",
                    SIMULATED,
                    "Flood extents modelled from river levels; ISRO Bhoonidhi SAR download needs credentials.{}".format(ml_note),
                    records=len(satellite_map),
                )
            else:
                # Real-time mode: no simulated polygons. Flood extents come
                # from the trained ML SAR U-Net when Sentinel-1 scenes have
                # been ingested (POST /api/ai/sar/ingest) — filling the 0.35
                # satellite weight with real ML inference instead of 0.
                satellite_map = {}
                try:
                    ml_extents = [
                        e for e in self.datalake.get_satellite_extents()
                        if (e.get("data_source") or "").startswith("ML_SAR")
                        and e.get("zone_id")
                    ]
                except Exception:
                    ml_extents = []
                satellite_map = {e["zone_id"]: e for e in ml_extents}
                if satellite_map:
                    registry.set_status(
                        "sentinel1_sar",
                        LIVE,
                        "Flood extents from trained SAR U-Net inference over {} zones.".format(len(satellite_map)),
                        records=len(satellite_map),
                    )
                else:
                    registry.set_status(
                        "sentinel1_sar",
                        NEEDS_KEY,
                        "No ML SAR extents yet — train the U-Net (ml/sar/train_colab.ipynb) and ingest a Sentinel-1 scene via POST /api/ai/sar/ingest; simulated extents stay disabled in real-time mode.",
                        records=0,
                    )

            alerts = list(alerts) + [
                a for a in self.official.sachet_alerts if not any(o.get("id") == a.get("id") for o in alerts)
            ]
            self._ingest_official_alerts(alerts)

            if settings.SIMULATION_ENABLED and step != self._incident_seed_step:
                # Add each seed at most once as the scenario unfolds — re-running
                # the loop every step used to duplicate the whole list.
                existing_texts = {i.get("description") for i in self.datalake.get_incidents()}
                for i in range(0, min(step + 1, len(self._seed_incidents))):
                    zid, text = self._seed_incidents[i]
                    if text in existing_texts:
                        continue
                    try:
                        self._parse_incident(text, source="SIMULATED_REPORT", explicit_zone=zid)
                    except Exception:
                        continue
                self._incident_seed_step = step

            incidents_all = self.datalake.get_incidents()
            incident_map: Dict[str, List[Dict[str, Any]]] = {}
            for inc in incidents_all:
                zid = inc.get("zone_id")
                if zid:
                    incident_map.setdefault(zid, []).append(inc)

            result = self.scorer.compute_all(weather_map, zone_river_map, satellite_map, incident_map)
            zone_scores = result["zones"]
            regional = result["regional"]

            conflicts = self.conflict_detector.detect(zone_scores, weather_map, zone_river_map, satellite_map)[:14]

            explanations = self.explainer.generate_all(
                ZONES, zone_scores, weather_map, zone_river_map, satellite_map, incident_map
            )
            explanation_map = {e["zone_id"]: e for e in explanations}

            priorities = compute_rescue_priorities(zone_scores)
            routes = precompute_zone_routes(zone_scores, incidents_all)
            self.datalake.put("routes", "latest", routes)
            recommendations = self.recommender.generate(regional, zone_scores, priorities, conflicts)

            source_summary = registry.summary()
            updated_at = datetime.now().isoformat()
            brief = build_brief(
                regional, zone_scores, weather_map, zone_river_map,
                incidents_all, alerts, source_summary, updated_at=updated_at,
            )

            self.datalake.persist()

            prev_state = self._last_state or {}
            state = {
                "simulation": self.simulation.current_step_info | {"running": self.simulation.running, "speed": self.simulation._speed_multiplier},
                "regional": regional,
                "zones": zone_scores,
                "conflicts": conflicts,
                "explanations": explanation_map,
                "priorities": priorities,
                "routes": routes,
                "recommendations": recommendations,
                "timeline": self.simulation.events(15),
                "incidents": incidents_all[-30:],
                "alerts": alerts[:25],
                "brief": brief,
                "water_levels": self._water_level_panel(zone_river_map, river_map),
                "precipitation": self._precipitation_panel(weather_map),
                "wind_grid": wind_grid,
                "sources": {"sources": registry.snapshot(), "summary": source_summary},
                "updated_at": updated_at,
                "refresh_interval_seconds": settings.LIVE_REFRESH_SECONDS,
            }
            state["news"] = self.news.build(state, prev_state, self.datalake)
            self._current = state
            self._last_state = state
            try:
                self.history.append(state)
            except Exception:
                pass
            await self._broadcast(state)
            return state

    # ------------------------------------------------------------------
    # Panel builders
    # ------------------------------------------------------------------
    def _water_level_panel(self, zone_river_map, river_map) -> List[Dict[str, Any]]:
        rows = []
        for sid, r in river_map.items():
            rows.append({
                "station_id": sid,
                "station": r.get("river") or sid,
                "river": r.get("river"),
                "state": r.get("state"),
                "basin": r.get("basin"),
                "water_level": r.get("water_level"),
                "warning_level": r.get("warning_level"),
                "danger_level": r.get("danger_level"),
                "status": r.get("status", "NORMAL"),
                "rate_of_rise": r.get("rate_of_rise", 0),
                "discharge": r.get("discharge"),
                "discharge_median": r.get("discharge_median"),
                "flow_ratio": r.get("flow_ratio"),
                "flow_plain": r.get("flow_plain") or "normal flow",
                "flow_status": r.get("flow_status", "NORMAL"),
                "flow_source": r.get("flow_source"),
                "water_level_source": r.get("water_level_source"),
                "flow_forecast": r.get("flow_forecast", []),
                "flood_relevance": _water_flood_relevance(r),
                "timestamp": r.get("timestamp"),
            })
        # Severity band first; within a band the most flood-relevant station on top.
        rows.sort(key=lambda x: (_STATUS_ORDER.get(x["status"], 4), -x["flood_relevance"], -(x.get("flow_ratio") or 0)))
        return rows

    def _precipitation_panel(self, weather_map) -> List[Dict[str, Any]]:
        rows = []
        for zid, w in weather_map.items():
            cur = w.get("rain")
            if cur is None:
                cur = w.get("precipitation")
            cur = float(cur or 0.0)
            fc = w.get("forecast_precipitation") or []
            next6 = sum(x for x in fc[:6] if isinstance(x, (int, float)))
            next24 = sum(x for x in fc[:24] if isinstance(x, (int, float)))
            rows.append({
                "zone_id": zid,
                "name": w.get("zone_name"),
                "state": w.get("state"),
                "basin": w.get("basin"),
                "rain_now_mm": round(cur, 1),
                "category": _rain_category(cur),
                "next_6h_mm": round(next6, 1),
                "next_24h_mm": round(next24, 1),
                "probability_pct": w.get("precipitation_probability"),
                "temperature_c": w.get("temperature_2m"),
                "humidity_pct": w.get("relative_humidity_2m"),
                "wind_kmph": w.get("wind_speed_10m"),
                "wind_deg": w.get("wind_direction_10m"),
                "latitude": w.get("latitude"),
                "longitude": w.get("longitude"),
                "forecast_hours": w.get("forecast_hours", [])[:12],
                "forecast_rain": [round(float(x), 1) if isinstance(x, (int, float)) else 0 for x in fc[:12]],
                "flood_relevance": _precip_flood_relevance(w),
                "data_source": w.get("data_source"),
                "timestamp": w.get("timestamp"),
            })
        # Flood relevance (intensity x flood-prone district) first;
        # total forecast rain breaks ties.
        rows.sort(key=lambda x: (-x["flood_relevance"], -x["next_24h_mm"]))
        return rows

    def _ingest_official_alerts(self, alerts: List[Dict[str, Any]]) -> None:
        for alert in alerts:
            aid = alert.get("id")
            if not aid or aid in self._ingested_alerts:
                continue
            self._ingested_alerts.add(aid)
            zone = self._nearest_zone(alert.get("latitude"), alert.get("longitude"))
            severity = min(float(alert.get("severity", 50.0)) / 100.0, 1.0)
            incident = {
                "id": aid,
                "timestamp": datetime.now().isoformat(),
                "zone_id": zone["id"] if zone else None,
                "location_name": alert.get("title") or "Official flood alert",
                "latitude": alert.get("latitude"),
                "longitude": alert.get("longitude"),
                "state": zone["state"] if zone else "",
                "district": zone.get("district", "") if zone else "",
                "category": "EVACUATION_NEEDED" if alert.get("alert_level") == "Red" else "FLOODED_ROAD",
                "severity": severity,
                "description": "{} — {} ({} alert)".format(
                    alert.get("title"), alert.get("description") or "", alert.get("alert_level") or ""
                ).strip(),
                "source": alert.get("source"),
                "confidence": 0.95,
                "verified": True,
                "nlp_extracted": {"official_alert": True, "alert_level": alert.get("alert_level"), "url": alert.get("url")},
            }
            self.datalake.add_incident(incident)

    def _nearest_zone(self, lat: Optional[float], lon: Optional[float]) -> Optional[Dict[str, Any]]:
        """Nearest priority zone by shortest distance to *any* polygon vertex
        (not just the centroid) — much better accuracy near district borders."""
        if lat is None or lon is None:
            return None
        best, best_dist = None, float("inf")
        for z in ZONES:
            pts = z.get("coordinates") or [z["centroid"]]
            d = min(self._haversine(lat, lon, p[1], p[0]) for p in pts)
            if d < best_dist:
                best_dist, best = d, z
        return best

    def _locate(self, lat: float, lon: float, k: int = 3) -> List[Dict[str, Any]]:
        """Nearest monitored points anywhere in India (priority zones, river
        gauges and ~200 flood-prone towns) with straight-line distances."""
        from .models.india_locator import locate

        return locate(lat, lon, k=k)

    # ------------------------------------------------------------------
    # Incident submission
    # ------------------------------------------------------------------
    async def submit_incident(
        self,
        text: str,
        source: str = "CITIZEN_REPORT",
        explicit_zone: Optional[str] = None,
    ) -> Dict[str, Any]:
        incident = self._parse_incident(text, source=source, explicit_zone=explicit_zone)
        await self.refresh(force=True)
        return incident

    def _parse_incident(
        self,
        text: str,
        source: str = "CITIZEN_REPORT",
        explicit_zone: Optional[str] = None,
    ) -> Dict[str, Any]:
        parsed = extract_incident(text, source=source, explicit_zone=explicit_zone)
        incident = {
            "id": f"INC-{datetime.now().strftime('%H%M%S')}-{abs(hash(text)) % 1000}",
            "timestamp": datetime.now().isoformat(),
            "zone_id": parsed.get("zone_id"),
            "location_name": parsed.get("location_name", "Unknown"),
            "latitude": parsed.get("latitude"),
            "longitude": parsed.get("longitude"),
            "state": parsed.get("state", ""),
            "district": parsed.get("district", ""),
            "category": parsed.get("category"),
            "severity": parsed.get("severity"),
            "description": text.strip(),
            "source": source,
            "confidence": parsed.get("confidence"),
            "verified": False,
            "nlp_extracted": parsed.get("nlp_extracted", {}),
        }
        self.datalake.add_incident(incident)
        self.datalake.log_event({
            "timestamp": incident["timestamp"],
            "type": "INCIDENT",
            "message": f"NLP ingested: {incident['location_name']} ({incident['category']}, severity {incident['severity']:.1f})",
        })
        return incident

    # ------------------------------------------------------------------
    # Simulation controls
    # ------------------------------------------------------------------
    async def simulation_step(self, action: str = "next") -> Dict[str, Any]:
        if action == "play":
            self.simulation.play()
        elif action == "pause":
            self.simulation.pause()
        elif action == "toggle":
            self.simulation.toggle()
        elif action == "surge":
            self.simulation.trigger_surge()
        elif action == "reset":
            self.simulation.reset()
            self.river_service.reset()
            self.sar.reset()
        else:
            self.simulation.next_step()
        await self.refresh(force=True)
        return self._current

    # ------------------------------------------------------------------
    # Routing evaluate
    # ------------------------------------------------------------------
    def evaluate_route(
        self,
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
        origin_name: str = "Origin",
        dest_name: str = "Destination",
    ) -> Dict[str, Any]:
        zone_scores = self._current.get("zones", {})
        incidents = self.datalake.get_incidents()
        return compute_route_risk(
            origin_lat, origin_lon, dest_lat, dest_lon,
            zone_scores, incidents,
            origin_name=origin_name,
            dest_name=dest_name,
        )

    # ------------------------------------------------------------------
    # Emergency / evacuation
    # ------------------------------------------------------------------
    def emergency_contacts(self) -> Dict[str, Any]:
        payload = contacts_payload()
        payload["generated_at"] = datetime.now().isoformat()
        return payload

    def evacuation_info(self) -> Dict[str, Any]:
        state = self._current
        shelters = self.datalake.list("infrastructure").get("shelters", [])
        zones = state.get("zones", {})
        at_risk = []
        for zid, z in zones.items():
            if (z.get("overall_score") or 0) >= 40:
                at_risk.append({
                    "zone_id": zid,
                    "name": z.get("district") or z.get("zone_name"),
                    "state": z.get("state"),
                    "level": z.get("severity_level"),
                    "score": z.get("overall_score"),
                    "population": ZONE_INDEX.get(zid, {}).get("population", 0),
                })
        at_risk.sort(key=lambda z: z["score"], reverse=True)
        return {
            "at_risk_zones": at_risk,
            "shelters": shelters,
            "shelter_count": len(shelters),
            "rescue_bases": self.datalake.list("infrastructure").get("rescue_bases", []),
            "routes": state.get("routes", []),
            "guidance": contacts_payload()["evacuation"],
            "generated_at": datetime.now().isoformat(),
        }

    # ------------------------------------------------------------------
    # WebSocket broadcast
    # ------------------------------------------------------------------
    async def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=20)
        self._subscribers.append(q)
        if self._current:
            await q.put(self._current)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        if q in self._subscribers:
            self._subscribers.remove(q)

    async def _broadcast(self, state: Dict[str, Any]):
        dead = []
        for q in self._subscribers:
            try:
                q.put_nowait(state)
            except asyncio.QueueFull:
                try:
                    q.get_nowait()
                    q.put_nowait(state)
                except Exception:
                    pass
            except Exception:
                dead.append(q)
        for q in dead:
            self._subscribers.remove(q)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _haversine(lat1, lon1, lat2, lon2):
        import math
        R = 6371.0
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dp = math.radians(lat2 - lat1)
        dl = math.radians(lon2 - lon1)
        h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return 2 * R * math.asin(math.sqrt(h))

    def _map_rivers_to_zones(self, river_map: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        from .models.india_data import STATION_INDEX
        out: Dict[str, Dict[str, Any]] = {}
        for z in ZONES:
            zid = z["id"]
            lon, lat = z["centroid"]
            best = None
            best_dist = float("inf")
            for r in river_map.values():
                sid = r.get("station_id")
                reg = STATION_INDEX.get(sid)
                dist = self._haversine(lat, lon, reg[5], reg[6]) if reg else (0 if r.get("basin") == z.get("basin") else 1e9)
                if dist < best_dist:
                    best_dist, best = dist, r
            if best is not None:
                out[zid] = best
        return out


orchestrator = FDROrchestrator()


async def background_live_data(interval_seconds: float = 90.0):
    """Keep the dashboard genuinely live: advance the scenario if playing and
    always re-pull weather, river flow and official alerts."""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            if orchestrator.simulation.running:
                orchestrator.simulation.next_step()
            await orchestrator.refresh(force=True)
        except Exception:
            pass
