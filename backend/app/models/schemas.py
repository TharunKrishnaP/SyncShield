from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class SeverityLevel(str, Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"
    CRITICAL = "CRITICAL"


class FloodStatus(str, Enum):
    NORMAL = "NORMAL"
    ABOVE_NORMAL = "ABOVE_NORMAL"
    SEVERE = "SEVERE"
    EXTREME = "EXTREME"


class DataSource(str, Enum):
    OPEN_METEO = "OPEN_METEO"
    IMD = "IMD"
    CWC_TELEMETRY = "CWC_TELEMETRY"
    CWC_MANUAL = "CWC_MANUAL"
    SENTINEL1_SAR = "SENTINEL1_SAR"
    BHUVAN = "BHUVAN"
    BHOONIDHI = "BHOONIDHI"
    NDEM = "NDEM"
    INDIA_WRIS = "INDIA_WRIS"
    CITIZEN_REPORT = "CITIZEN_REPORT"
    FIELD_REPORT = "FIELD_REPORT"
    SOCIAL_MEDIA = "SOCIAL_MEDIA"
    SIMULATION = "SIMULATION"


class IncidentCategory(str, Enum):
    FLOODED_ROAD = "FLOODED_ROAD"
    TRAPPED_RESIDENTS = "TRAPPED_RESIDENTS"
    POWER_OUTAGE = "POWER_OUTAGE"
    HOSPITAL_ACCESS_BLOCKED = "HOSPITAL_ACCESS_BLOCKED"
    BRIDGE_COLLAPSE = "BRIDGE_COLLAPSE"
    LANDSLIDE = "LANDSLIDE"
    EVACUATION_NEEDED = "EVACUATION_NEEDED"
    RELIEF_SHELTER_FULL = "RELIEF_SHELTER_FULL"
    WATER_CONTAMINATION = "WATER_CONTAMINATION"
    COMMUNICATION_DOWN = "COMMUNICATION_DOWN"
    OTHER = "OTHER"


class PriorityLevel(int, Enum):
    CRITICAL = 1
    HIGH = 2
    MONITOR = 3
    LOW = 4


class Zone(BaseModel):
    id: str
    name: str
    basin: str
    state: str
    district: str
    coordinates: List[List[float]]  # GeoJSON polygon coordinates
    population: int
    vulnerable_population: int = 0
    area_km2: float
    hospitals: List[Dict[str, Any]] = []
    shelters: List[Dict[str, Any]] = []
    rescue_bases: List[Dict[str, Any]] = []


class RiverStation(BaseModel):
    id: str
    name: str
    river: str
    basin: str
    state: str
    district: str
    latitude: float
    longitude: float
    warning_level: float  # WL in meters
    danger_level: float   # DL in meters
    highest_flood_level: float  # HFL in meters
    zero_gauge_level: float  # RL of gauge zero in MSL
    station_type: str  # "Level Forecast", "Inflow Forecast", "Monitoring"
    data_source: DataSource = DataSource.CWC_TELEMETRY


class RiverReading(BaseModel):
    station_id: str
    timestamp: datetime
    water_level: float  # in meters
    discharge: Optional[float] = None  # in m3/s
    rainfall: Optional[float] = None  # in mm
    data_source: DataSource = DataSource.CWC_TELEMETRY
    quality_flag: str = "GOOD"


class WeatherData(BaseModel):
    location_id: str
    latitude: float
    longitude: float
    timestamp: datetime
    temperature_2m: float
    precipitation: float  # mm
    precipitation_probability: float
    rain: float
    showers: float
    snowfall: float
    wind_speed_10m: float
    wind_direction_10m: float
    relative_humidity_2m: float
    pressure_msl: float
    cloud_cover: float
    data_source: DataSource = DataSource.OPEN_METEO


class SatelliteFloodExtent(BaseModel):
    id: str
    timestamp: datetime
    basin: str
    state: str
    district: str
    flood_polygons: List[List[List[float]]]  # GeoJSON MultiPolygon
    flood_area_km2: float
    water_depth_avg: Optional[float] = None  # meters
    confidence: float = 0.8
    satellite: str = "Sentinel-1"
    sensor: str = "SAR"
    resolution_m: float = 10.0
    data_source: DataSource = DataSource.SENTINEL1_SAR
    processing_level: str = "L2"


class IncidentReport(BaseModel):
    id: str
    timestamp: datetime
    location_name: str
    latitude: float
    longitude: float
    state: str
    district: str
    category: IncidentCategory
    severity: float  # 0.0 - 1.0
    description: str
    source: DataSource = DataSource.CITIZEN_REPORT
    confidence: float = 0.7
    verified: bool = False
    nlp_extracted: Optional[Dict[str, Any]] = None


class SituationScore(BaseModel):
    zone_id: str
    zone_name: str
    basin: str
    state: str
    district: str
    overall_score: float  # 0-100
    severity_level: SeverityLevel
    satellite_score: float
    weather_score: float
    river_score: float
    incident_score: float
    population_score: float
    trend: float  # rate of change per hour
    deteriorating: bool
    last_updated: datetime
    evidence_breakdown: Dict[str, Any]


class RescuePriority(BaseModel):
    zone_id: str
    zone_name: str
    basin: str
    state: str
    district: str
    priority: PriorityLevel
    priority_score: float
    severity: float
    population_exposure: int
    vulnerable_population: int
    accessibility_index: float  # 0-1, lower = less accessible
    rate_of_change: float
    recommended_actions: List[str]
    coordinates: List[List[float]]


class RouteRisk(BaseModel):
    origin: Dict[str, Any]  # {name, lat, lon, type}
    destination: Dict[str, Any]
    direct_route: Dict[str, Any]  # {distance_km, risk_score, flood_exposure, blocked_segments, status}
    alternative_route: Dict[str, Any]
    recommendation: str


class ConflictDetection(BaseModel):
    id: str
    zone_id: str
    timestamp: datetime
    conflict_type: str
    description: str
    modality_a: str
    modality_b: str
    confidence_penalty: float
    diagnosis: str
    resolved: bool = False


class AIExplanation(BaseModel):
    zone_id: str
    primary_reason: str
    evidence_points: List[Dict[str, Any]]  # [{factor, contribution_pct, description}]
    natural_language_summary: str


class DecisionRecommendation(BaseModel):
    id: str
    timestamp: datetime
    priority: int
    category: str
    title: str
    description: str
    affected_zones: List[str]
    responsible_agency: str
    confidence: float
    estimated_resources: Dict[str, Any]


class SimulationState(BaseModel):
    running: bool = False
    current_step: int = 0
    total_steps: int = 10
    speed_multiplier: float = 10.0
    scenario_name: str = "monsoon_surge_2024"
    start_time: Optional[datetime] = None
    events_triggered: List[str] = []