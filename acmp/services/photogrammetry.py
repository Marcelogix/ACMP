"""Flat-ground camera-footprint calculations for coverage missions."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass


# Optical-format names are not literal inch measurements.  These common
# industry designations are mapped to their useful active-diagonal estimates.
OPTICAL_FORMAT_DIAGONALS_MM = {
    "1/2.3": 7.7,
    "1/1.7": 9.5,
    "1/1.3": 9.6,
    "1": 16.0,
    "4/3": 21.64,
    "aps-c": 28.2,
    "full frame": 43.27,
}


@dataclass(frozen=True)
class CoverageGeometry:
    sensor_diagonal_mm: float
    footprint_cross_m: float
    footprint_along_m: float
    photo_distance_m: float
    path_spacing_m: float


def sensor_diagonal_mm(value: str) -> float:
    """Parse e.g. ``1/1.3`` optical format or a direct ``9.6 mm`` diagonal."""
    normalized = value.strip().lower().replace(',', '.').replace('″', '').replace('"', '').replace(' type', '')
    if normalized in OPTICAL_FORMAT_DIAGONALS_MM:
        return OPTICAL_FORMAT_DIAGONALS_MM[normalized]
    match = re.fullmatch(r"\s*(\d+(?:[.,]\d+)?)\s*mm\s*", normalized)
    if match:
        diagonal = float(match.group(1).replace(',', '.'))
        if diagonal > 0:
            return diagonal
    raise ValueError("Sensorformat z. B. als 1/1.3, 4/3, APS-C oder direkte Diagonale wie 9.6 mm eingeben.")


def coverage_geometry(
    altitude_m: float,
    gimbal_pitch_deg: float,
    focal_length_mm: float,
    sensor_format: str,
    image_ratio: str,
    forward_overlap_pct: float,
    side_overlap_pct: float,
) -> CoverageGeometry:
    """Calculate a flat-ground footprint, aligned with the flight direction.

    The gimbal is assumed to point along the flight direction.  At oblique
    angles this projects all four image-corner rays on to a level ground plane.
    """
    diagonal = sensor_diagonal_mm(sensor_format)
    try:
        ratio_x, ratio_y = (float(part) for part in image_ratio.split(':', 1))
    except (TypeError, ValueError):
        raise ValueError("Bildformat muss beispielsweise 4:3 oder 16:9 sein.") from None
    if min(altitude_m, focal_length_mm, ratio_x, ratio_y) <= 0:
        raise ValueError("Flughöhe, Brennweite und Bildformat müssen größer als null sein.")
    sensor_width = diagonal * ratio_x / math.hypot(ratio_x, ratio_y)
    sensor_height = diagonal * ratio_y / math.hypot(ratio_x, ratio_y)
    # DJI pitch -90° is nadir; 0° is horizontal.
    tilt = math.radians(90 + gimbal_pitch_deg)
    forward = (0.0, math.sin(tilt), -math.cos(tilt))
    right = (1.0, 0.0, 0.0)
    up = (0.0, math.cos(tilt), math.sin(tilt))
    corners = []
    for horizontal in (-sensor_width / 2 / focal_length_mm, sensor_width / 2 / focal_length_mm):
        for vertical in (-sensor_height / 2 / focal_length_mm, sensor_height / 2 / focal_length_mm):
            ray = (forward[0] + horizontal * right[0] + vertical * up[0],
                   forward[1] + horizontal * right[1] + vertical * up[1],
                   forward[2] + horizontal * right[2] + vertical * up[2])
            if ray[2] >= -1e-8:
                raise ValueError("Kamerawinkel zeigt bis an oder über den Horizont; Footprint ist nicht berechenbar.")
            scale = altitude_m / -ray[2]
            corners.append((ray[0] * scale, ray[1] * scale))
    cross = max(point[0] for point in corners) - min(point[0] for point in corners)
    along = max(point[1] for point in corners) - min(point[1] for point in corners)
    return CoverageGeometry(
        diagonal, cross, along,
        along * (1 - forward_overlap_pct / 100),
        cross * (1 - side_overlap_pct / 100),
    )
