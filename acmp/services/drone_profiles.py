"""Load editable built-in camera profiles from the bundled JSON registry."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


PROFILE_FILE = Path(__file__).resolve().parent.parent / "data" / "drone_profiles.json"
VALID_CATEGORIES = {"consumer", "prosumer_enterprise"}
VALID_RATIOS = {"4:3", "3:2", "16:9"}


@dataclass(frozen=True)
class DroneProfile:
    key: str
    label: str
    category: str
    sensor_format: str
    focal_length_mm: float
    image_ratio: str = "4:3"


def load_drone_profiles(path: Path = PROFILE_FILE) -> tuple[DroneProfile, ...]:
    """Read and validate a JSON profile registry with clear errors for edits."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        entries = document["profiles"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise ValueError(f"Drohnenprofil-Datei ist ungültig: {path.name} ({error})") from error
    if not isinstance(entries, list):
        raise ValueError("Drohnenprofil-Datei: 'profiles' muss eine Liste sein.")
    profiles, keys = [], set()
    for index, entry in enumerate(entries, start=1):
        try:
            profile = DroneProfile(
                key=str(entry["key"]).strip(), label=str(entry["label"]).strip(),
                category=str(entry["category"]), sensor_format=str(entry["sensor_format"]).strip(),
                focal_length_mm=float(entry["focal_length_mm"]), image_ratio=str(entry.get("image_ratio", "4:3")),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"Drohnenprofil #{index} ist unvollständig oder ungültig: {error}") from error
        if not profile.key or not profile.label or not profile.sensor_format or profile.key in keys:
            raise ValueError(f"Drohnenprofil #{index} benötigt eindeutigen Schlüssel, Namen und Sensorformat.")
        if profile.category not in VALID_CATEGORIES or profile.image_ratio not in VALID_RATIOS or profile.focal_length_mm <= 0:
            raise ValueError(f"Drohnenprofil #{index} enthält Kategorie, Bildformat oder Brennweite außerhalb des gültigen Bereichs.")
        profiles.append(profile)
        keys.add(profile.key)
    return tuple(profiles)


DRONE_PROFILES = load_drone_profiles()
PROFILE_BY_KEY = {profile.key: profile for profile in DRONE_PROFILES}

