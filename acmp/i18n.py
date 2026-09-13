"""Language helpers shared by the ACMP user interface."""

UI_EN = {
    "Datei": "File", "Einstellungen": "Settings", "Öffnen …": "Open …", "Speichern unter …": "Save as …",
    "Preset speichern": "Save preset", "Preset laden": "Load preset", "Sprache …": "Language …", "Info": "Info",
    "Karte": "Map", "Flugeinstellungen": "Flight settings", "Exportieren": "Export",
    "Gebiet auswählen": "Select area", "Mein Standort": "My location", "Suchen": "Search",
    "Rechteck": "Rectangle", "Kreis": "Circle", "Polygon": "Polygon", "Sperrgebiete": "No-fly zones",
    "Route generieren und auf Karte zeigen": "Generate route and show on map",
    "Eine Mission erzwingen (Grenzen überschreiten)": "Force one mission (exceed limits)",
    "Foto bei jedem Wegpunkt": "Photo at every waypoint", "Foto nach Distanzintervall": "Photo at distance interval",
    "Keine Aktion": "No action", "Gleichmäßig verteilen": "Distribute evenly", "Maximal ausnutzen": "Use maximum",
}
UI_DE = {english: german for german, english in UI_EN.items()}


def canonical_ui_text(value: str) -> str:
    """Convert translated selection text to the stable internal German value."""
    return UI_DE.get(value, value)
