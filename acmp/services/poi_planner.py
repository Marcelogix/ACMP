"""Independent route planner for point-of-interest capture missions.

POI routes are generated independently as height bands around an object or
parallel facade passes. The optional roof scan reuses only the proven generic
lawnmower geometry helper for its horizontal raster.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from acmp.services.route_planner import (
    add_overshoot_turns, centripetal_catmull_rom_route, cubic_bezier_route, generate_lawnmower_route,
    optimal_direction_deg,
)


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
    # A boundary here is a hard mission break: the direct connection from the
    # preceding route part would touch a forbidden area.
    separate_before: tuple[bool, ...] = ()

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
    return (allowed is None or allowed.covers(line)) and not any(line.intersects(zone) for zone in blocked)


def _smoothed_local_line(coordinates, approximation="catmull_rom"):
    """Create the same centripetal Catmull-Rom approximation used by the map.

    The shared preview helper accepts latitude/longitude pairs.  Scaling the
    local metre coordinates into a tiny synthetic geographic area lets us use
    exactly that interpolation here while retaining metre geometry for the
    subsequent airspace check.
    """
    synthetic = [[y / 111_132.92, x / 111_319.49] for x, y in coordinates]
    smoother = cubic_bezier_route if approximation == "cubic_bezier" else centripetal_catmull_rom_route
    smoothed = smoother(synthetic, samples_per_segment=20)
    return LineString([(lon * 111_319.49, lat * 111_132.92) for lat, lon in smoothed])


def _smooth_connection_is_safe(previous_coordinates, following_coordinates, allowed, blocked, approximation="catmull_rom"):
    """Check a new join with its two Catmull-Rom control points on each side."""
    context = list(previous_coordinates[-2:]) + list(following_coordinates[:2])
    return len(context) < 3 or _inside_allowed(_smoothed_local_line(context, approximation), allowed, blocked)


def _smooth_connection_helpers(previous_coordinates, following_coordinates, allowed, blocked, approximation="catmull_rom"):
    """Find one local steering point when a smooth join would graze a zone."""
    start, end = previous_coordinates[-1], following_coordinates[0]
    candidates = []
    for zone in blocked:
        centre = zone.centroid
        for x, y in list(zone.exterior.coords)[:-1]:
            dx, dy = x - centre.x, y - centre.y
            length = math.hypot(dx, dy) or 1.0
            # Keep the controller point a little beyond the already buffered
            # no-fly boundary; it counters the spline's inward bow.
            candidates.append((x + dx / length * 0.75, y + dy / length * 0.75))
    candidates.sort(key=lambda point: math.dist(start, point) + math.dist(point, end))
    sequences = [[point] for point in candidates]
    # A rectangle that separates both endpoints cannot usually be passed by
    # one corner alone.  Try a two-corner local bypass as well; this is still
    # preferable to splitting otherwise short height bands into missions.
    sequences.extend(
        [[first, second] for first in candidates for second in candidates if first != second]
    )
    for steering_points in sequences:
        connector = LineString([start, *steering_points, end])
        context = list(previous_coordinates[-2:]) + steering_points + list(following_coordinates[:2])
        if _inside_allowed(connector, allowed, blocked) and _inside_allowed(
            _smoothed_local_line(context, approximation), allowed, blocked
        ):
            return steering_points
    return None


def _line_parts(geometry):
    """Return only usable, connected pieces from a Shapely line operation."""
    if geometry.is_empty:
        return []
    if geometry.geom_type == "LineString":
        return [list(geometry.coords)] if geometry.length > 0.05 else []
    if geometry.geom_type in {"MultiLineString", "GeometryCollection"}:
        parts = []
        for item in geometry.geoms:
            parts.extend(_line_parts(item))
        return parts
    return []


def _safe_line_parts(line, allowed, blocked):
    """Clip a route to the permitted airspace without joining separated arcs."""
    safe = line if allowed is None else line.intersection(allowed)
    if blocked:
        safe = safe.difference(unary_union(blocked))
    parts = _line_parts(safe)
    # A ring is represented as a line whose first coordinate is repeated at
    # the end.  Shapely may split its one remaining safe arc at precisely this
    # artificial seam. Rejoin only that seam; genuinely separate arcs stay
    # separate and therefore become distinct missions.
    source = list(line.coords)
    if len(parts) > 1 and source and source[0] == source[-1]:
        first, last = parts[0], parts[-1]
        if math.hypot(first[0][0] - last[-1][0], first[0][1] - last[-1][1]) < 0.05:
            parts = [last + first[1:]] + parts[1:-1]
    # Boolean clipping returns intersection coordinates directly on the
    # forbidden boundary.  Move them a short distance into the retained line
    # piece: otherwise a vertical level transition at that point merely
    # *touches* the safety buffer and must be treated as unsafe.
    def pull_endpoints_inward(part, distance_m=0.15):
        if len(part) < 2:
            return part
        start, next_point = part[0], part[1]
        end, previous = part[-1], part[-2]

        def move_toward(point, target):
            length = math.hypot(target[0] - point[0], target[1] - point[1])
            if length <= distance_m:
                return point
            factor = distance_m / length
            return (
                point[0] + (target[0] - point[0]) * factor,
                point[1] + (target[1] - point[1]) * factor,
            )

        adjusted = list(part)
        adjusted[0] = move_toward(start, next_point)
        adjusted[-1] = move_toward(end, previous)
        return adjusted

    return [pull_endpoints_inward(part) for part in parts]


def _local_detour_route(coordinates, allowed, blocked, object_keepout):
    """Replace only blocked chords with short visibility-graph detours.

    The object keep-out makes the inner corridor usable when it exists, while
    still preventing a shortcut through the object.  Candidate corners are
    shifted beyond their buffered boundary so DJI steering points never sit
    directly on a safety boundary.
    """
    obstacles = list(blocked) + [object_keepout]

    def safe_segment(start, end):
        segment = LineString([start, end])
        return (allowed is None or allowed.covers(segment)) and not any(segment.intersects(item) for item in obstacles)

    def detour(start, end):
        if safe_segment(start, end):
            return [end]
        nodes = [start, end]
        for obstacle in obstacles:
            if obstacle.geom_type != "Polygon":
                return None
            centre = obstacle.centroid
            for x, y in list(obstacle.exterior.coords)[:-1]:
                dx, dy = x - centre.x, y - centre.y
                length = math.hypot(dx, dy) or 1.0
                nodes.append((x + dx / length * 0.25, y + dy / length * 0.25))
        distances = [float("inf")] * len(nodes)
        previous = [-1] * len(nodes)
        distances[0] = 0.0
        remaining = set(range(len(nodes)))
        while remaining:
            current = min(remaining, key=lambda index: distances[index])
            if distances[current] == float("inf"):
                break
            remaining.remove(current)
            if current == 1:
                break
            for candidate in remaining:
                if not safe_segment(nodes[current], nodes[candidate]):
                    continue
                length = math.dist(nodes[current], nodes[candidate])
                if distances[current] + length < distances[candidate]:
                    distances[candidate] = distances[current] + length
                    previous[candidate] = current
        if previous[1] < 0:
            return None
        path = []
        current = 1
        while current >= 0:
            path.append(nodes[current])
            current = previous[current]
        return list(reversed(path))[1:]

    route = [coordinates[0]]
    for start, end in zip(coordinates, coordinates[1:]):
        replacement = detour(start, end)
        if replacement is None:
            return None
        route.extend(replacement)
    return route


def _concentric_orbit_detours(coordinates, center, object_radius, allowed, blocked):
    """Keep the requested orbit except for radial in/out avoidance arcs.

    A blocked section is replaced by a shorter-radius arc first.  Only if the
    complete inner arc and both radial transitions are safe do we use it;
    otherwise the same section is tested on progressively larger circles.
    This deliberately produces ``outer → inner/outer → outer`` rather than a
    generic corner-to-corner navigation path.
    """
    ring = list(coordinates[:-1])
    if len(ring) < 3:
        return None
    radii = [math.hypot(x - center.x, y - center.y) for x, y in ring]
    base_radius = sum(radii) / len(radii)
    if max(abs(radius - base_radius) for radius in radii) > 0.25:
        return None  # contour or non-centred orbit: retain its existing fallback
    orientation = sum(
        ring[index][0] * ring[(index + 1) % len(ring)][1] - ring[(index + 1) % len(ring)][0] * ring[index][1]
        for index in range(len(ring))
    )
    direction = 1 if orientation >= 0 else -1
    count = len(ring) * 4  # sufficient density for safe radial transitions
    first_angle = math.atan2(ring[0][1] - center.y, ring[0][0] - center.x)

    def point(angle_index, radius):
        angle = first_angle + direction * 2 * math.pi * angle_index / count
        return (center.x + radius * math.cos(angle), center.y + radius * math.sin(angle))

    # A true object buffer is provided by the caller through object_radius:
    # for a centred circle this is exactly the radius that must not be crossed.
    object_keepout = Point(center.x, center.y).buffer(object_radius + 2.0)

    def safe_segment(start, end):
        segment = LineString([start, end])
        return (allowed is None or allowed.covers(segment)) and not segment.intersects(object_keepout) and not any(segment.intersects(zone) for zone in blocked)

    base = [point(index, base_radius) for index in range(count)]
    edges = [not safe_segment(base[index], base[(index + 1) % count]) for index in range(count)]
    # Reserve a few otherwise-valid outer-circle steps before and after a
    # conflict. They provide room for the radial transition itself instead of
    # starting that transition directly beside a rectangle corner.
    original_edges = list(edges)
    for index, blocked_edge in enumerate(original_edges):
        if blocked_edge:
            for offset in range(-3, 4):
                edges[(index + offset) % count] = True
    if not any(edges):
        return coordinates
    if all(edges):
        return None
    # Start just after a safe edge, so each blocked edge run is linear rather
    # than wrapping around the arbitrary first waypoint.
    start = next(index for index, blocked_edge in enumerate(edges) if not blocked_edge)
    ordered_edges = [edges[(start + offset + 1) % count] for offset in range(count)]
    ordered_base = [base[(start + offset + 1) % count] for offset in range(count)]
    route = [ordered_base[0]]
    index = 0
    while index < count:
        if not ordered_edges[index]:
            route.append(ordered_base[(index + 1) % count])
            index += 1
            continue
        end = index
        while end + 1 < count and ordered_edges[end + 1]:
            end += 1
        entry_index, exit_index = index, end + 1
        entry, exit_point = ordered_base[entry_index], ordered_base[exit_index % count]
        candidates = [base_radius - step * 0.5 for step in range(1, int((base_radius - object_radius - 2.0) / 0.5) + 1)]
        candidates += [base_radius + step * 0.5 for step in range(1, 101)]
        replacement = None
        for radius in candidates:
            arc = [point((start + 1 + offset) % count, radius) for offset in range(entry_index, exit_index + 1)]
            candidate = [entry, arc[0], *arc[1:], exit_point]
            if all(safe_segment(first, second) for first, second in zip(candidate, candidate[1:])):
                replacement = candidate[1:]
                break
        if replacement is None:
            return None
        route.extend(replacement)
        index = end + 1
    # Preserve a closed orbit. The final direct edge was chosen as the safe
    # seam above, so it cannot cut through the zone.
    return route + [route[0]]


def _contour_offset_detours(poi, coordinates, requested_offset, allowed, blocked, boundary_clearance_m, support_spacing_m=None):
    """Follow a no-fly boundary locally, then return to the original contour."""
    keepout = poi.buffer(2.0)

    def safe_segment(start, end):
        segment = LineString([start, end])
        return (allowed is None or allowed.covers(segment)) and not segment.intersects(keepout) and not any(segment.intersects(zone) for zone in blocked)

    def boundary_arcs(ring, start, end):
        length = ring.length
        first_distance, last_distance = ring.project(Point(start)), ring.project(Point(end))
        vertices = list(ring.coords[:-1])
        vertex_distances = [(ring.project(Point(point)), point) for point in vertices]
        arcs = []
        for direction in (1, -1):
            span = ((last_distance - first_distance) * direction) % length
            selected = []
            for distance, point in vertex_distances:
                progress = ((distance - first_distance) * direction) % length
                if 1e-6 < progress < span - 1e-6:
                    selected.append((progress, point))
            selected.sort(key=lambda item: item[0])
            arcs.append([ring.interpolate(first_distance).coords[0], *(point for _progress, point in selected), ring.interpolate(last_distance).coords[0]])
        return arcs

    def add_corner_support_points(points):
        """Place one point before and after each genuine boundary corner."""
        if not support_spacing_m or len(points) < 3:
            return points
        result = [points[0]]
        for previous, corner, following in zip(points, points[1:], points[2:]):
            incoming = math.dist(previous, corner)
            outgoing = math.dist(corner, following)
            if incoming < 0.05 or outgoing < 0.05:
                result.append(corner)
                continue
            distance = min(float(support_spacing_m), incoming / 3, outgoing / 3)
            before = tuple(corner[axis] + (previous[axis] - corner[axis]) * distance / incoming for axis in (0, 1))
            after = tuple(corner[axis] + (following[axis] - corner[axis]) * distance / outgoing for axis in (0, 1))
            result.extend([before, corner, after])
        result.append(points[-1])
        return result

    def intersection_distances(segment, zone):
        """First and last contact with a buffered no-fly boundary."""
        contact = segment.intersection(zone)
        points = []
        def collect(geometry):
            if geometry.is_empty:
                return
            if geometry.geom_type == "Point":
                points.append(geometry)
            elif geometry.geom_type == "LineString":
                points.extend(Point(value) for value in geometry.coords)
            elif hasattr(geometry, "geoms"):
                for item in geometry.geoms:
                    collect(item)
        collect(contact)
        distances = sorted(segment.project(point) for point in points)
        return (distances[0], distances[-1]) if distances else None

    def detour(source_coordinates, zone):
        segment = LineString(source_coordinates)
        start, end = source_coordinates[0], source_coordinates[-1]
        contacts = intersection_distances(segment, zone)
        if contacts is None:
            return None
        # Move the two transition points 0.75 m away from the safety buffer,
        # keeping them safely on the original contour rather than its edge.
        margin = min(0.75, segment.length / 4)
        before = segment.interpolate(max(0.0, contacts[0] - margin)).coords[0]
        after = segment.interpolate(min(segment.length, contacts[1] + margin)).coords[0]
        # The no-fly geometry already contains the regular 2 m safety buffer.
        # This is additional to the regular no-fly safety buffer. Smooth DJI
        # routes need more reserve than explicitly supported right-angle turns.
        boundary = zone.buffer(boundary_clearance_m, join_style="mitre").simplify(0.75, preserve_topology=True)
        if boundary.geom_type != "Polygon":
            return None
        ring_coordinates = list(boundary.exterior.coords)
        ring = LineString(ring_coordinates)
        arcs = boundary_arcs(ring, before, after)
        # Prefer the arc nearest the POI only when the actual remaining gap is
        # at least five metres. Otherwise take the outer arc around the zone.
        inner_available = poi.distance(zone) >= 5.0
        arcs.sort(key=lambda arc: sum(Point(point).distance(poi) for point in arc) / len(arc), reverse=not inner_available)
        arc = add_corner_support_points(arcs[0])
        candidate = [start, before, *arc, after, end]
        if all(safe_segment(first, second) for first, second in zip(candidate, candidate[1:])):
            return candidate[1:]
        return None

    route, index = [coordinates[0]], 0
    while index < len(coordinates) - 1:
        start, end = coordinates[index], coordinates[index + 1]
        if safe_segment(start, end):
            route.append(end)
            index += 1
            continue
        last = index
        while last + 1 < len(coordinates) - 1 and not safe_segment(coordinates[last + 1], coordinates[last + 2]):
            last += 1
        source = coordinates[index:last + 2]
        source_line = LineString(source)
        zones = [zone for zone in blocked if source_line.intersects(zone)]
        # Multiple overlapping zones are handled by the safe fallback instead
        # of inventing an ambiguous sequence of boundary-following arcs.
        replacement = detour(source, zones[0]) if len(zones) == 1 else None
        if replacement is None:
            return None
        route.extend(replacement)
        index = last + 1
    return route


def _flight_boundary_detours(coordinates, allowed, blocked):
    """Replace only out-of-field sections by a short inside boundary arc."""
    if allowed is None or allowed.geom_type not in {"Polygon", "MultiPolygon"}:
        return None

    def safe_segment(start, end):
        segment = LineString([start, end])
        return allowed.covers(segment) and not any(segment.intersects(zone) for zone in blocked)

    def boundary_arcs(ring, start, end):
        length = ring.length
        first, last = ring.project(Point(start)), ring.project(Point(end))
        vertices = [(ring.project(Point(point)), point) for point in list(ring.coords[:-1])]
        arcs = []
        for direction in (1, -1):
            span = ((last - first) * direction) % length
            selected = [
                (((distance - first) * direction) % length, point)
                for distance, point in vertices
                if 1e-6 < ((distance - first) * direction) % length < span - 1e-6
            ]
            selected.sort(key=lambda item: item[0])
            arcs.append([ring.interpolate(first).coords[0], *(point for _progress, point in selected), ring.interpolate(last).coords[0]])
        return arcs

    def detour(source):
        line = LineString(source)
        contact = line.intersection(allowed.boundary)
        points = []
        def collect(geometry):
            if geometry.is_empty:
                return
            if geometry.geom_type == "Point":
                points.append(geometry)
            elif geometry.geom_type == "LineString":
                points.extend(Point(value) for value in geometry.coords)
            elif hasattr(geometry, "geoms"):
                for item in geometry.geoms:
                    collect(item)
        collect(contact)
        distances = sorted(line.project(point) for point in points)
        if len(distances) < 2:
            return None
        margin = min(0.75, line.length / 4)
        before = line.interpolate(max(0.0, distances[0] - margin)).coords[0]
        after = line.interpolate(min(line.length, distances[-1] + margin)).coords[0]
        polygons = [allowed] if allowed.geom_type == "Polygon" else list(allowed.geoms)
        for polygon in polygons:
            # Keep the actual flight path half a metre inside the boundary.
            inset = polygon.buffer(-0.5, join_style="mitre")
            if inset.is_empty or inset.geom_type != "Polygon":
                continue
            ring = LineString(list(inset.exterior.coords))
            for arc in sorted(boundary_arcs(ring, before, after), key=lambda item: LineString(item).length):
                candidate = [source[0], before, *arc, after, source[-1]]
                if all(safe_segment(first, second) for first, second in zip(candidate, candidate[1:])):
                    return candidate[1:]
        return None

    route, index = [coordinates[0]], 0
    while index < len(coordinates) - 1:
        start, end = coordinates[index], coordinates[index + 1]
        if safe_segment(start, end):
            route.append(end)
            index += 1
            continue
        last = index
        while last + 1 < len(coordinates) - 1 and not safe_segment(coordinates[last + 1], coordinates[last + 2]):
            last += 1
        replacement = detour(coordinates[index:last + 2])
        if replacement is None:
            return None
        route.extend(replacement)
        index = last + 1
    return route


def plan_poi_route(
    poi_area, flight_areas, no_fly_zones, *, capture_type, facade_bearing_deg,
    orbit_clockwise, object_height_m, distance_m, min_altitude_m, max_altitude_m,
    vertical_overlap_pct, sensor_diagonal_mm, focal_length_mm, image_ratio,
    control_point_detail_pct=70, orbit_geometry="Automatisch",
    no_fly_strategy="adapt", outside_strategy="adapt", safety_margin_m=2.0,
    contour_boundary_clearance_m=1.5,
    contour_support_spacing_m=None,
    smoothing_approximation="catmull_rom",
    level_transition_mode="Standard",
    level_transition_support_spacing_m=2.0,
    no_fly_heights_m=None,
    top_down_roof_scan=False,
    top_down_overshoot_m=0.0,
    reduced_overshoot=False,
):
    """Create a 2.5D POI plan, optionally adapting or clipping POI bands.

    ``adapt`` first searches a complete safe orbit at a closer (then farther)
    offset.  If that is impossible it deliberately falls back to ``skip``:
    disconnected safe arcs are never connected through a forbidden area.
    """
    if len(poi_area) < 3:
        raise POIPlanningError("Bitte zeichne einen Point of Interest mit mindestens drei Punkten.")
    if not flight_areas and outside_strategy != "allow":
        raise POIPlanningError("Für eine POI-Route wird mindestens ein Flugbereich benötigt.")
    origin_lat = sum(point[0] for point in poi_area) / len(poi_area)
    origin_lon = sum(point[1] for point in poi_area) / len(poi_area)
    poi = _local_geometry(poi_area, origin_lat, origin_lon)
    if not poi.is_valid or poi.area <= 0:
        raise POIPlanningError("Die POI-Geometrie ist ungültig.")
    if no_fly_strategy not in {"allow", "adapt", "skip"}:
        raise POIPlanningError("Die POI-Sperrgebietsstrategie ist ungültig.")
    if outside_strategy not in {"allow", "adapt", "skip"}:
        raise POIPlanningError("Die POI-Flugbereichsstrategie ist ungültig.")
    if smoothing_approximation not in {"catmull_rom", "cubic_bezier"}:
        raise POIPlanningError("Die gewählte Flugbahn-Approximation ist ungültig.")
    allowed = None if outside_strategy == "allow" else unary_union(
        [_local_geometry(area, origin_lat, origin_lon) for area in flight_areas]
    )
    blocked = [] if no_fly_strategy == "allow" else [
        _local_geometry(area, origin_lat, origin_lon).buffer(safety_margin_m)
        for area in no_fly_zones
    ]
    zone_heights = list(no_fly_heights_m or [])
    zone_heights = (zone_heights + [120.0] * max(0, len(no_fly_zones) - len(zone_heights)))[:len(no_fly_zones)]
    center = poi.centroid
    orbit = capture_type == "Objekt umrunden"
    if orbit:
        circular, circle_center, circle_radius = _is_nearly_circular(poi)
        if orbit_geometry not in {"Automatisch", "Kreis um Mittelpunkt", "Kontur mit Abstand"}:
            raise POIPlanningError("Die gewählte POI-Bahnform ist ungültig.")
        use_center_circle = orbit_geometry == "Kreis um Mittelpunkt" or (
            orbit_geometry == "Automatisch" and circular
        )
        def orbit_coordinates(offset_m):
            if use_center_circle:
                return _safe_circle_coordinates(circle_center, circle_radius, offset_m, control_point_detail_pct)
            detail = min(100.0, max(0.0, float(control_point_detail_pct))) / 100.0
            return _ring_coordinates(
                poi.buffer(offset_m, join_style="round", resolution=2 + round(6 * detail))
                .simplify(1.8 - 1.6 * detail, preserve_topology=True)
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
            coordinates = orbit_coordinates(distance_m)
        else:
            # Polygon edges stay exact; rounded corners receive only the
            # handful of steering points needed for a safe curve.
            coordinates = orbit_coordinates(distance_m)
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
    # Preserve an otherwise unmodified path for levels above every applicable
    # zone ceiling. It still respects the selected flight-area policy.
    clear_coordinates = list(coordinates)
    clear_line = LineString(clear_coordinates)
    if outside_strategy == "adapt" and allowed is not None and not allowed.covers(clear_line):
        clear_route = _flight_boundary_detours(clear_coordinates, allowed, [])
        if clear_route is not None:
            clear_coordinates = clear_route
            clear_line = LineString(clear_coordinates)
    # First retain the requested offset.  For "Anpassen" use a whole safe
    # orbit/pass if possible; this preserves complete coverage and makes its
    # overlap calculation unambiguous.  Otherwise clipping below is the safe
    # fallback requested by the UI.
    effective_distance = distance_m
    base_line = LineString(coordinates)
    if no_fly_strategy == "adapt" and blocked and any(base_line.intersects(zone) for zone in blocked):
        local_route = (
            _concentric_orbit_detours(coordinates, circle_center, circle_radius, allowed, blocked)
            if orbit and use_center_circle else
            _contour_offset_detours(poi, coordinates, distance_m, allowed, blocked, contour_boundary_clearance_m, contour_support_spacing_m)
            if orbit else _local_detour_route(coordinates, allowed, blocked, poi.buffer(2.0))
        )
        if local_route is not None:
            coordinates = local_route
            base_line = LineString(coordinates)
            # A locally inward detour has a smaller image footprint. Base the
            # height-band spacing on that worst case, never on the original
            # wider distance.
            effective_distance = min(distance_m, min(Point(point).distance(poi) for point in coordinates))
    if outside_strategy == "adapt" and allowed is not None and not allowed.covers(base_line):
        field_route = _flight_boundary_detours(coordinates, allowed, blocked)
        if field_route is not None:
            coordinates = field_route
            base_line = LineString(coordinates)
    # A global radius change is allowed only as a no-fly fallback. Flight-area
    # adaptation must remain local along the field boundary above.
    if no_fly_strategy == "adapt" and not _inside_allowed(base_line, allowed, blocked):
        candidates = [max(2.0, distance_m - step * 0.5) for step in range(1, int(max(0, distance_m - 2.0) / 0.5) + 1)]
        if no_fly_strategy == "adapt":
            candidates += [distance_m + step * 0.5 for step in range(1, 101)]
        for candidate_distance in candidates:
            if orbit:
                candidate = orbit_coordinates(candidate_distance)
                if orbit_clockwise:
                    candidate = list(reversed(candidate))
                candidate = candidate + [candidate[0]]
            else:
                # A facade can only move closer for a bounded flight area.
                shift = candidate_distance - distance_m
                candidate = [(x + normal[0] * shift, y + normal[1] * shift) for x, y in coordinates]
            if _inside_allowed(LineString(candidate), allowed, blocked):
                coordinates, effective_distance, base_line = candidate, candidate_distance, LineString(candidate)
                break

    bands, spacing = _height_bands(
        object_height_m, min_altitude_m, max_altitude_m, effective_distance, vertical_overlap_pct,
        sensor_diagonal_mm, focal_length_mm, image_ratio,
    )
    levels = []
    separate_before = []
    previous_coordinates = []
    previous_altitude = None
    must_clip = not _inside_allowed(base_line, allowed, blocked)
    for level_index, (target_height, altitude) in enumerate(bands, 1):
        active_zone_count = sum(altitude <= height + 0.5 for height in zone_heights)
        level_coordinates = coordinates if active_zone_count else clear_coordinates
        level_blocked = blocked if active_zone_count else []
        level_must_clip = must_clip if active_zone_count else not _inside_allowed(clear_line, allowed, level_blocked)
        ordered = level_coordinates if orbit or level_index % 2 else list(reversed(level_coordinates))
        parts = [ordered] if not level_must_clip else _safe_line_parts(LineString(ordered), allowed, level_blocked)
        if not parts:
            raise POIPlanningError(
                f"Höhenebene {level_index} hat außerhalb der Sperr- und Flugbereiche keine sichere Aufnahmebahn."
            )
        # Alternate both direction and arc order. This produces the desired
        # bottom-to-top / top-to-bottom zig-zag for a half orbit.
        if level_index % 2 == 0:
            parts = [list(reversed(part)) for part in reversed(parts)]
        for part_index, band_coordinates in enumerate(parts):
            if len(band_coordinates) < 2:
                continue
            transition_coordinates = []
            transition = False
            connection_blocked = [
                zone for zone, height in zip(blocked, zone_heights)
                if previous_altitude is None or min(previous_altitude, altitude) <= height + 0.5
            ]
            if previous_coordinates and not _smooth_connection_is_safe(
                previous_coordinates, band_coordinates, allowed, connection_blocked, smoothing_approximation
            ):
                transition_coordinates = _smooth_connection_helpers(
                    previous_coordinates, band_coordinates, allowed, connection_blocked, smoothing_approximation
                )
                # A separate mission is the last resort.  Normally a single
                # local steering point retains the merged POI height bands.
                transition = transition_coordinates is None
                if transition:
                    transition_coordinates = []
            route_coordinates = transition_coordinates + list(band_coordinates)
            waypoints = []
            for point_index, (x, y) in enumerate(route_coordinates):
                lat, lon = _to_geographic(x, y, origin_lat, origin_lon)
                target_x, target_y = (center.x, center.y) if orbit else (x - normal[0] * effective_distance, y - normal[1] * effective_distance)
                yaw = (math.degrees(math.atan2(target_x - x, target_y - y)) + 360) % 360
                horizontal_distance = math.hypot(target_x - x, target_y - y)
                pitch = math.degrees(math.atan2(target_height - altitude, horizontal_distance))
                kind = "transition" if point_index < len(transition_coordinates) else "capture"
                waypoints.append(POIWaypoint(lat, lon, altitude, max(-90.0, min(0.0, pitch)), yaw, level_index, kind))
            if len(waypoints) >= 2:
                levels.append(tuple(waypoints))
                separate_before.append(transition)
                previous_coordinates = route_coordinates
                previous_altitude = altitude

    # Facade bands end at the top edge and therefore do not cover a roof. An
    # orbit can add one pass above the object, but never violates the configured
    # ceiling. Each camera points at the centre of the roof, rather than simply
    # looking straight down below the aircraft. A facade-only request
    # intentionally remains a facade-only request.
    if orbit and max_altitude_m > object_height_m + 1e-6:
        roof_altitude = min(max_altitude_m, object_height_m + max(2.0, spacing))
        roof_level_index = len(levels) + 1
        roof_active_zone_count = sum(roof_altitude <= height + 0.5 for height in zone_heights)
        roof_coordinates = coordinates if roof_active_zone_count else clear_coordinates
        roof_blocked = blocked if roof_active_zone_count else []
        roof_must_clip = must_clip if roof_active_zone_count else not _inside_allowed(clear_line, allowed, roof_blocked)
        roof_parts = [roof_coordinates] if not roof_must_clip else _safe_line_parts(LineString(roof_coordinates), allowed, roof_blocked)
        if not roof_parts:
            raise POIPlanningError("Die Dach-Höhenebene hat keine sichere Aufnahmebahn.")
        for roof_part_index, roof_coordinates in enumerate(roof_parts):
            transition_coordinates = []
            transition = False
            connection_blocked = [
                zone for zone, height in zip(blocked, zone_heights)
                if previous_altitude is None or min(previous_altitude, roof_altitude) <= height + 0.5
            ]
            if previous_coordinates and not _smooth_connection_is_safe(
                previous_coordinates, roof_coordinates, allowed, connection_blocked, smoothing_approximation
            ):
                transition_coordinates = _smooth_connection_helpers(
                    previous_coordinates, roof_coordinates, allowed, connection_blocked, smoothing_approximation
                )
                transition = transition_coordinates is None
                if transition:
                    transition_coordinates = []
            route_coordinates = transition_coordinates + list(roof_coordinates)
            roof_waypoints = []
            for point_index, (x, y) in enumerate(route_coordinates):
                lat, lon = _to_geographic(x, y, origin_lat, origin_lon)
                horizontal_distance = math.hypot(center.x - x, center.y - y)
                yaw = (math.degrees(math.atan2(center.x - x, center.y - y)) + 360) % 360
                pitch = -math.degrees(math.atan2(roof_altitude - object_height_m, horizontal_distance))
                roof_waypoints.append(POIWaypoint(
                    lat, lon, roof_altitude, max(-90.0, min(0.0, pitch)), yaw, roof_level_index,
                    "transition" if point_index < len(transition_coordinates) else "roof_capture"
                ))
            if len(roof_waypoints) >= 2:
                levels.append(tuple(roof_waypoints))
                separate_before.append(transition)
                previous_coordinates = route_coordinates
                previous_altitude = roof_altitude
    if top_down_roof_scan and max_altitude_m >= object_height_m + distance_m:
        # Reuse the established terrain scan path generator: alternating rows,
        # proper U-turns and optional exterior overshoot points. It remains a
        # single POI level so normal mission-limit splitting can keep it whole.
        roof_altitude = object_height_m + distance_m
        footprint = _vertical_footprint_m(distance_m, sensor_diagonal_mm, focal_length_mm, image_ratio)
        spacing = footprint * (1 - vertical_overlap_pct / 100)
        raw_no_fly = no_fly_zones if no_fly_strategy != "allow" else []
        terrain_route = generate_lawnmower_route(
            poi_area, spacing, optimal_direction_deg(poi_area), raw_no_fly, allow_outside=True,
        )
        overshot_route, _unused_overshoot_paths = add_overshoot_turns(
            terrain_route, top_down_overshoot_m, reduced_overshoot,
        )
        def local_line(route):
            return LineString([
                ((lon - origin_lon) * 111_319.49 * math.cos(math.radians(origin_lat)),
                 (lat - origin_lat) * 111_132.92)
                for lat, lon in route
            ])
        # Overshoot is optional safety/turning room, never authority to leave
        # the configured flight area or enter a no-fly zone. Fall back to the
        # contained terrain route when the exterior turn cannot be flown.
        if not _inside_allowed(local_line(overshot_route), allowed, blocked):
            terrain_route = generate_lawnmower_route(
                poi_area, spacing, optimal_direction_deg(poi_area), raw_no_fly, allow_outside=False,
            )
        if len(terrain_route) < 2 or not _inside_allowed(local_line(terrain_route), allowed, blocked):
            raise POIPlanningError("Für den Top-Down-Dachscan konnte keine sichere Rasterroute erzeugt werden.")
        roof_waypoints = []
        route = overshot_route if _inside_allowed(local_line(overshot_route), allowed, blocked) else terrain_route
        for index, (lat, lon) in enumerate(route):
            target = route[index + 1] if index + 1 < len(route) else route[index - 1]
            yaw = (math.degrees(math.atan2(target[1] - lon, target[0] - lat)) + 360) % 360
            roof_waypoints.append(POIWaypoint(
                lat, lon, roof_altitude, -90.0, yaw, len(levels) + 1, "roof_topdown"
            ))
        levels.append(tuple(roof_waypoints))
        separate_before.append(False)
    elif top_down_roof_scan:
        raise POIPlanningError(
            "Für den Top-Down-Dachscan muss die Maximalflughöhe mindestens Objekthöhe plus Objektabstand erreichen."
        )
    if level_transition_mode == "Stützpunkte":
        levels = _add_level_transition_support_points(levels, separate_before, level_transition_support_spacing_m)
    return POIRoutePlan(tuple(levels), spacing, tuple(separate_before))


def _add_level_transition_support_points(levels, separate_before, spacing_m):
    """Add two on-path controllers before and after every connected level change."""
    result = [list(level) for level in levels]
    spacing_m = max(0.1, float(spacing_m))
    for index in range(len(result) - 1):
        if index + 1 < len(separate_before) and separate_before[index + 1]:
            continue
        previous, following = result[index], result[index + 1]
        if len(previous) < 2 or len(following) < 2:
            continue
        def fraction(a, b):
            distance = math.hypot((a.lat - b.lat) * 111_132.92, (a.lon - b.lon) * 111_319.49)
            return min(0.45, spacing_m / max(distance, 0.01))
        def between(a, b, factor, level):
            return POIWaypoint(a.lat + (b.lat - a.lat) * factor, a.lon + (b.lon - a.lon) * factor,
                               a.altitude_m + (b.altitude_m - a.altitude_m) * factor,
                               a.gimbal_pitch_deg + (b.gimbal_pitch_deg - a.gimbal_pitch_deg) * factor,
                               a.yaw_deg + (b.yaw_deg - a.yaw_deg) * factor, level, "transition")
        tail_fraction = fraction(previous[-2], previous[-1])
        head_fraction = fraction(following[0], following[1])
        # Four additional controllers: two immediately before the old level's
        # endpoint and two after the new level's start point.
        result[index] = previous[:-1] + [between(previous[-2], previous[-1], 1 - 2 * tail_fraction, previous[-1].level), between(previous[-2], previous[-1], 1 - tail_fraction, previous[-1].level), previous[-1]]
        result[index + 1] = [following[0], between(following[0], following[1], head_fraction, following[0].level), between(following[0], following[1], 2 * head_fraction, following[0].level)] + following[1:]
    return result


__all__ = ["POIPlanningError", "POIRoutePlan", "POIWaypoint", "plan_poi_route"]
