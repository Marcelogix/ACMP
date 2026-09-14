"""Drone capability profiles and capture-strategy selection for mapping missions.

The planner keeps the photogrammetric intent in metres.  A consumer profile
turns that intent into a controller interval plus a matching flight speed,
whereas an enterprise profile can retain a native WPML distance trigger.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DroneCapabilities:
    category: str
    supports_wpml_distance_trigger: bool
    supports_wpml_time_trigger: bool
    supports_wpml_gimbal_pitch: bool
    requires_manual_interval_capture: bool
    supported_photo_intervals: tuple[float, ...]
    min_mapping_speed: float
    max_mapping_speed: float


CONSUMER_CAPABILITIES = DroneCapabilities(
    category="consumer",
    supports_wpml_distance_trigger=False,
    supports_wpml_time_trigger=False,
    supports_wpml_gimbal_pitch=True,
    requires_manual_interval_capture=True,
    # Conservative, commonly available DJI Fly interval choices.  Model
    # profiles can replace this tuple without changing UI or export code.
    supported_photo_intervals=(2.0, 3.0, 5.0, 7.0, 10.0),
    min_mapping_speed=0.5,
    max_mapping_speed=15.0,
)

ENTERPRISE_CAPABILITIES = DroneCapabilities(
    category="prosumer_enterprise",
    supports_wpml_distance_trigger=True,
    supports_wpml_time_trigger=False,
    supports_wpml_gimbal_pitch=True,
    requires_manual_interval_capture=False,
    supported_photo_intervals=(),
    min_mapping_speed=0.5,
    max_mapping_speed=15.0,
)


def capabilities_for(category: str) -> DroneCapabilities:
    """Return a profile without scattering model/category checks in the UI."""
    return ENTERPRISE_CAPABILITIES if category == "prosumer_enterprise" else CONSUMER_CAPABILITIES


@dataclass(frozen=True)
class CapturePlan:
    mode: str  # ``manual_interval`` or ``wpml_distance``
    requested_distance_m: float
    flight_speed_mps: float
    interval_s: float | None = None

    @property
    def actual_distance_m(self) -> float:
        return self.flight_speed_mps * self.interval_s if self.interval_s else self.requested_distance_m


def choose_capture_plan(
    requested_distance_m: float,
    preferred_speed_mps: float,
    capabilities: DroneCapabilities,
    minimum_interval_s: float = 0.0,
) -> CapturePlan:
    """Choose an allowed interval whose mapping speed matches the preference.

    ``minimum_interval_s`` is a hard camera constraint.  Among the remaining
    controller intervals, matching the requested mapping speed takes priority;
    the resulting photo spacing is the tie-breaker.  This lets a 2 s-capable
    camera use 2 s / 6.3 m/s instead of an unnecessarily slower 3 s / 4.2 m/s
    for a roughly 12.6 m image spacing.  If a short interval would be too fast,
    a longer interval naturally lowers the flight speed.
    """
    distance = max(0.01, float(requested_distance_m))
    preferred = min(max(float(preferred_speed_mps), capabilities.min_mapping_speed), capabilities.max_mapping_speed)
    if not capabilities.requires_manual_interval_capture:
        return CapturePlan("wpml_distance", distance, preferred)

    candidates = []
    for interval in capabilities.supported_photo_intervals:
        if interval < max(0.0, float(minimum_interval_s)):
            continue
        required_speed = distance / interval
        clamped_speed = min(max(required_speed, capabilities.min_mapping_speed), capabilities.max_mapping_speed)
        # WPML serialises waypoint speed with one decimal; choose and report
        # the same executable value, not a misleading higher precision value.
        clamped_speed = round(clamped_speed, 1)
        feasible = capabilities.min_mapping_speed <= required_speed <= capabilities.max_mapping_speed
        # The speed is the primary operator preference once the camera's
        # minimum interval is honoured. Photo spacing breaks speed ties.
        actual_distance = clamped_speed * interval
        candidates.append((not feasible, abs(clamped_speed - preferred), abs(actual_distance - distance), interval, clamped_speed))
    if not candidates:
        raise ValueError("Für die gewählte minimale Intervalldauer ist kein unterstütztes Fotointervall hinterlegt.")
    _, _, _, interval, speed = min(candidates)
    return CapturePlan("manual_interval", distance, speed, interval)
