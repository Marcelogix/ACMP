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
    requires_manual_interval_capture: bool
    supported_photo_intervals: tuple[float, ...]
    min_mapping_speed: float
    max_mapping_speed: float


CONSUMER_CAPABILITIES = DroneCapabilities(
    category="consumer",
    supports_wpml_distance_trigger=False,
    supports_wpml_time_trigger=False,
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
) -> CapturePlan:
    """Choose the feasible interval/speed pair closest to mapping speed.

    Feasible pairs are always preferred.  If none is feasible (normally only
    possible for an unusually small/large requested spacing), choose the pair
    whose required speed is closest to the allowed range and clamp it.  This
    makes the resulting spacing explicit rather than silently choosing an
    unsuitable interval.
    """
    distance = max(0.01, float(requested_distance_m))
    preferred = min(max(float(preferred_speed_mps), capabilities.min_mapping_speed), capabilities.max_mapping_speed)
    if not capabilities.requires_manual_interval_capture:
        return CapturePlan("wpml_distance", distance, preferred)

    candidates = []
    for interval in capabilities.supported_photo_intervals:
        required_speed = distance / interval
        clamped_speed = min(max(required_speed, capabilities.min_mapping_speed), capabilities.max_mapping_speed)
        # WPML serialises waypoint speed with one decimal; choose and report
        # the same executable value, not a misleading higher precision value.
        clamped_speed = round(clamped_speed, 1)
        feasible = capabilities.min_mapping_speed <= required_speed <= capabilities.max_mapping_speed
        # Prioritise exact requested spacing, then the speed closest to the
        # user's preferred mapping speed.  Infeasible choices expose their
        # resulting spacing and are only used as a fallback.
        actual_distance = clamped_speed * interval
        candidates.append((not feasible, abs(actual_distance - distance), abs(clamped_speed - preferred), interval, clamped_speed))
    if not candidates:
        raise ValueError("Für dieses Drohnenprofil sind keine Fotointervalle hinterlegt.")
    _, _, _, interval, speed = min(candidates)
    return CapturePlan("manual_interval", distance, speed, interval)
