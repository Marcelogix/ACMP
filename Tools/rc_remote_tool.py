"""Read-only RC 2 mission browser and KMZ inspector for ACMP.

Start from the repository root with ``python Tools/rc_remote_tool.py``.
The tool never writes to the remote control.  Downloaded KMZ files live only
in a temporary directory while this window is open.
"""
from __future__ import annotations

import json
import sys
import tempfile
import xml.dom.minidom
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QAction, QFontDatabase
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from acmp.services.rc2_manager import RC2Manager, RC2Mission
from acmp.services.rc2_mission_parser import read_waypoint_path


MAP_HTML = """<!doctype html><html><head><meta charset='utf-8'>
<link rel='stylesheet' href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css'>
<script src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'></script>
<style>html,body,#map{height:100%;width:100%;margin:0}.leaflet-container{font-family:Segoe UI,Arial,sans-serif}</style>
</head><body><div id='map'></div><script>
const map=L.map('map',{zoomControl:true}).setView([51.1657,10.4515],6);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:20,attribution:'© OpenStreetMap-Mitwirkende'}).addTo(map);
let missionLayer=L.layerGroup().addTo(map);
function showMission(route,label){
  missionLayer.clearLayers(); if(!route || route.length<2) return;
  const line=L.polyline(route,{color:'#d13c10',weight:4,opacity:.92}).addTo(missionLayer);
  L.circleMarker(route[0],{radius:7,color:'#087f5b',fillOpacity:1}).bindTooltip('Start').addTo(missionLayer);
  L.circleMarker(route[route.length-1],{radius:7,color:'#b42318',fillOpacity:1}).bindTooltip('Ende').addTo(missionLayer);
  route.forEach((p,i)=>L.circleMarker(p,{radius:3,color:'#fff',weight:2,fillColor:'#d13c10',fillOpacity:1}).bindTooltip(String(i+1)).addTo(missionLayer));
  line.bindTooltip(label,{sticky:true}); map.fitBounds(line.getBounds().pad(.14));
}
</script></body></html>"""


