"""Extract display-only waypoint paths from DJI WPML/KMZ mission files."""
from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


def read_waypoint_path(kmz_path: Path) -> list[list[float]]:
    """Return ordered ``[latitude, longitude]`` points from a DJI KMZ."""
    with zipfile.ZipFile(kmz_path) as archive:
        names = archive.namelist()
        source = next((name for name in names if name.lower() == "wpmz/waylines.wpml"), None)
        source = source or next((name for name in names if name.lower().endswith((".wpml", ".kml"))), None)
        if source is None:
            raise ValueError("Die KMZ enthält keine WPML/KML-Missionsdatei.")
        root = ET.fromstring(archive.read(source))
    points: list[tuple[int, list[float]]] = []
    for fallback_index, placemark in enumerate(root.iter()):
        if placemark.tag.rsplit("}", 1)[-1] != "Placemark":
            continue
        coordinates = next((node.text for node in placemark.iter() if node.tag.rsplit("}", 1)[-1] == "coordinates"), None)
        if not coordinates:
            continue
        try:
            longitude, latitude, *_ = coordinates.strip().split(",")
            point = [float(latitude), float(longitude)]
        except ValueError:
            continue
        wp_index = next((node.text for node in placemark.iter() if node.tag.rsplit("}", 1)[-1] == "index"), None)
        try:
            order = int(wp_index) if wp_index is not None else fallback_index
        except ValueError:
            order = fallback_index
        points.append((order, point))
    path = [point for _order, point in sorted(points, key=lambda entry: entry[0])]
    if len(path) < 2:
        raise ValueError("Die Mission enthält weniger als zwei lesbare Wegpunkte.")
    return path


__all__ = ["read_waypoint_path"]
