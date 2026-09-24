"""Scenario player for the monsoon-surge demonstration.

Pre-built timeline of event steps (10:00 → 11:30), each injecting
weather/river/satellite changes and log events so the dashboard visibly
deteriorates across a session.
"""
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class ScenarioStep:
    step: int
    label: str
    time_label: str
    surge_factor: float
    description: str
    event_type: str = "INFO"


SCENARIO = [
    ScenarioStep(0, "Baseline", "10:00 AM", 1.0, "Monsoon onset. Normal river levels across flood-prone basins."),
    ScenarioStep(1, "Rain onset", "10:15 AM", 1.2, "Heavy rainfall reported over NE, Bihar, and East coast; pre-monsoon signal."),
    ScenarioStep(2, "River rise", "10:30 AM", 1.5, "CWC gauges rise above warning level at Guwahati, Patna, Farakka."),
    ScenarioStep(3, "Warning level", "10:45 AM", 1.8, "Multiple gauges reach warning level; alert triggered for 6 zones."),
    ScenarioStep(4, "Satellite overpass", "10:52 AM", 2.0, "Sentinel-1 overpass captures expanded inundation in Brahmaputra valley."),
    ScenarioStep(5, "Above normal", "11:00 AM", 2.2, "River levels cross into danger zone across 4 states; shelters activated."),
    ScenarioStep(6, "Severe flood", "11:10 AM", 2.5, "SAR extents expand; evacuation advisories issued for 5 districts."),
    ScenarioStep(7, "Road cutoff", "11:15 AM", 2.7, "NH-27 (Guwahati), NH-31 (Patna) and NH-544 (Aluva) underpasses submerged."),
    ScenarioStep(8, "Extreme flood", "11:20 AM", 3.0, "Critical: Guwahati, Patna, Cuttack, Aluva scores reach VERY HIGH / CRITICAL."),
    ScenarioStep(9, "Peak crisis", "11:25 AM", 3.2, "Peak inundation. Priority-1 rescue zones set. NDRF recon deployed."),
    ScenarioStep(10, "Aftermath", "11:30 AM", 3.0, "Receding current. Damage assessment phase begins."),
]


class SimulationEngine:
    def __init__(self):
        self._step: int = 0
        self._running: bool = False
        self._speed_multiplier: float = 10.0
        self._scenario = SCENARIO
        self._events: List[Dict[str, Any]] = []

    # ---- state ----
    @property
    def step(self) -> int:
        return self._step

    @step.setter
    def step(self, value: int):
        self._step = max(0, min(value, len(self._scenario) - 1))

    @property
    def running(self) -> bool:
        return self._running

    @property
    def current_step_info(self) -> Dict[str, Any]:
        s = self._scenario[self._step]
        return {
            "step": self._step,
            "label": s.label,
            "time_label": s.time_label,
            "surge_factor": s.surge_factor,
            "description": s.description,
            "total_steps": len(self._scenario),
        }

    # ---- controls ----
    def play(self):
        self._running = True
        self._log("PLAY", "Simulation playback started.")

    def pause(self):
        self._running = False
        self._log("PAUSE", "Simulation playback paused.")

    def toggle(self):
        self._running = not self._running
        return self._running

    def next_step(self) -> Dict[str, Any]:
        if self._step < len(self._scenario) - 1:
            self._step += 1
            s = self._scenario[self._step]
            self._log(s.event_type, s.description)
        return self.current_step_info

    def previous_step(self) -> Dict[str, Any]:
        self._step = max(0, self._step - 1)
        return self.current_step_info

    def reset(self):
        self._step = 0
        self._running = False
        self._events = []
        self._log("RESET", "Simulation reset to baseline.")

    def trigger_surge(self) -> Dict[str, Any]:
        if self._step < len(self._scenario) - 1:
            self._step = min(len(self._scenario) - 1, self._step + 3)
        s = self._scenario[self._step]
        self._log("SURGE", f"Manual surge event: {s.label} — {s.description}")
        return self.current_step_info

    def advance_auto(self) -> Optional[Dict[str, Any]]:
        """Auto-advance if playing; used by the background ticker."""
        if not self._running:
            return None
        return self.next_step()

    def _log(self, event_type: str, message: str):
        self._events.append({
            "timestamp": datetime.now().isoformat(),
            "type": event_type,
            "message": message,
        })
        if len(self._events) > 200:
            self._events = self._events[-200:]

    def events(self, limit: int = 20) -> List[Dict[str, Any]]:
        return list(reversed(self._events[-limit:]))

    def surge_factor(self) -> float:
        return self._scenario[self._step].surge_factor

    def time_label(self) -> str:
        return self._scenario[self._step].time_label