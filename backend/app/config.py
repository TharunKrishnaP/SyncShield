import os
from pydantic_settings import BaseSettings
from typing import List, Optional
from functools import lru_cache


class Settings(BaseSettings):
    # App
    APP_NAME: str = "AI Multimodal Flood Disaster Response DataLake (FDR) - India"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    ENVIRONMENT: str = "development"

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Data Lake
    DATA_LAKE_PATH: str = os.path.join(os.path.dirname(__file__), "..", "..", "data_lake")
    DATA_LAKE_PERSIST_INTERVAL: int = 60  # seconds

    # Live refresh cadence (dashboard push interval in seconds)
    LIVE_REFRESH_SECONDS: int = 60

    # History lake (append-only time series, SQLite)
    HISTORY_DB_PATH: str = os.path.join(os.path.dirname(__file__), "..", "..", "data", "history.db")
    HISTORY_RETENTION_HOURS: int = 24 * 7  # keep one week of readings / risk scores

    # Citizen self-service
    CITIZEN_MEDIA_DIR: str = os.path.join(os.path.dirname(__file__), "..", "..", "data_lake", "citizen_media")

    # External APIs
    OPEN_METEO_BASE_URL: str = "https://api.open-meteo.com/v1"
    IMD_API_BASE_URL: str = "https://api.imd.gov.in/api/v1"
    NWDP_API_BASE_URL: str = "https://nwdp.nwic.gov.in/api"
    BHUVAN_API_BASE_URL: str = "https://bhuvan-app1.nrsc.gov.in"
    BHOONIDHI_API_BASE_URL: str = "https://bhoonidhi-api.nrsc.gov.in"
    NDEM_API_BASE_URL: str = "https://ndem.nrsc.gov.in"
    INDIA_WRIS_BASE_URL: str = "https://indiawris.gov.in"
    CWC_FFS_BASE_URL: str = "https://ffs.india-water.gov.in"
    SACHET_API_BASE_URL: str = "https://sachet.ndma.gov.in"

    # API Keys (optional, for authenticated APIs)
    IMD_API_KEY: Optional[str] = None
    NWDP_API_KEY: Optional[str] = None
    BHOONIDHI_API_KEY: Optional[str] = None
    NDEM_API_KEY: Optional[str] = None
    SACHET_API_KEY: Optional[str] = None

    # India Geographic Bounds
    INDIA_BBOX: List[float] = [68.1, 6.5, 97.4, 35.5]  # [min_lon, min_lat, max_lon, max_lat]

    # Major River Basins in India
    MAJOR_BASINS: List[dict] = [
        {"name": "Ganga", "code": "GANGA", "states": ["Uttarakhand", "Uttar Pradesh", "Bihar", "Jharkhand", "West Bengal"]},
        {"name": "Brahmaputra", "code": "BRAHMAPUTRA", "states": ["Arunachal Pradesh", "Assam", "West Bengal"]},
        {"name": "Indus", "code": "INDUS", "states": ["Jammu & Kashmir", "Ladakh", "Himachal Pradesh", "Punjab"]},
        {"name": "Godavari", "code": "GODAVARI", "states": ["Maharashtra", "Telangana", "Andhra Pradesh", "Chhattisgarh", "Odisha"]},
        {"name": "Krishna", "code": "KRISHNA", "states": ["Maharashtra", "Karnataka", "Telangana", "Andhra Pradesh"]},
        {"name": "Cauvery", "code": "CAUVERY", "states": ["Karnataka", "Tamil Nadu", "Kerala", "Puducherry"]},
        {"name": "Mahanadi", "code": "MAHANADI", "states": ["Chhattisgarh", "Odisha"]},
        {"name": "Narmada", "code": "NARMADA", "states": ["Madhya Pradesh", "Maharashtra", "Gujarat"]},
        {"name": "Tapi", "code": "TAPI", "states": ["Madhya Pradesh", "Maharashtra", "Gujarat"]},
        {"name": "Sabarmati", "code": "SABARMATI", "states": ["Rajasthan", "Gujarat"]},
        {"name": "Mahanadi", "code": "MAHANADI", "states": ["Chhattisgarh", "Odisha"]},
        {"name": "Subarnarekha", "code": "SUBARNAREKHA", "states": ["Jharkhand", "Odisha", "West Bengal"]},
        {"name": "Brahmani-Baitarani", "code": "BRAHMANI_BAITARANI", "states": ["Odisha", "Jharkhand"]},
        {"name": "Pennar", "code": "PENNAR", "states": ["Karnataka", "Andhra Pradesh"]},
        {"name": "Periyar", "code": "PERIYAR", "states": ["Kerala"]},
    ]

    # Simulation
    # Off by default: the dashboard runs strictly on real-time sources. Flip
    # SIMULATION_ENABLED=True (or set the env var) only for guided demos that
    # knowingly want synthetic scenario data.
    SIMULATION_ENABLED: bool = False
    SIMULATION_SPEED_MULTIPLIER: float = 10.0  # 10x speed for demo

    # AI Engine Weights
    WEIGHT_SATELLITE: float = 0.35
    WEIGHT_WEATHER: float = 0.20
    WEIGHT_RIVER: float = 0.20
    WEIGHT_INCIDENTS: float = 0.15
    WEIGHT_POPULATION: float = 0.10

    # Severity Thresholds
    SEVERITY_LOW: int = 20
    SEVERITY_MODERATE: int = 40
    SEVERITY_HIGH: int = 60
    SEVERITY_VERY_HIGH: int = 80
    SEVERITY_CRITICAL: int = 100

    # ---- Trained ML layer (Phase 1) ----
    # Trained artifacts live under ml/artifacts/ (repo root).
    ML_ARTIFACTS_DIR: str = os.path.join(os.path.dirname(__file__), "..", "..", "ml", "artifacts")
    ML_TEXT_DIR: str = os.path.join(ML_ARTIFACTS_DIR, "text_classifier")
    ML_SAR_DIR: str = os.path.join(ML_ARTIFACTS_DIR, "sar_unet")
    ML_SAR_SCENES_DIR: str = os.path.join(
        os.path.dirname(__file__), "..", "..", "ml", "data", "sar_scenes"
    )
    # Minimum ML probability to override the rule engine on incident category.
    ML_TEXT_CONFIDENCE: float = 0.55

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()