class KmzInspector(QDialog):
    """Show archive files, XML structure, and raw KMZ source for debugging."""

    def __init__(self, path: Path, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(f"KMZ-Debugger – {path.name}")
        self.resize(980, 650)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("KMZ-Dateien sind ZIP-Archive. Die Strukturansicht zeigt alle XML-Keys und Values; bei einem Wegpunkt erscheinen dessen Einstellungen gemeinsam rechts."))
        tabs = QTabWidget()

        structure_page = QWidget()
        structure_layout = QVBoxLayout(structure_page)
        structure_split = QSplitter()
        self.structure = QTreeWidget()
        self.structure.setHeaderLabels(["KMZ-/XML-Struktur"])
        self.properties = QTableWidget(0, 2)
        self.properties.setHorizontalHeaderLabels(["Key", "Value"])
        self.properties.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.properties.setAlternatingRowColors(True)
        self.properties.horizontalHeader().setStretchLastSection(True)
        structure_split.addWidget(self.structure)
        structure_split.addWidget(self.properties)
        structure_split.setStretchFactor(1, 1)
        structure_layout.addWidget(structure_split)
        tabs.addTab(structure_page, "Struktur & Einstellungen")

        raw_page = QWidget()
        raw_layout = QVBoxLayout(raw_page)
        split = QSplitter()
        self.files = QTreeWidget()
        self.files.setHeaderLabels(["Archivdatei", "Größe"])
        self.text = QTextEdit(readOnly=True)
        self.text.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        split.addWidget(self.files)
        split.addWidget(self.text)
        split.setStretchFactor(1, 1)
        raw_layout.addWidget(split)
        tabs.addTab(raw_page, "Archiv & Rohdatei")
        layout.addWidget(tabs, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._contents: dict[str, bytes] = {}
        try:
            with zipfile.ZipFile(path) as archive:
                for info in archive.infolist():
                    self._contents[info.filename] = archive.read(info.filename)
                    self._add_archive_file(info.filename, info.file_size)
                    self._add_xml_structure(info.filename, self._contents[info.filename])
        except (OSError, zipfile.BadZipFile) as error:
            self.text.setPlainText(f"KMZ konnte nicht als ZIP-Archiv gelesen werden:\n{error}")
        self.files.currentItemChanged.connect(self._show_file)
        self.structure.currentItemChanged.connect(self._show_properties)
        if self.files.topLevelItemCount():
            self.files.setCurrentItem(self.files.topLevelItem(0))
        self.structure.expandToDepth(2)

    @staticmethod
    def _tag(value: str) -> str:
        return value.rsplit("}", 1)[-1]

    def _add_archive_file(self, name: str, size: int) -> None:
        parent: QTreeWidgetItem | QTreeWidget = self.files
        parts = Path(name).parts
        for index, part in enumerate(parts):
            is_file = index == len(parts) - 1
            child = next((parent.child(row) for row in range(parent.childCount()) if parent.child(row).text(0) == part), None) if isinstance(parent, QTreeWidgetItem) else next((parent.topLevelItem(row) for row in range(parent.topLevelItemCount()) if parent.topLevelItem(row).text(0) == part), None)
            if child is None:
                child = QTreeWidgetItem(parent, [part, f"{size:,} B" if is_file else ""])
            parent = child
        parent.setData(0, Qt.ItemDataRole.UserRole, name)

    def _add_xml_structure(self, name: str, data: bytes) -> None:
        if not name.lower().endswith((".kml", ".wpml", ".xml")):
            return
        root_item = QTreeWidgetItem(self.structure, [name])
        root_item.setData(0, Qt.ItemDataRole.UserRole, [("Archivdatei", name), ("Größe", f"{len(data):,} B")])
        try:
            self._add_element(root_item, ET.fromstring(data), ())
        except ET.ParseError as error:
            QTreeWidgetItem(root_item, [f"XML konnte nicht gelesen werden: {error}"])

    def _add_element(self, parent: QTreeWidgetItem, element: ET.Element, path: tuple[str, ...]) -> None:
        tag = self._tag(element.tag)
        index = next((node.text.strip() for node in element.iter() if self._tag(node.tag) == "index" and node.text and node.text.strip()), None)
        label = f"Wegpunkt {index} · {tag}" if tag == "Placemark" and index is not None else tag
        item = QTreeWidgetItem(parent, [label])
        item.setData(0, Qt.ItemDataRole.UserRole, self._element_properties(element, path + (tag,)))
        for child in element:
            self._add_element(item, child, path + (tag,))

    def _element_properties(self, element: ET.Element, path: tuple[str, ...]) -> list[tuple[str, str]]:
        properties = [("Element", self._tag(element.tag))]
        properties.extend((f"@{self._tag(key)}", value) for key, value in element.attrib.items())
        text = (element.text or "").strip()
        if text:
            properties.append(("Wert", text))
        # A Placemark is a waypoint in DJI WPML.  Its leaf nodes are flattened
        # here so a single click exposes all waypoint-specific settings.
        if self._tag(element.tag) == "Placemark":
            for leaf in element.iter():
                if leaf is element or list(leaf) or not (leaf.text or "").strip():
                    continue
                properties.append((self._tag(leaf.tag), (leaf.text or "").strip()))
                properties.extend((f"{self._tag(leaf.tag)}.@{self._tag(key)}", value) for key, value in leaf.attrib.items())
        properties.append(("Unterelemente", str(len(element))))
        return properties

    def _show_properties(self, item: QTreeWidgetItem | None) -> None:
        values = item.data(0, Qt.ItemDataRole.UserRole) if item is not None else None
        self.properties.setRowCount(0)
        if not values:
            return
        for key, value in values:
            row = self.properties.rowCount()
            self.properties.insertRow(row)
            self.properties.setItem(row, 0, QTableWidgetItem(str(key)))
            self.properties.setItem(row, 1, QTableWidgetItem(str(value)))

    def _show_file(self, item: QTreeWidgetItem | None) -> None:
        if item is None:
            return
        name = item.data(0, Qt.ItemDataRole.UserRole)
        if not name:
            self.text.setPlainText("Ordner – bitte eine Datei auswählen.")
            return
        data = self._contents[name]
        if name.lower().endswith((".kml", ".wpml", ".xml")):
            try:
                self.text.setPlainText(xml.dom.minidom.parseString(data).toprettyxml(indent="  "))
            except Exception:
                self.text.setPlainText(data.decode("utf-8", errors="replace"))
        else:
            self.text.setPlainText(f"Binärdatei: {name}\n{len(data):,} Bytes\n\nKeine Textvorschau verfügbar.")


class RcRemoteTool(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RC Remote Tool – ACMP")
        self.resize(1250, 760)
        self._manager = RC2Manager()
        self._missions: dict[str, RC2Mission] = {}
        self._downloads: dict[str, Path] = {}
        self._tempdir = tempfile.TemporaryDirectory(prefix="acmp_rc_debug_")
        self._build_ui()

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        controls = QHBoxLayout()
        scan = QPushButton("RC-Missionen herunterladen")
        scan.setToolTip("Liest die auf dem verbundenen DJI RC 2 vorhandenen Missions-Slots ein.")
        scan.clicked.connect(self.scan)
        show = QPushButton("Ausgewählte Mission anzeigen")
        show.clicked.connect(self.show_selected)
        debug = QPushButton("Ausgewählte KMZ debuggen")
        debug.clicked.connect(self.debug_selected)
        controls.addWidget(scan)
        controls.addWidget(show)
        controls.addWidget(debug)
        controls.addStretch(1)
        layout.addLayout(controls)
        layout.addWidget(QLabel("RC-Missionen (eine Zeile auswählen; Anzeigen ersetzt immer die vorherige Kartenmission):"))
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["UUID", "KMZ-Datei", "Geändert", "Größe", "Gerät"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 280)
        self.table.setColumnWidth(1, 190)
        layout.addWidget(self.table, 1)
        layout.addWidget(QLabel("Karte – OpenStreetMap; beim Anzeigen wird auf die vollständige Mission gezoomt."))
        self.map = QWebEngineView()
        self.map.setMinimumHeight(330)
        self.map.setHtml(MAP_HTML, QUrl("https://acmp.local/"))
        layout.addWidget(self.map, 2)
        self.setStatusBar(QStatusBar())
        action = QAction("RC-Missionen herunterladen", self, triggered=self.scan)
        action.setShortcut("F5")
        self.addAction(action)

    def _selected(self) -> RC2Mission | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "Keine Mission ausgewählt", "Bitte wähle eine RC-Mission aus der Tabelle aus.")
            return None
        return self._missions.get(self.table.item(rows[0].row(), 0).text())

    def scan(self) -> None:
        self.statusBar().showMessage("Suche RC2-Missionsslots …")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            result = self._manager.find_waypoint_missions()
        finally:
            QApplication.restoreOverrideCursor()
        if result.error:
            QMessageBox.warning(self, "RC2-Scan fehlgeschlagen", result.error)
            self.statusBar().showMessage(result.error, 8000)
            return
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self._missions = {mission.uuid: mission for mission in result.missions}
        for mission in result.missions:
            row = self.table.rowCount()
            self.table.insertRow(row)
            size = f"{mission.size_bytes:,} B" if mission.size_bytes else "—"
            for column, value in enumerate((mission.uuid, mission.kmz_name, mission.modified or "—", size, mission.device_name)):
                self.table.setItem(row, column, QTableWidgetItem(str(value)))
        self.table.setSortingEnabled(True)
        device = ", ".join(result.devices) or "kein RC2"
        self.statusBar().showMessage(f"{len(result.missions)} Mission(en) auf {device} gefunden.", 8000)

    def _download(self, mission: RC2Mission) -> Path | None:
        cached = self._downloads.get(mission.uuid)
        if cached and cached.exists():
            return cached
        destination = Path(self._tempdir.name) / f"{mission.uuid}.kmz"
        self.statusBar().showMessage(f"Lade {mission.kmz_name} vom RC2 herunter …")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self._manager.download_mission(mission, destination)
        except OSError as error:
            QMessageBox.warning(self, "Download fehlgeschlagen", str(error))
            return None
        finally:
            QApplication.restoreOverrideCursor()
        self._downloads[mission.uuid] = destination
        return destination

    def show_selected(self) -> None:
        mission = self._selected()
        if mission is None:
            return
        path = self._download(mission)
        if path is None:
            return
        try:
            route = read_waypoint_path(path)
        except (OSError, ValueError, zipfile.BadZipFile) as error:
            QMessageBox.warning(self, "Mission nicht lesbar", f"Die KMZ wurde heruntergeladen, aber die Wegpunkte konnten nicht gelesen werden:\n\n{error}")
            return
        label = f"{mission.uuid} · {len(route)} Wegpunkte"
        self.map.page().runJavaScript(f"showMission({json.dumps(route)}, {json.dumps(label)});")
        self.statusBar().showMessage(f"{label} wird angezeigt.", 8000)

    def debug_selected(self) -> None:
        mission = self._selected()
        if mission is None:
            return
        path = self._download(mission)
        if path is not None:
            KmzInspector(path, self).exec()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("RC Remote Tool")
    window = RcRemoteTool()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
