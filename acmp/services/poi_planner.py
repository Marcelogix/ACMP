"""Independent route planner for point-of-interest capture missions.

The terrain lawnmower planner deliberately does not appear here.  POI routes
are generated as height bands around an object or parallel facade passes.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union


class POIPlanningError(ValueError):
    """The requested POI capture cannot be flown safely with its constraints."""


@dataclass(frozen=True)
class POIWaypoint:
    lat: float
    lon: float
    altitude_m: float
    gimbal_pitch_deg: float
    yaw_deg: float
    level: int
    kind: str  # capture or transition


@dataclass(frozen=True)
class POIRoutePlan:
    levels: tuple[tuple[POIWaypoint, ...], ...]
    vertical_spacing_m: float

    @property
    def waypoints(self) -> tuple[POIWaypoint, ...]:
        return tuple(waypoint for level in self.levels for waypoint in level)


def _local_geometry(points, origin_lat, origin_lon):
    lat_scale = 111_132.92
    lon_scale = 111_319.49 * math.cos(math.radians(origin_lat))
    return Polygon([((lon - origin_lon) * lon_scale, (lat - origin_lat) * lat_scale) for lat, lon in points])


def _to_geographic(x, y, origin_lat, origin_lon):
    return origin_lat + y / 111_132.92, origin_lon + x / (111_319.49 * math.cos(math.radians(origin_lat)))


def _vertical_footprint_m(distance_m, sensor_diagonal_mm, focal_length_mm, image_ratio):
    try:
        ratio_x, ratio_y = (float(value) for value in image_ratio.split(":", 1))
    except (ValueError, TypeError):
        raise POIPlanningError("Bildformat muss beispielsweise 4:3 oder 16:9 sein.") from None
    sensor_height = sensor_diagonal_mm * ratio_y / math.hypot(ratio_x, ratio_y)
    vertical_fov = 2 * math.atan(sensor_height / (2 * focal_length_mm))
    return 2 * distance_m * math.tan(vertical_fov / 2)


def _height_bands(object_height_m, min_altitude_m, max_altitude_m, distance_m, vertical_overlap_pct, sensor_diagonal_mm, focal_length_mm, image_ratio):
    if not 0 < object_height_m or not min_altitude_m <= max_altitude_m or distance_m <= 0:
        raise POIPlanningError("Objekthöhe, Abstand sowie Mindest- und Maximalflughöhe müssen gültig sein.")
    footprint = _vertical_footprint_m(distance_m, sensor_diagonal_mm, focal_length_mm, image_ratio)
    spacing = footprint * (1 - vertical_overlap_pct / 100)
    if spacing <= 0.02:
        raise POIPlanningError("Die vertikale Überlappung ergibt keinen sinnvollen Höhenabstand.")
    targets = []
    target = min(footprint / 2, object_height_m)
    while target <= object_height_m + 0.01:
        altitude = max(min_altitude_m, target)
        if altitude > max_altitude_m + 1e-6:
            break
        targets.append((min(target, object_height_m), altitude))
        if target >= object_height_m:
            break
        target = min(object_height_m, target + spacing)
    if not targets:
        raise POIPlanningError("Die Maximalflughöhe erlaubt keine POI-Aufnahme.")
    return targets, spacing


def _ring_coordinates(geometry):
    if geometry.is_empty:
        return []
    if geometry.geom_type == "MultiPolygon":
        geometry = max(geometry.geoms, key=lambda item: item.area)
    if geometry.geom_type != "Polygon":
        return []
    return list(geometry.exterior.coords)[:-1]


def _is_nearly_circular(polygon):
    center = polygon.centroid
    radii = [math.hypot(x - center.x, y - center.y) for x, y in polygon.exterior.coords[:-1]]
    if not radii:
        return False, center, 0.0
    radius = sum(radii) / len(radii)
    return radius > 0 and max(abs(value - radius) for value in radii) / radius < 0.035, center, radius


def _safe_circle_coordinates(center, object_radius, distance_m, detail_pct):
    """Use few control points but keep every connecting chord outside the offset."""
    target_radius = object_radius + distance_m
    # The chord itself remains at least at ``target_radius``. Higher detail
    # means smaller permitted outward correction and consequently more points.
    detail = min(100.0, max(0.0, float(detail_pct))) / 100.0
    max_outward_deviation = 4.0 - 3.5 * detail  # 4 m (sparse) … 0.5 m (fine)
    count = max(8, min(48, math.ceil(math.pi / math.acos(1 / (1 + max_outward_deviation / target_radius)))))
    waypoint_radius = target_radius / math.cos(math.pi / count)
    return [
        (center.x + waypoint_radius * math.cos(2 * math.pi * index / count),
         center.y + waypoint_radius * math.sin(2 * math.pi * index / count))
        for index in range(count)
    ]


def _inside_allowed(line, allowed, blocked):
    return allowed.covers(line) and not any(line.intersects(zone) for zone in blocked)


def plan_poi_route(
    poi_area, flight_areas, no_fly_zones, *, capture_type, facade_bearing_deg,
    orbit_clockwise, object_height_m, distance_m, min_altitude_m, max_altitude_m,
    vertical_overlap_pct, sensor_diagonal_mm, focal_length_mm, image_ratio,
    control_point_detail_pct=70, orbit_geometry="Automatisch",
):
    """Create a 2.5D POI plan and reject geometry that leaves the flight area.

    No-fly zones are intentionally never crossed.  Automatic detours are not
    invented here because they would break the constant-distance coverage
    requirement; the caller receives a precise unsafe-route error instead.
    """
    if len(poi_area) < 3:
        raise POIPlanningError("Bitte zeichne einen Point of Interest mit mindestens drei Punkten.")
    if not flight_areas:
        raise POIPlanningError("Für eine POI-Route wird mindestens ein Flugbereich benötigt.")
    origin_lat = sum(point[0] for point in poi_area) / len(poi_area)
    origin_lon = sum(point[1] for point in poi_area) / len(poi_area)
    poi = _local_geometry(poi_area, origin_lat, origin_lon)
    if not poi.is_valid or poi.area <= 0:
        raise POIPlanningError("Die POI-Geometrie ist ungültig.")
    allowed = unary_union([_local_geometry(area, origin_lat, origin_lon) for area in flight_areas])
    blocked = [_local_geometry(area, origin_lat, origin_lon) for area in no_fly_zones]
    bands, spacing = _height_bands(
        object_height_m, min_altitude_m, max_altitude_m, distance_m, vertical_overlap_pct,
        sensor_diagonal_mm, focal_length_mm, image_ratio,
    )
    center = poi.centroid
    levels = []
    orbit = capture_type == "Objekt umrunden"
    if orbit:
        circular, circle_center, circle_radius = _is_nearly_circular(poi)
        if orbit_geometry not in {"Automatisch", "Kreis um Mittelpunkt", "Kontur mit Abstand"}:
            raise POIPlanningError("Die gewählte POI-Bahnform ist ungültig.")
        use_center_circle = orbit_geometry == "Kreis um Mittelpunkt" or (
            orbit_geometry == "Automatisch" and circular
        )
        if use_center_circle:
            # For arbitrary polygons the farthest contour vertex defines the
            # smallest safe centre-circle. Every polygon edge remains inside
            # the disk through its end points, preserving the minimum offset.
            if not circular:
                circle_center = poi.centroid
                circle_radius = max(
                    math.hypot(x - circle_center.x, y - circle_center.y)
                    for x, y in poi.exterior.coords[:-1]
                )
            coordinates = _safe_circle_coordinates(circle_center, circle_radius, distance_m, control_point_detail_pct)
        else:
            # Polygon edges stay exact; rounded corners receive only the
            # handful of steering points needed for a safe curve.
            detail = min(100.0, max(0.0, float(control_point_detail_pct))) / 100.0
            coordinates = _ring_coordinates(
                poi.buffer(distance_m, join_style="round", resolution=2 + round(6 * detail))
                .simplify(1.8 - 1.6 * detail, preserve_topology=True)
            )
        if len(coordinates) < 3:
            raise POIPlanningError("Die Umlaufbahn konnte nicht aus dem Point of Interest erzeugt werden.")
        # A closed ring needs a repeated first point to produce a complete loop.
        if orbit_clockwise:
            coordinates = list(reversed(coordinates))
        coordinates = coordinates + [coordinates[0]]
    else:
        bearing = math.radians(facade_bearing_deg)
        normal = (math.sin(bearing), math.cos(bearing))  # 0° north, 90° east
        tangent = (normal[1], -normal[0])
        exterior = list(poi.exterior.coords)
        maximum_normal = max((x - center.x) * normal[0] + (y - center.y) * normal[1] for x, y in exterior)
        tangent_values = [(x - center.x) * tangent[0] + (y - center.y) * tangent[1] for x, y in exterior]
        line_normal = maximum_normal + distance_m
        coordinates = [
            (center.x + normal[0] * line_normal + tangent[0] * min(tangent_values), center.y + normal[1] * line_normal + tangent[1] * min(tangent_values)),
            (center.x + normal[0] * line_normal + tangent[0] * max(tangent_values), center.y + normal[1] * line_normal + tangent[1] * max(tangent_values)),
        ]
    for level_index, (target_height, altitude) in enumerate(bands, 1):
        band_coordinates = coordinates if orbit or level_index % 2 else list(reversed(coordinates))
        line = LineString(band_coordinates)
        if not _inside_allowed(line, allowed, blocked):
            raise POIPlanningError(
                f"Höhenebene {level_index} verlässt den Flugbereich oder schneidet ein Sperrgebiet. "
                "Automatische Umfliegungen werden noch nicht erzeugt."
            )
        waypoints = []
        for x, y in band_coordinates:
            lat, lon = _to_geographic(x, y, origin_lat, origin_lon)
            target_x, target_y = (center.x, center.y) if orbit else (x - normal[0] * distance_m, y - normal[1] * distance_m)
            yaw = (math.degrees(math.atan2(target_x - x, target_y - y)) + 360) % 360
            pitch = math.degrees(math.atan2(target_height - altitude, distance_m))
            waypoints.append(POIWaypoint(lat, lon, altitude, max(-90.0, min(0.0, pitch)), yaw, level_index, "capture"))
        levels.append(tuple(waypoints))

    # Facade bands end at the top edge and therefore do not cover a roof. An
    # orbit can add one pass above the object, but never violates the configured
    # ceiling. Each camera points at the centre of the roof, rather than simply
    # looking straight down below the aircraft. A facade-only request
    # intentionally remains a facade-only request.
    if orbit and max_altitude_m > object_height_m + 1e-6:
        roof_altitude = min(max_altitude_m, object_height_m + max(2.0, spacing))
        roof_level_index = len(levels) + 1
        roof_line = LineString(coordinates)
        if not _inside_allowed(roof_line, allowed, blocked):
            raise POIPlanningError(
                "Die Dach-Höhenebene verlässt den Flugbereich oder schneidet ein Sperrgebiet. "
                "Automatische Umfliegungen werden noch nicht erzeugt."
            )
        roof_waypoints = []
        for x, y in coordinates:
            lat, lon = _to_geographic(x, y, origin_lat, origin_lon)
            horizontal_distance = math.hypot(center.x - x, center.y - y)
            yaw = (math.degrees(math.atan2(center.x - x, center.y - y)) + 360) % 360
            pitch = -math.degrees(math.atan2(roof_altitude - object_height_m, horizontal_distance))
            roof_waypoints.append(POIWaypoint(
                lat, lon, roof_altitude, max(-90.0, min(0.0, pitch)), yaw, roof_level_index, "roof_capture"
            ))
        levels.append(tuple(roof_waypoints))
    return POIRoutePlan(tuple(levels), spacing)


__all__ = ["POIPlanningError", "POIRoutePlan", "POIWaypoint", "plan_poi_route"]
