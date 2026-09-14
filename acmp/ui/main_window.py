"""ACMP: Interaktive Karte zum Zeichnen eines Flugbereich-Polygons.

Die Karte basiert auf Leaflet/OpenStreetMap.  Es werden keine Zugangsschlüssel
benötigt; Satellitenbilder kommen von Esri World Imagery.
"""

from __future__ import annotations

import json
import math
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import escape
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from PySide6.QtCore import QSettings, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEnginePermission
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFrame,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QInputDialog,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QListWidget,
    QTextEdit,
    QTextBrowser,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

UI_EN = {
    "Datei": "File", "Einstellungen": "Settings", "Neu": "New", "Öffnen …": "Open …", "Speichern": "Save", "Speichern unter …": "Save as …",
    "Preset speichern": "Save preset", "Preset laden": "Load preset", "Sprache …": "Language …", "Info": "Info",
    "Gebiet auswählen": "Select area", "Adresse oder Ort suchen": "Search address or place",
    "Mein Standort": "My location", "Suchen": "Search", "Kartenansicht": "Map view",
    "Karte": "Map", "Satellit": "Satellite", "Polygon": "Polygon", "Rechteck": "Rectangle", "Kreis": "Circle", "Letzten Punkt rückgängig": "Undo last point",
    "Alles löschen": "Clear all", "Sperrgebiete": "No-fly zones", "Sperrgebiet zeichnen": "Draw no-fly zone",
    "Aktuelles Sperrgebiet verwerfen": "Discard current no-fly zone", "Ausgewähltes Sperrgebiet löschen": "Delete selected no-fly zone",
    "Fläche: —": "Area: —", "Koordinaten der aktiven Zone (Lat, Lon)": "Active-area coordinates (Lat, Lon)",
    "Koordinaten kopieren": "Copy coordinates", "Fluggebiet planen": "Plan flight area", "Flugeinstellungen": "Flight settings",
    "Flughöhe:": "Altitude:", "Geschwindigkeit:": "Speed:", "Bahnabstand:": "Path spacing:",
    "Richtungsvorgabe:": "Direction mode:", "Bahnrichtung:": "Path direction:", "Routenmodus:": "Route mode:",
    "Stützpunkt-Abstand:": "Support-point spacing:", "Kamera & Photogrammetrie": "Camera & photogrammetry",
    "Seitliche Überlappung:": "Side overlap:", "Vorwärtsüberlappung:": "Forward overlap:", "Foto alle (Distanz):": "Photo every (distance):",
    "Kamera-Neigung:": "Gimbal pitch:", "Aktion:": "Action:", "Missionsgrenze": "Mission limits",
    "Max. Wegpunkte:": "Max. waypoints:", "Max. Flugzeit / Mission:": "Max. flight time / mission:", "Aufteilung auf Missionen:": "Split across missions:",
    "Bei Flugende:": "At flight end:", "Bei Signalverlust:": "On signal loss:",
    "Außerhalb des Flugbereichs:": "Outside flight area:", "Bei Sperrgebieten:": "For no-fly zones:",
    "Route generieren und auf Karte zeigen": "Generate route and show on map", "Route verstecken": "Hide route", "Route zeigen": "Show route",
    "Eine Mission erzwingen (Grenzen überschreiten)": "Force one mission (exceed limits)", "Routenanzeige löschen": "Clear route display",
    "Exportieren & Speichern": "Export & save", "KMZ-Datei speichern": "Save KMZ file", "KMZ-Dateiname / Missionsname": "KMZ filename / mission name",
    "KMZ-Datei speichern …": "Save KMZ file …", "Vorschaubild speichern …": "Save preview image …", "Text im Vorschaubild": "Preview-image text",
    "Vorschaubild mit Name speichern …": "Save preview image with name …", "Exportieren": "Export",
    "Erzeugt ein DJI-WPML-KMZ mit <code>template.kml</code> und <code>waylines.wpml</code>.": "Creates a DJI WPML KMZ with <code>template.kml</code> and <code>waylines.wpml</code>.",
    "Missionsname": "Mission name",
    "West → Ost (0°)": "West → East (0°)", "Ost → West (180°)": "East → West (180°)",
    "Süd → Nord (90°)": "South → North (90°)", "Nord → Süd (270°)": "North → South (270°)",
    "Eigene Gradzahl": "Custom angle", "Optimal (längste Kante)": "Optimal (longest edge)", "Optimal (längste Kante, umgekehrt)": "Optimal (longest edge, reversed)", "Optimal (kürzeste Flugzeit)": "Optimal (shortest flight time)",
    "Standard (DJI-Näherung: glatte Kurven)": "Standard (DJI approximation: smooth curves)", "WPML gerade / Punktstopp (nicht garantiert)": "WPML straight / point stop (not guaranteed)",
    "Stützpunkte für geradere Bahnen": "Support points for straighter paths", "Overshooting": "Overshooting",
    "Geschätzte DJI-Flugbahn anzeigen (Centripetal-Catmull-Rom; Näherung)": "Show estimated DJI flight path (centripetal Catmull-Rom; approximation)", "Foto bei jedem Wegpunkt": "Photo at every waypoint",
    "Foto nach Distanzintervall": "Photo at distance interval", "Keine Aktion": "No action", "2 s schweben": "Hover 2 s", "Was ist hier?": "What's here?",
    "Konflikte …": "Conflicts …",
    "UAS-Geozonen": "UAS geozones", "UAS-Geozonen (Deutschland)": "UAS geozones (Germany)",
    "Lokale Bestimmungen": "Local rules", "Lokale Bestimmungen (Deutschland)": "Local rules (Germany)",
    "Flugbereich": "Flight area", "Auf Flugbereich zoomen": "Zoom to flight area",
    "Routenparameter": "Route parameters",
    "Außerhalb erlaubt": "Outside flight area allowed", "Im Flugbereich bleiben (exkl. Overshooting)": "Remain inside flight area (except Overshooting)",
    "Sperrgebiet umfliegen": "Avoid no-fly zones", "Sperrgebiet durchfliegen": "Allow flight through no-fly zones",
    "Maximal ausnutzen": "Use maximum", "Gleichmäßig verteilen": "Distribute evenly",
    "Rückkehr zum Startpunkt (Home)": "Return to home", "Schweben am letzten Wegpunkt": "Hover at last waypoint",
    "Landen am letzten Wegpunkt": "Land at last waypoint", "Zum ersten Wegpunkt": "Go to first waypoint", "Schweben": "Hover", "Landen": "Land",
    "Noch keine Route generiert.": "No route generated yet.", "Punkte: 0": "Points: 0",
    "Aktive Zone: noch nicht gezeichnet · Sperrgebiete: 0": "Active area: not drawn · no-fly zones: 0",
    "Zeichne mindestens drei Punkte auf der Karte.": "Draw at least three points on the map.",
    "Vorschaubilder – experimentell": "Preview images – experimental",
    "Die Bilddateien werden erstellt, aber DJI Fly übernimmt externe Vorschaubilder möglicherweise nicht.": "Image files are created, but DJI Fly may not use external preview images.",
    "Vorschauformat: JPEG, 400 × 300 Pixel": "Preview format: JPEG, 400 × 300 pixels",
    "Offizieller dipul/DFS-Kartenlayer, nur zur Orientierung.": "Official dipul/DFS map layer, for orientation only.",
    "Zuletzt erkannte Überschneidungen erneut prüfen und bearbeiten.": "Review and edit the most recently detected conflicts.",
    "BfN-Schutzgebiete als Hinweis – keine pauschalen Flugverbote.": "BfN protected areas as hints – not blanket no-fly zones.",
    "Hinweis zur rechtlichen Einordnung": "Legal-information notice",
}
UI_DE = {english: german for german, english in UI_EN.items()}


# Die Namen entsprechen den Layern des öffentlichen dipul/DFS-WMS.  Die
# Abfrage ist absichtlich nur ein Hinweis: WMS GetFeatureInfo liefert keine
# rechtsverbindliche Freigabe und kann bei kleinen Zonen Treffer übersehen.
GEOZONE_LAYERS = (
    "bahnanlagen,behoerden,bundesautobahnen,bundesstrassen,ffh-gebiete,"
    "flugbeschraenkungsgebiete,flughaefen,flugplaetze,industrieanlagen,"
    "kontrollzonen,krankenhaeuser,militaerische_anlagen,nationalparks,"
    "naturschutzgebiete,polizei,temporaere_betriebseinschraenkungen,"
    "vogelschutzgebiete,wohngrundstuecke"
)
from shapely.geometry import LineString, Polygon, shape, mapping
from shapely.ops import unary_union
GEOZONE_LABELS = {
    "bahnanlagen": "Bahnanlagen", "behoerden": "Behörden",
    "bundesautobahnen": "Bundesautobahnen", "bundesstrassen": "Bundesstraßen",
    "ffh-gebiete": "FFH-Gebiete", "flugbeschraenkungsgebiete": "Flugbeschränkungsgebiete",
    "flughaefen": "Flughäfen", "flugplaetze": "Flugplätze",
    "industrieanlagen": "Industrieanlagen", "kontrollzonen": "Kontrollzonen",
    "krankenhaeuser": "Krankenhäuser", "militaerische_anlagen": "Militärische Anlagen",
    "nationalparks": "Nationalparks", "naturschutzgebiete": "Naturschutzgebiete",
    "polizei": "Polizei", "temporaere_betriebseinschraenkungen": "Temporäre Betriebseinschränkungen",
    "vogelschutzgebiete": "Vogelschutzgebiete", "wohngrundstuecke": "Wohngrundstücke",
}
LOCAL_RULE_LAYERS = {
    "Landschaftsschutzgebiete": "Landschaftsschutzgebiet",
    "Naturparke": "Naturpark",
    "Biosphaerenreservate": "Biosphärenreservat",
    "Nationale_Naturmonumente": "Nationales Naturmonument",
}


def canonical_ui_text(value: str) -> str:
    return UI_DE.get(value, value)


MAP_HTML = r"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>html,body,#map{height:100%;width:100%;margin:0}.leaflet-container{font-family:Segoe UI,Arial,sans-serif}</style>
</head><body><div id="map"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const normal = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom: 20, attribution:'© OpenStreetMap-Mitwirkende'});
const satellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {maxZoom: 19, attribution:'Tiles © Esri'});
const geozones = L.tileLayer.wms('https://uas-betrieb.de/geoservices/dipul/wms?', {
  layers:'bahnanlagen,behoerden,bundesautobahnen,bundesstrassen,ffh-gebiete,flugbeschraenkungsgebiete,flughaefen,flugplaetze,industrieanlagen,kontrollzonen,krankenhaeuser,militaerische_anlagen,nationalparks,naturschutzgebiete,polizei,temporaere_betriebseinschraenkungen,vogelschutzgebiete,wohngrundstuecke',
  format:'image/png',transparent:true,version:'1.3.0',opacity:.85,attribution:'© DFS/dipul'
});
const map = L.map('map', {zoomControl:true, layers:[normal]}).setView([51.1657, 10.4515], 6);
map.createPane('localRulesPane');
map.getPane('localRulesPane').style.zIndex=350;
map.getPane('localRulesPane').style.filter='hue-rotate(35deg) saturate(.65)';
const localRules = L.tileLayer.wms('https://geodienste.bfn.de/ogc/wms/schutzgebiet?', {
  layers:'Landschaftsschutzgebiete,Naturparke,Biosphaerenreservate,Nationale_Naturmonumente',
  format:'image/png',transparent:true,version:'1.3.0',opacity:.35,pane:'localRulesPane',attribution:'© BfN Schutzgebiete'
});
L.control.layers({'Karte':normal, 'Satellit':satellite}, null, {position:'topleft'}).addTo(map);
L.control.scale({position:'bottomleft', metric:true, imperial:false, maxWidth:140}).addTo(map);
let points = [], polygon = null, preview = null, shapePreview = null, shapeStart = null, markers = [], drawMode = 'none';
let noFlyZones = [], activeNoFly = [], selectedNoFly = -1, noFlyLayer = L.layerGroup().addTo(map);
let missionLayer = L.layerGroup().addTo(map);
let overshootZoneLayer = L.layerGroup().addTo(map);
let geozoneConflictLayer = L.layerGroup().addTo(map);
function emit(){ console.log('ACMP_POLYGON:' + JSON.stringify(points)); }
function emitNoFly(){ console.log('ACMP_NO_FLY:' + JSON.stringify(noFlyZones)); }
function clearVisuals(){
  if(polygon) map.removeLayer(polygon); if(preview) map.removeLayer(preview);
  markers.forEach(m=>map.removeLayer(m)); polygon=null; preview=null; markers=[];
}
function redraw(silent=false){
  clearVisuals();
  points.forEach((p,i)=>{ markers.push(L.circleMarker(p,{radius:6,color:'#1064b8',fillColor:'#fff',fillOpacity:1,weight:3}).bindTooltip(String(i+1),{permanent:true,direction:'top',offset:[0,-8]}).addTo(map)); });
  if(points.length >= 3) polygon=L.polygon(points,{color:'#0878d1',weight:3,fillColor:'#39a9ff',fillOpacity:.20}).addTo(map);
  else if(points.length === 2) polygon=L.polyline(points,{color:'#0878d1',weight:3}).addTo(map);
  if(!silent) emit();
}
function redrawNoFly(){
  noFlyLayer.clearLayers();
  noFlyZones.forEach((zone,index)=>{
    const selected=index===selectedNoFly;
    L.polygon(zone, selected
      ? {color:'#ff8c00',weight:5,fillColor:'#ffb000',fillOpacity:.42,dashArray:'9 5'}
      : {color:'#c92525',weight:3,fillColor:'#e53935',fillOpacity:.28}
    ).bindTooltip(`Sperrgebiet ${index+1}`,{sticky:true}).addTo(noFlyLayer);
  });
  if(activeNoFly.length >= 3) L.polygon(activeNoFly,{color:'#c92525',weight:3,dashArray:'7 6',fillColor:'#e53935',fillOpacity:.18}).addTo(noFlyLayer);
  else if(activeNoFly.length) L.polyline(activeNoFly,{color:'#c92525',weight:3,dashArray:'7 6'}).addTo(noFlyLayer);
}
map.on('click', e=>{
  if(drawMode==='area'){ points.push([e.latlng.lat,e.latlng.lng]); redraw(); }
  if(drawMode==='nofly'){ activeNoFly.push([e.latlng.lat,e.latlng.lng]); redrawNoFly(); }
  if(drawMode==='inspect'){ drawMode='none'; map.getContainer().style.cursor=''; console.log('ACMP_INSPECT:' + JSON.stringify([e.latlng.lat,e.latlng.lng])); }
  if(drawMode==='localinspect'){ drawMode='none'; map.getContainer().style.cursor=''; console.log('ACMP_LOCAL_INSPECT:' + JSON.stringify([e.latlng.lat,e.latlng.lng])); }
});
map.on('contextmenu', e=>{ L.DomEvent.preventDefault(e.originalEvent); });
map.on('mousedown', e=>{
  if(drawMode==='rectangle' || drawMode==='circle'){
    shapeStart=e.latlng; map.dragging.disable();
    if(shapePreview) map.removeLayer(shapePreview);
  }
});
map.on('mousemove', e=>{
  if((drawMode==='rectangle' || drawMode==='circle') && shapeStart){
    if(shapePreview) map.removeLayer(shapePreview);
    shapePreview=drawMode==='rectangle'
      ? L.rectangle(L.latLngBounds(shapeStart,e.latlng),{color:'#0878d1',weight:3,fillOpacity:.16,dashArray:'6 6'}).addTo(map)
      : L.circle(shapeStart,{radius:map.distance(shapeStart,e.latlng),color:'#0878d1',weight:3,fillOpacity:.16,dashArray:'6 6'}).addTo(map);
    return;
  }
  const active=drawMode==='area' ? points : activeNoFly;
  if(drawMode==='none' || !active.length) return;
  if(preview) map.removeLayer(preview);
  const color=drawMode==='nofly' ? '#c92525' : '#0878d1';
  preview=L.polyline([...active,[e.latlng.lat,e.latlng.lng]],{color:color,dashArray:'6 7',weight:2}).addTo(map);
});
map.on('mouseup', e=>{
  if(!shapeStart || (drawMode!=='rectangle' && drawMode!=='circle')) return;
  const start=shapeStart, kind=drawMode; shapeStart=null; map.dragging.enable();
  if(shapePreview){map.removeLayer(shapePreview);shapePreview=null;}
  if(kind==='rectangle'){
    const bounds=L.latLngBounds(start,e.latlng), sw=bounds.getSouthWest(), ne=bounds.getNorthEast();
    points=[[sw.lat,sw.lng],[sw.lat,ne.lng],[ne.lat,ne.lng],[ne.lat,sw.lng]];
  } else {
    const radius=map.distance(start,e.latlng), count=64;
    points=Array.from({length:count},(_,i)=>{
      const radians=2*Math.PI*i/count;
      return [start.lat+(radius*Math.cos(radians))/111132.92, start.lng+(radius*Math.sin(radians))/(111319.49*Math.cos(start.lat*Math.PI/180))];
    });
  }
  drawMode='none'; redraw(); console.log('ACMP_SHAPE_DONE');
});
function endPreview(){ if(preview){map.removeLayer(preview);preview=null;} }
function setDrawing(value){ drawMode=value?'area':'none'; map.getContainer().style.cursor=value?'crosshair':''; endPreview(); }
function setShapeDrawing(kind){ drawMode=kind; map.getContainer().style.cursor='crosshair'; endPreview(); }
function setNoFlyDrawing(value){ drawMode=value?'nofly':'none'; map.getContainer().style.cursor=value?'crosshair':''; endPreview(); if(!value) finishNoFly(); }
function setInspect(value){ drawMode=value?'inspect':'none'; map.getContainer().style.cursor=value?'crosshair':''; endPreview(); }
function setLocalInspect(value){ drawMode=value?'localinspect':'none'; map.getContainer().style.cursor=value?'crosshair':''; endPreview(); }
function finishNoFly(){ if(activeNoFly.length >= 3){noFlyZones.push(activeNoFly);emitNoFly();} activeNoFly=[];redrawNoFly(); }
function cancelNoFly(){ activeNoFly=[];redrawNoFly(); }
function deleteNoFly(index){ if(index>=0 && index<noFlyZones.length){noFlyZones.splice(index,1);redrawNoFly();emitNoFly();} }
function selectNoFly(index){ selectedNoFly=index; redrawNoFly(); }
function clearNoFly(){ noFlyZones=[];activeNoFly=[];redrawNoFly();emitNoFly(); }
function clearAll(){ points=[]; noFlyZones=[]; activeNoFly=[]; redraw(); redrawNoFly(); emitNoFly(); }
function setProjectGeometry(newPoints,newZones){
  points=Array.isArray(newPoints)?newPoints:[];
  noFlyZones=Array.isArray(newZones)?newZones:[];
  activeNoFly=[]; selectedNoFly=-1; redraw(true); redrawNoFly();
}
function undo(){ if(points.length){points.pop();redraw();} }
function clearPolygon(){ points=[]; redraw(); }
function zoomToArea(){ const layers=[]; if(points.length) layers.push(L.polygon(points)); noFlyZones.forEach(z=>layers.push(L.polygon(z))); if(layers.length) map.fitBounds(L.featureGroup(layers).getBounds().pad(.12)); }
function setBase(name){ if(name==='satellite'){map.removeLayer(normal);satellite.addTo(map);}else{map.removeLayer(satellite);normal.addTo(map);} }
function setGeozones(value){ if(value){geozones.addTo(map);}else{map.removeLayer(geozones);} }
function setGeozoneOpacity(value){ geozones.setOpacity(value/100); }
function setLocalRules(value){ if(value){localRules.addTo(map);}else{map.removeLayer(localRules);} }
function setLocalRulesOpacity(value){ localRules.setOpacity(value/100); }
function clearGeozoneConflicts(){ geozoneConflictLayer.clearLayers(); }
function showGeozoneConflicts(features){
  clearGeozoneConflicts();
  L.geoJSON({type:'FeatureCollection',features:features},{
    style:feature=>feature.properties._acmp_decision==='block'
      ? {color:'#c92525',weight:3,fillColor:'#e53935',fillOpacity:.34,dashArray:'7 5'}
      : {color:'#ff00b8',weight:3,fillColor:'#ff3dbf',fillOpacity:.30,dashArray:'7 5'},
    onEachFeature:(feature,layer)=>layer.bindTooltip(`UAS-Geozone: ${feature.properties._acmp_label || 'Unbekannt'}`,{sticky:true})
  }).addTo(geozoneConflictLayer);
}
function goTo(lat,lng,zoom){ map.setView([lat,lng],zoom || 16); L.marker([lat,lng]).addTo(map).bindPopup('Suchergebnis').openPopup(); }
function clearMission(){ missionLayer.clearLayers(); overshootZoneLayer.clearLayers(); }
function setMissionVisible(value){ if(value){ if(!map.hasLayer(missionLayer)) missionLayer.addTo(map); }else if(map.hasLayer(missionLayer)){ map.removeLayer(missionLayer); } }
function showMission(route){
  showMissions([route]);
}
function showMissions(missions, summaries=[], estimatedPaths=[], overshootPaths=[], overshootZone=null){
  clearMission(); let globalIndex=0; const colors=['#d13c10','#7b3fb2','#087f5b','#9a6700','#1261a0'];
  if(overshootZone) L.geoJSON(overshootZone,{style:{color:'#00bcd4',weight:2,fillColor:'#00c8e8',fillOpacity:.18,dashArray:'8 5'},onEachFeature:(_feature,layer)=>layer.bindTooltip('Erweiterte Flugzone für Overshooting (inkl. Sicherheitszugabe)',{sticky:true})}).addTo(overshootZoneLayer);
  overshootPaths.forEach(path=>{
    if(path && path.length>1) L.polyline(path,{color:'#00bcd4',weight:6,opacity:.38}).bindTooltip('Erweiterter Flugbereich / Overshoot',{sticky:true}).addTo(missionLayer);
  });
  const allPoints=missions.flat();
  const maxLat=Math.max(...allPoints.map(p=>p[0])), maxLon=Math.max(...allPoints.map(p=>p[1]));
  const latSpan=Math.max(...allPoints.map(p=>p[0]))-Math.min(...allPoints.map(p=>p[0]));
  const lonSpan=Math.max(...allPoints.map(p=>p[1]))-Math.min(...allPoints.map(p=>p[1]));
  missions.forEach((route,missionIndex)=>{ if(!route || route.length < 2) return; const color=colors[missionIndex%colors.length];
  const estimated=estimatedPaths[missionIndex];
  L.polyline(route,estimated ? {color:'#667085',weight:2,opacity:.7,dashArray:'7 7'} : {color:color,weight:3,opacity:.9}).addTo(missionLayer);
  if(estimated && estimated.length>1) L.polyline(estimated,{color:color,weight:4,opacity:.92}).bindTooltip('Geschätzte DJI-Flugbahn (Centripetal-Catmull-Rom-Näherung)',{sticky:true}).addTo(missionLayer);
  const center=[maxLat-missionIndex*Math.max(latSpan*.10,.00008),maxLon+Math.max(lonSpan*.08,.00015)];
  const summary=summaries[missionIndex] || `Mission ${missionIndex+1} · ${route.length} WP`;
  const label=L.divIcon({className:'',html:`<div style="background:white;color:${color};border:2px solid ${color};border-radius:5px;padding:3px 6px;white-space:nowrap;font:600 12px Segoe UI,Arial;box-shadow:0 1px 4px #555">${summary}</div>`,iconSize:null,iconAnchor:[0,0]});
  L.marker(center,{icon:label,interactive:false}).addTo(missionLayer);
  route.forEach((p,i)=>{
    globalIndex++;
    const icon=L.divIcon({className:'',html:`<div style="background:${color};color:white;border:2px solid white;border-radius:50%;width:22px;height:22px;line-height:22px;text-align:center;font-size:11px;font-weight:bold;box-shadow:0 1px 3px #444">${missionIndex+1}.${i+1}</div>`,iconSize:[28,22],iconAnchor:[14,11]});
    L.marker(p,{icon:icon,interactive:false}).addTo(missionLayer);
    if(i < route.length-1){
      const q=route[i+1], mid=[(p[0]+q[0])/2,(p[1]+q[1])/2];
      const dx=q[1]-p[1], dy=q[0]-p[0], rotation=Math.atan2(dx,dy)*180/Math.PI;
      const arrow=L.divIcon({className:'',html:`<div style="color:${color};font-size:20px;font-weight:bold;transform:rotate(${rotation}deg);text-shadow:0 0 2px white">▲</div>`,iconSize:[20,20],iconAnchor:[10,10]});
      L.marker(mid,{icon:arrow,interactive:false}).addTo(missionLayer);
    }
  }); });
}
</script></body></html>"""


class MapPage(QWebEnginePage):
    polygon_changed = Signal(list)
    no_fly_changed = Signal(list)
    shape_completed = Signal()
    inspection_requested = Signal(list)
    local_inspection_requested = Signal(list)

    def javaScriptConsoleMessage(self, level, message, line_number, source_id):
        if message.startswith("ACMP_POLYGON:"):
            try:
                self.polygon_changed.emit(json.loads(message.removeprefix("ACMP_POLYGON:")))
            except json.JSONDecodeError:
                pass
        elif message.startswith("ACMP_NO_FLY:"):
            try:
                self.no_fly_changed.emit(json.loads(message.removeprefix("ACMP_NO_FLY:")))
            except json.JSONDecodeError:
                pass
        elif message == "ACMP_SHAPE_DONE":
            self.shape_completed.emit()
        elif message.startswith("ACMP_INSPECT:"):
            try:
                self.inspection_requested.emit(json.loads(message.removeprefix("ACMP_INSPECT:")))
            except json.JSONDecodeError:
                pass
        elif message.startswith("ACMP_LOCAL_INSPECT:"):
            try:
                self.local_inspection_requested.emit(json.loads(message.removeprefix("ACMP_LOCAL_INSPECT:")))
            except json.JSONDecodeError:
                pass
        super().javaScriptConsoleMessage(level, message, line_number, source_id)


class MapView(QWebEngineView):
    """Unterdrückt das Browser-Kontextmenü innerhalb der Karte."""

    def contextMenuEvent(self, event):
        event.accept()


from acmp.services.kmz_exporter import build_dji_kmz
from acmp.services.route_planner import (
    add_overshoot_turns, centripetal_catmull_rom_route, count_direction_changes, densify_route, estimated_route_seconds, generate_lawnmower_route,
    optimal_direction_deg, plan_missions, polygon_area_m2, route_length_m, shortest_route_direction_deg,
)

class MainWindow(QMainWindow):
    geozone_check_finished = Signal(int, object)
    context_geozone_check_finished = Signal(object)
    local_rules_check_finished = Signal(object)

    def __init__(self):
        super().__init__()
        self.points: list[list[float]] = []
        self.no_fly_zones: list[list[list[float]]] = []
        self.no_fly_names: list[str] = []
        self.current_project_path: Path | None = None
        self.preset_dir = Path(__file__).resolve().parents[2] / "presets"
        self.generated_route: list[list[float]] = []
        self.generated_missions: list[list[list[float]]] = []
        self.overshoot_paths: list[list[list[float]]] = []
        self.reduced_support_points = False
        self.keep_support_route_inside = False
        self.reduced_overshoot_points = False
        self.force_single_mission = False
        self._geozone_check_id = 0
        self._last_geozone_features: list[dict] = []
        self._geozone_review_decisions: dict[str, str] = {}
        self._geozone_review_base_zones: list = []
        self._geozone_review_base_names: list[str] = []
        self._geozone_review_dialog: QDialog | None = None
        self.geozone_check_finished.connect(self._show_geozone_check_result)
        self.context_geozone_check_finished.connect(self._show_context_geozone_result)
        self.local_rules_check_finished.connect(self._show_local_rules_result)
        self.settings = QSettings("ACMP", "Mission Planner")
        self.ui_language = self.settings.value("ui_language", "de")
        self.geozone_zone_method = self.settings.value("geozone_zone_method", "global")
        self.setWindowTitle("ACMP – Aerial Capture Mission Planner")
        self.resize(1500, 900)
        self._build_ui()

    def _build_ui(self):
        menu_bar = self.menuBar()
        self.file_menu = menu_bar.addMenu("&Datei")
        file_menu = self.file_menu
        new_project = QAction("Neu", self)
        new_project.setShortcut("Ctrl+N")
        new_project.triggered.connect(self.new_project)
        file_menu.addAction(new_project)
        open_project = QAction("Öffnen …", self)
        open_project.setShortcut("Ctrl+O")
        open_project.triggered.connect(self.open_project)
        file_menu.addAction(open_project)
        save_current = QAction("Speichern", self)
        save_current.setShortcut("Ctrl+S")
        save_current.triggered.connect(self.save_project)
        file_menu.addAction(save_current)
        save_project = QAction("Speichern unter …", self)
        save_project.setShortcut("Ctrl+Shift+S")
        save_project.triggered.connect(self.save_project_as)
        file_menu.addAction(save_project)
        file_menu.addSeparator()
        save_preset = QAction("Preset speichern", self)
        save_preset.triggered.connect(self.save_preset)
        file_menu.addAction(save_preset)
        load_preset = QAction("Preset laden", self)
        load_preset.triggered.connect(self.load_preset)
        file_menu.addAction(load_preset)

        self.settings_action = QAction("Einstellungen", self)
        self.settings_action.triggered.connect(self.open_settings_dialog)
        menu_bar.addAction(self.settings_action)
        about = QAction("Info", self)
        about.triggered.connect(self._show_about)
        menu_bar.addAction(about)

        self.page = MapPage(self)
        self.page.polygon_changed.connect(self._polygon_changed)
        self.page.no_fly_changed.connect(self._no_fly_changed)
        self.page.shape_completed.connect(self._shape_completed)
        self.page.inspection_requested.connect(self._inspect_map_point)
        self.page.local_inspection_requested.connect(self._inspect_local_rules_point)
        self.page.permissionRequested.connect(self._handle_web_permission)
        self.map_view = MapView()
        self.map_view.setPage(self.page)
        self.map_view.loadFinished.connect(
            lambda _ok: self._apply_saved_map_opacities()
        )
        self.map_view.setHtml(MAP_HTML, QUrl("https://acmp.local/"))

        sidebar = self._build_sidebar()
        splitter = QSplitter()
        splitter.addWidget(self.map_view)
        splitter.addWidget(sidebar)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([1020, 480])
        self.setCentralWidget(splitter)
        self._apply_language()

    def _build_sidebar(self):
        side = QFrame()
        side.setMinimumWidth(360)
        side.setMaximumWidth(540)
        layout = QVBoxLayout(side)
        layout.setContentsMargins(8, 8, 8, 8)
        tabs = QTabWidget()
        layout.addWidget(tabs)

        # Tab 1: Gebiet erfassen
        capture = QWidget()
        capture_layout = QVBoxLayout(capture)
        capture_layout.setContentsMargins(12, 12, 12, 12)
        capture_layout.setSpacing(10)
        heading = QLabel("Gebiet auswählen")
        heading.setStyleSheet("font-size:20px;font-weight:600;")
        capture_layout.addWidget(heading)
        capture_layout.addWidget(QLabel("Adresse oder Ort suchen"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("z. B. Brandenburger Tor, Berlin")
        self.search_input.returnPressed.connect(self.search)
        search_row = QHBoxLayout()
        search_row.addWidget(self.search_input, 1)
        locate_button = QPushButton("Mein Standort")
        locate_button.clicked.connect(self.use_current_location)
        search_row.addWidget(locate_button)
        capture_layout.addLayout(search_row)
        search_button = QPushButton("Suchen")
        search_button.clicked.connect(self.search)
        capture_layout.addWidget(search_button)

        capture_layout.addWidget(QLabel("Kartenansicht"))
        self.base_layer = QComboBox()
        self.base_layer.addItems(["Karte", "Satellit"])
        self.base_layer.currentTextChanged.connect(
            lambda text: self.js("setBase('satellite')" if self._canonical(text) == "Satellit" else "setBase('normal')")
        )
        map_controls = QHBoxLayout()
        map_controls.addWidget(self.base_layer, 1)
        zoom_button = QPushButton("Auf Flugbereich zoomen")
        zoom_button.clicked.connect(lambda: self.js("zoomToArea()"))
        map_controls.addWidget(zoom_button, 1)
        capture_layout.addLayout(map_controls)

        geozone_group = QGroupBox("UAS-Geozonen")
        geozone_layout = QVBoxLayout(geozone_group)
        geozone_controls = QHBoxLayout()
        self.geozones_toggle = QCheckBox("UAS-Geozonen (Deutschland)")
        self.geozones_toggle.setToolTip("Offizieller dipul/DFS-Kartenlayer, nur zur Orientierung.")
        self.geozones_toggle.toggled.connect(self._set_geozones_enabled)
        geozone_controls.addWidget(self.geozones_toggle, 1)
        self.inspect_button = QPushButton("Was ist hier?")
        self.inspect_button.setCheckable(True)
        self.inspect_button.setEnabled(self.geozones_toggle.isChecked())
        self.inspect_button.toggled.connect(self.set_inspect_mode)
        geozone_controls.addWidget(self.inspect_button, 1)
        self.geozone_review_button = QPushButton("Konflikte …")
        self.geozone_review_button.setEnabled(False)
        self.geozone_review_button.setToolTip("Zuletzt erkannte Überschneidungen erneut prüfen und bearbeiten.")
        self.geozone_review_button.clicked.connect(self._open_geozone_review)
        geozone_controls.addWidget(self.geozone_review_button, 1)
        geozone_layout.addLayout(geozone_controls)
        local_rules_group = QGroupBox("Lokale Bestimmungen")
        local_rules_layout = QHBoxLayout(local_rules_group)
        self.local_rules_toggle = QCheckBox("Lokale Bestimmungen (Deutschland)")
        self.local_rules_toggle.setToolTip("BfN-Schutzgebiete als Hinweis – keine pauschalen Flugverbote.")
        self.local_rules_toggle.toggled.connect(self._set_local_rules_enabled)
        local_rules_layout.addWidget(self.local_rules_toggle, 1)
        self.local_rules_inspect_button = QPushButton("Was ist hier?")
        self.local_rules_inspect_button.setCheckable(True)
        self.local_rules_inspect_button.setEnabled(False)
        self.local_rules_inspect_button.toggled.connect(self.set_local_inspect_mode)
        local_rules_layout.addWidget(self.local_rules_inspect_button, 1)
        local_rules_info = QPushButton("?")
        local_rules_info.setFixedWidth(34)
        local_rules_info.setToolTip("Hinweis zur rechtlichen Einordnung")
        local_rules_info.clicked.connect(self._show_local_rules_info)
        local_rules_layout.addWidget(local_rules_info)
        geozone_layout.addWidget(local_rules_group)
        capture_layout.addWidget(geozone_group)

        flight_area_group = QGroupBox("Flugbereich")
        flight_area_layout = QVBoxLayout(flight_area_group)
        self.draw_button = QPushButton("Polygon")
        self.draw_button.setCheckable(True)
        self.draw_button.toggled.connect(self.set_drawing)
        self.rectangle_button = QPushButton("Rechteck")
        self.rectangle_button.clicked.connect(lambda: self.start_shape("rectangle"))
        self.circle_button = QPushButton("Kreis")
        self.circle_button.clicked.connect(lambda: self.start_shape("circle"))
        shape_row = QHBoxLayout()
        shape_row.addWidget(self.draw_button)
        shape_row.addWidget(self.rectangle_button)
        shape_row.addWidget(self.circle_button)
        flight_area_layout.addLayout(shape_row)
        undo_button = QPushButton("Letzten Punkt rückgängig")
        undo_button.clicked.connect(lambda: self.js("undo()"))
        flight_area_layout.addWidget(undo_button)
        capture_layout.addWidget(flight_area_group)

        no_fly_group = QGroupBox("Sperrgebiete")
        no_fly_layout = QVBoxLayout(no_fly_group)
        self.no_fly_button = QPushButton("Sperrgebiet zeichnen")
        self.no_fly_button.setCheckable(True)
        self.no_fly_button.setStyleSheet("QPushButton { background:#c92525; color:white; font-weight:600; } QPushButton:checked { background:#8e1515; }")
        self.no_fly_button.toggled.connect(self.set_no_fly_drawing)
        no_fly_layout.addWidget(self.no_fly_button)
        cancel_no_fly = QPushButton("Aktuelles Sperrgebiet verwerfen")
        cancel_no_fly.clicked.connect(lambda: self.js("cancelNoFly()"))
        no_fly_layout.addWidget(cancel_no_fly)
        self.zone_list = QListWidget()
        self.zone_list.setMinimumHeight(95)
        self.zone_list.currentRowChanged.connect(lambda row: self.js(f"selectNoFly({row})"))
        self.zone_list.itemDoubleClicked.connect(self.rename_no_fly_zone)
        no_fly_layout.addWidget(self.zone_list)
        delete_zone = QPushButton("Ausgewähltes Sperrgebiet löschen")
        delete_zone.clicked.connect(self.delete_selected_no_fly)
        no_fly_layout.addWidget(delete_zone)
        clear_button = QPushButton("Alles löschen")
        clear_button.clicked.connect(lambda: self.js("clearAll()"))
        no_fly_layout.addWidget(clear_button)
        capture_layout.addWidget(no_fly_group)

        capture_layout.addWidget(QLabel("<hr>"))
        self.count_label = QLabel("Punkte: 0")
        self.area_label = QLabel("Fläche: —")
        capture_layout.addWidget(self.count_label)
        capture_layout.addWidget(self.area_label)
        self.zone_summary = QLabel("Aktive Zone: noch nicht gezeichnet · Sperrgebiete: 0")
        self.zone_summary.setWordWrap(True)
        capture_layout.addWidget(self.zone_summary)
        coordinate_group = QGroupBox("Koordinaten der aktiven Zone (Lat, Lon)")
        coordinate_group.setCheckable(True)
        coordinate_group.setChecked(False)
        coordinate_layout = QVBoxLayout(coordinate_group)
        self.coordinates = QTextEdit()
        self.coordinates.setReadOnly(True)
        self.coordinates.setPlaceholderText("Zeichne mindestens drei Punkte auf der Karte.")
        self.coordinates.setMinimumHeight(120)
        coordinate_layout.addWidget(self.coordinates)
        copy_button = QPushButton("Koordinaten kopieren")
        copy_button.clicked.connect(self.copy_coordinates)
        coordinate_layout.addWidget(copy_button)
        self.coordinates.setVisible(False)
        copy_button.setVisible(False)
        coordinate_group.toggled.connect(self.coordinates.setVisible)
        coordinate_group.toggled.connect(copy_button.setVisible)
        capture_layout.addWidget(coordinate_group, 1)
        tabs.addTab(capture, "Fluggebiet planen")

        # Tab 2: Mapping-Mission einstellen
        flight = QWidget()
        flight_layout = QVBoxLayout(flight)
        flight_layout.setContentsMargins(12, 12, 12, 12)
        flight_layout.setSpacing(10)
        flight_heading = QLabel("Flugeinstellungen")
        flight_heading.setStyleSheet("font-size:20px;font-weight:600;")
        flight_layout.addWidget(flight_heading)

        basic_group = QGroupBox("Routenparameter")
        basic_form = QFormLayout(basic_group)
        self.basic_form = basic_form
        self.altitude = self._number(60, 10, 500, 1, " m")
        self.speed = self._number(5, 1, 15, 0.5, " m/s")
        self.curve_speed = self._number(3, 0.5, 15, 0.5, " m/s")
        self.curve_speed.setToolTip("Wird nur für enge Kurven bei Stützpunkten und Overshooting verwendet.")
        self.path_spacing = self._number(20, 1, 250, 1, " m")
        self.direction = self._number(0, 0, 359.9, 5, " °")
        self.direction_mode = QComboBox()
        self.direction_mode.addItems([
            "West → Ost (0°)", "Ost → West (180°)", "Süd → Nord (90°)",
            "Nord → Süd (270°)", "Eigene Gradzahl", "Optimal (längste Kante)",
            "Optimal (längste Kante, umgekehrt)",
            "Optimal (kürzeste Flugzeit)",
        ])
        self.direction_mode.currentTextChanged.connect(self._direction_mode_changed)
        self.route_mode = QComboBox()
        self.route_mode.currentTextChanged.connect(self._route_mode_changed)
        self.support_spacing = self._number(2, 0.5, 100, 0.5, " m")
        self.support_spacing.setToolTip(
            "Abstand der zwei Stützpunkte vor und nach jedem Umkehrpunkt. "
            "Gerade Bahnen erhalten keine zusätzlichen Punkte."
        )
        self.support_spacing.setEnabled(False)
        self.overshoot_distance = self._number(5, 1, 100, 1, " m")
        self.overshoot_distance.setEnabled(False)
        self.overshoot_distance.setToolTip(
            "Maximale Erweiterung außerhalb des Flugbereichs je U-Turn. "
            "Es werden nur zwei zusätzliche Außenwegpunkte erzeugt."
        )
        self.overshoot_options = QWidget()
        overshoot_options_layout = QHBoxLayout(self.overshoot_options)
        overshoot_options_layout.setContentsMargins(0, 0, 0, 0)
        self.reduced_overshoot_button = QPushButton("Sparmodus")
        self.reduced_overshoot_button.setCheckable(True)
        self.reduced_overshoot_button.setToolTip("Ersetzt die zwei Außenwegpunkte jeder Umkehr durch einen einzelnen Außenwegpunkt.")
        self.reduced_overshoot_button.toggled.connect(self._overshoot_options_changed)
        overshoot_options_layout.addWidget(self.reduced_overshoot_button)
        overshoot_options_layout.addStretch(1)
        self.support_options = QWidget()
        support_options_layout = QHBoxLayout(self.support_options)
        support_options_layout.setContentsMargins(0, 0, 0, 0)
        self.reduced_support_button = QPushButton("Sparmodus")
        self.reduced_support_button.setCheckable(True)
        self.reduced_support_button.setToolTip("Fasst die zwei mittleren Stützpunkte jeder Umkehr zu einem Punkt zusammen.")
        self.reduced_support_button.toggled.connect(self._support_options_changed)
        self.keep_support_inside_button = QPushButton("Nur im Flugbereich erlauben")
        self.keep_support_inside_button.setCheckable(True)
        self.keep_support_inside_button.setToolTip("Plant mit einem Sicherheitsabstand nach innen. Das ist eine Näherung, keine Controller-Garantie.")
        self.keep_support_inside_button.toggled.connect(self._support_options_changed)
        support_options_layout.addWidget(self.reduced_support_button)
        support_options_layout.addWidget(self.keep_support_inside_button)
        self.flight_path_preview = QCheckBox("Geschätzte DJI-Flugbahn anzeigen (Centripetal-Catmull-Rom; Näherung)")
        self.flight_path_preview.setChecked(True)
        self.flight_path_preview.setToolTip(
            "Nur Karten-Vorschau: Die exportierten Wegpunkte bleiben linear. "
            "Die Flugsteuerung kann in der Praxis abweichen."
        )
        self.flight_path_preview.toggled.connect(lambda _checked: self._refresh_mission_display())
        self._configure_route_modes()
        basic_form.addRow("Flughöhe:", self.altitude)
        basic_form.addRow("Geschwindigkeit:", self.speed)
        basic_form.addRow("Kurvengeschwindigkeit:", self.curve_speed)
        basic_form.addRow("Bahnabstand:", self.path_spacing)
        basic_form.addRow("Richtungsvorgabe:", self.direction_mode)
        basic_form.addRow("Bahnrichtung:", self.direction)
        basic_form.addRow("Routenmodus:", self.route_mode)
        basic_form.addRow("Stützpunkt-Abstand an Umkehrpunkten:", self.support_spacing)
        basic_form.addRow("Überflug außerhalb des Flugbereichs:", self.overshoot_distance)
        basic_form.addRow(self.overshoot_options)
        basic_form.addRow(self.support_options)
        basic_form.addRow(self.flight_path_preview)
        self._route_mode_changed(self.route_mode.currentText())
        self._direction_mode_changed(self.direction_mode.currentText())
        flight_layout.addWidget(basic_group)
        photo_group = QGroupBox("Kamera & Photogrammetrie")
        photo_form = QFormLayout(photo_group)
        self.side_overlap = self._number(70, 0, 95, 1, " %")
        self.forward_overlap = self._number(80, 0, 95, 1, " %")
        self.photo_distance = self._number(5, 0.5, 500, 0.5, " m")
        self.gimbal_pitch = self._number(-90, -90, 0, 1, " °")
        self.waypoint_action = QComboBox()
        self.waypoint_action.addItems(["Foto bei jedem Wegpunkt", "Foto nach Distanzintervall", "Keine Aktion", "2 s schweben"])
        photo_form.addRow("Seitliche Überlappung:", self.side_overlap)
        photo_form.addRow("Vorwärtsüberlappung:", self.forward_overlap)
        photo_form.addRow("Foto alle (Distanz):", self.photo_distance)
        photo_form.addRow("Kamera-Neigung:", self.gimbal_pitch)
        photo_form.addRow("Aktion:", self.waypoint_action)
        flight_layout.addWidget(photo_group)
        limit_group = QGroupBox("Missionsgrenze")
        limit_form = QFormLayout(limit_group)
        self.max_waypoints = self._number(200, 2, 65535, 1, " Punkte", decimals=0)
        self.max_flight_minutes = self._number(20, 1, 240, 1, " min", decimals=0)
        self.split_mode = QComboBox()
        self.split_mode.addItems(["Maximal ausnutzen", "Gleichmäßig verteilen"])
        self.finish_action = QComboBox()
        self.finish_action.addItems([
            "Rückkehr zum Startpunkt (Home)",
            "Schweben am letzten Wegpunkt",
            "Landen am letzten Wegpunkt",
            "Zum ersten Wegpunkt",
        ])
        self.signal_loss_action = QComboBox()
        self.signal_loss_action.addItems([
            "Schweben",
            "Rückkehr zum Startpunkt (Home)",
            "Landen",
        ])
        limit_form.addRow("Max. Wegpunkte:", self.max_waypoints)
        limit_form.addRow("Max. Flugzeit / Mission:", self.max_flight_minutes)
        limit_form.addRow("Aufteilung auf Missionen:", self.split_mode)
        limit_form.addRow("Bei Flugende:", self.finish_action)
        limit_form.addRow("Bei Signalverlust:", self.signal_loss_action)
        self.outside_area_mode = QComboBox()
        self.outside_area_mode.addItems(["Außerhalb erlaubt", "Im Flugbereich bleiben (exkl. Overshooting)"])
        self.no_fly_mode = QComboBox()
        self.no_fly_mode.addItems(["Sperrgebiet umfliegen", "Sperrgebiet durchfliegen"])
        limit_form.addRow("Außerhalb des Flugbereichs:", self.outside_area_mode)
        limit_form.addRow("Bei Sperrgebieten:", self.no_fly_mode)
        flight_layout.addWidget(limit_group)
        self.mission_summary = QLabel("Noch keine Route generiert.")
        self.mission_summary.setWordWrap(True)
        self.waypoint_warning = QLabel("")
        self.waypoint_warning.setWordWrap(True)
        flight_layout.addWidget(self.mission_summary)
        flight_layout.addWidget(self.waypoint_warning)
        generate = QPushButton("Route generieren und auf Karte zeigen")
        generate.setStyleSheet("font-weight:600;padding:7px;")
        generate.clicked.connect(self.generate_mission)
        flight_layout.addWidget(generate)
        self.force_one_button = QPushButton("Eine Mission erzwingen (Grenzen überschreiten)")
        self.force_one_button.setToolTip("Behält die eingestellten Grenzwerte bei, exportiert die aktuelle Route aber als eine Mission.")
        self.force_one_button.setStyleSheet("color:#9a6700;font-weight:600;padding:6px;")
        self.force_one_button.clicked.connect(self.force_one_mission)
        self.force_one_button.setVisible(False)
        flight_layout.addWidget(self.force_one_button)
        self.toggle_route_button = QPushButton("Route verstecken")
        self.toggle_route_button.setCheckable(True)
        self.toggle_route_button.toggled.connect(self._toggle_route_visibility)
        clear_route = QPushButton("Routenanzeige löschen")
        clear_route.clicked.connect(lambda: self.js("clearMission()"))
        route_controls = QHBoxLayout()
        route_controls.addWidget(self.toggle_route_button)
        route_controls.addWidget(clear_route)
        flight_layout.addLayout(route_controls)
        flight_layout.addStretch(1)
        tabs.addTab(flight, "Flugeinstellungen")

        # Tab 3: Export und gezieltes Ersetzen einer Controller-Dummy-Mission
        export = QWidget()
        export_layout = QVBoxLayout(export)
        export_layout.setContentsMargins(12, 12, 12, 12)
        export_layout.setSpacing(10)
        export_title = QLabel("Exportieren & Speichern")
        export_title.setStyleSheet("font-size:20px;font-weight:600;")
        export_layout.addWidget(export_title)
        kmz_group = QGroupBox("KMZ-Datei speichern")
        kmz_layout = QVBoxLayout(kmz_group)
        kmz_layout.addWidget(QLabel("Erzeugt ein DJI-WPML-KMZ mit <code>template.kml</code> und <code>waylines.wpml</code>."))
        kmz_layout.addWidget(QLabel("KMZ-Dateiname / Missionsname"))
        self.mission_name = QLineEdit("ACMP_Mapping_Mission")
        self.mission_name.setPlaceholderText("Missionsname")
        kmz_layout.addWidget(self.mission_name)
        save_kmz = QPushButton("KMZ-Datei speichern …")
        save_kmz.clicked.connect(self.export_kmz_file)
        kmz_layout.addWidget(save_kmz)
        export_layout.addWidget(kmz_group)
        preview_group = QGroupBox("Vorschaubilder – experimentell")
        preview_layout = QVBoxLayout(preview_group)
        preview_note = QLabel("Die Bilddateien werden erstellt, aber DJI Fly übernimmt externe Vorschaubilder möglicherweise nicht.")
        preview_note.setWordWrap(True)
        preview_note.setStyleSheet("color:#9a6700;")
        preview_layout.addWidget(preview_note)
        save_preview = QPushButton("Vorschaubild speichern …")
        save_preview.clicked.connect(lambda: self.export_preview_image(False))
        preview_layout.addWidget(save_preview)
        preview_layout.addWidget(QLabel("Text im Vorschaubild"))
        self.thumbnail_title = QLineEdit()
        self.thumbnail_title.setPlaceholderText("z. B. Kirche Nord – Akku 1 – 60 m")
        preview_layout.addWidget(self.thumbnail_title)
        save_named_preview = QPushButton("Vorschaubild mit Name speichern …")
        save_named_preview.clicked.connect(lambda: self.export_preview_image(True))
        preview_layout.addWidget(save_named_preview)
        preview_layout.addWidget(QLabel("Vorschauformat: JPEG, 400 × 300 Pixel"))
        export_layout.addWidget(preview_group)
        export_layout.addStretch(1)
        tabs.addTab(export, "Exportieren")
        self._restore_last_flight_settings()
        self._connect_flight_settings_autosave()
        return side

    @staticmethod
    def _number(value, minimum, maximum, step, suffix, decimals=1):
        field = QDoubleSpinBox()
        field.setRange(minimum, maximum)
        field.setValue(value)
        field.setSingleStep(step)
        field.setDecimals(decimals)
        field.setSuffix(suffix)
        return field

    def _direction_mode_changed(self, selection: str):
        selection = self._canonical(selection)
        fixed_angles = {
            "West → Ost (0°)": 0,
            "Ost → West (180°)": 180,
            "Süd → Nord (90°)": 90,
            "Nord → Süd (270°)": 270,
        }
        if selection == "Eigene Gradzahl":
            self.direction.setEnabled(True)
            return
        self.direction.setEnabled(False)
        if selection in {"Optimal (längste Kante)", "Optimal (längste Kante, umgekehrt)"}:
            if len(self.points) >= 2:
                angle = optimal_direction_deg(self.points)
                self.direction.setValue((angle + 180) % 360 if selection.endswith("umgekehrt)") else angle)
            return
        if selection == "Optimal (kürzeste Flugzeit)":
            self.statusBar().showMessage("Optimale Flugzeit wird beim Generieren der Route berechnet.", 3000)
            return
        self.direction.setValue(fixed_angles[selection])

    def _route_mode_changed(self, selection: str):
        mode = self._canonical(selection)
        support_mode = mode == "Stützpunkte für geradere Bahnen"
        overshoot_mode = mode == "Overshooting"
        self.curve_speed.setEnabled(support_mode or overshoot_mode)
        self.support_spacing.setEnabled(support_mode)
        self.overshoot_distance.setEnabled(overshoot_mode)
        if hasattr(self, "support_options"):
            self._set_route_option_visible(self.support_spacing, support_mode)
            self._set_route_option_visible(self.support_options, support_mode)
            self._set_route_option_visible(self.overshoot_distance, overshoot_mode)
            self._set_route_option_visible(self.overshoot_options, overshoot_mode)
        if mode == "Standard (DJI-Näherung: glatte Kurven)" and not self.flight_path_preview.isChecked():
            self.flight_path_preview.setChecked(True)
        if hasattr(self, "generated_missions"):
            self._refresh_mission_display()

    def _set_route_option_visible(self, field, visible: bool):
        field.setVisible(visible)
        label = self.basic_form.labelForField(field)
        if label is not None:
            label.setVisible(visible)

    def _support_options_changed(self, *_args):
        self.reduced_support_points = self.reduced_support_button.isChecked()
        self.keep_support_route_inside = self.keep_support_inside_button.isChecked()
        self._save_last_flight_settings()

    def _overshoot_options_changed(self, *_args):
        self.reduced_overshoot_points = self.reduced_overshoot_button.isChecked()
        self._save_last_flight_settings()

    def _configure_route_modes(self):
        """Expose point-stop WPML only for the drone categories that support it."""
        previous = self._canonical(self.route_mode.currentText())
        if previous == "Lineare Wegpunkte (derzeit; mit Overshoot)":
            previous = "Overshooting"
        modes = [
            "Standard (DJI-Näherung: glatte Kurven)",
            "Stützpunkte für geradere Bahnen",
            "Overshooting",
        ]
        if str(self.settings.value("drone_category", "consumer")) == "prosumer_enterprise":
            modes.insert(1, "WPML gerade / Punktstopp (nicht garantiert)")
        self.route_mode.blockSignals(True)
        self.route_mode.clear()
        self.route_mode.addItems(modes)
        self.route_mode.setCurrentText(previous if previous in modes else modes[0])
        self.route_mode.blockSignals(False)
        self._route_mode_changed(self.route_mode.currentText())

    def _set_saved_route_mode(self, value):
        mode = self._canonical(str(value))
        if mode == "Lineare Wegpunkte (derzeit; mit Overshoot)":
            mode = "Overshooting"
        for index in range(self.route_mode.count()):
            if self._canonical(self.route_mode.itemText(index)) == mode:
                self.route_mode.setCurrentIndex(index)
                return

    def _set_saved_outside_area_mode(self, value):
        mode = self._canonical(str(value))
        if mode in {"Dauerhaft im Flugbereich bleiben", "Im Flugbereich bleiben (exkl. Overshooting)"}:
            self.outside_area_mode.setCurrentIndex(1)
        elif mode in [self._canonical(self.outside_area_mode.itemText(index)) for index in range(self.outside_area_mode.count())]:
            self.outside_area_mode.setCurrentText(str(value))

    def _refresh_mission_display(self):
        if self.generated_missions:
            self._show_missions(self.generated_missions)

    def _toggle_route_visibility(self, hidden: bool):
        self.js(f"setMissionVisible({str(not hidden).lower()})")
        self.toggle_route_button.setText("Route zeigen" if hidden else "Route verstecken")

    def _preset_values(self) -> dict:
        return {
            "altitude": self.altitude.value(), "speed": self.speed.value(), "curve_speed": self.curve_speed.value(),
            "path_spacing": self.path_spacing.value(), "direction": self.direction.value(),
            "direction_mode": self.direction_mode.currentText(),
            "route_mode": self.route_mode.currentText(), "support_spacing": self.support_spacing.value(), "overshoot_distance": self.overshoot_distance.value(),
            "reduced_support_points": self.reduced_support_points, "keep_support_route_inside": self.keep_support_route_inside,
            "reduced_overshoot_points": self.reduced_overshoot_points,
            "side_overlap": self.side_overlap.value(), "forward_overlap": self.forward_overlap.value(),
            "photo_distance": self.photo_distance.value(), "gimbal_pitch": self.gimbal_pitch.value(),
            "waypoint_action": self.waypoint_action.currentText(),
            "max_waypoints": self.max_waypoints.value(), "max_flight_minutes": self.max_flight_minutes.value(),
            "split_mode": self.split_mode.currentText(),
            "finish_action": self.finish_action.currentText(),
            "signal_loss_action": self.signal_loss_action.currentText(),
            "outside_area_mode": self.outside_area_mode.currentText(), "no_fly_mode": self.no_fly_mode.currentText(),
        }

    def save_preset(self):
        name, accepted = QInputDialog.getText(self, "Preset speichern", "Name des Presets:")
        name = name.strip()
        if not accepted or not name:
            return
        safe_name="".join(char for char in name if char.isalnum() or char in "-_ ").strip() or "Preset"
        try:
            self.preset_dir.mkdir(exist_ok=True)
            destination=self.preset_dir / f"{safe_name}.json"
            destination.write_text(json.dumps(self._preset_values(),ensure_ascii=False,indent=2),encoding="utf-8")
        except OSError as error:
            QMessageBox.critical(self,"Preset fehlgeschlagen",f"Das Preset konnte nicht gespeichert werden:\n\n{error}"); return
        self.statusBar().showMessage(f"Preset gespeichert: {destination.name}", 3000)

    def load_preset(self):
        files=sorted(self.preset_dir.glob("*.json")) if self.preset_dir.is_dir() else []
        if not files:
            QMessageBox.information(self, "Keine Presets", "Es wurde noch kein Flugeinstellungs-Preset gespeichert.")
            return
        names=[file.stem for file in files]
        name, accepted = QInputDialog.getItem(self, "Preset laden", "Preset:", names, 0, False)
        if not accepted:
            return
        try:
            values = json.loads((self.preset_dir / f"{name}.json").read_text(encoding="utf-8"))
            for field, key in [
                (self.altitude, "altitude"), (self.speed, "speed"), (self.path_spacing, "path_spacing"),
                (self.side_overlap, "side_overlap"), (self.forward_overlap, "forward_overlap"),
                (self.photo_distance, "photo_distance"), (self.gimbal_pitch, "gimbal_pitch"),
                (self.max_waypoints, "max_waypoints"), (self.max_flight_minutes, "max_flight_minutes"),
                (self.support_spacing, "support_spacing"),
            ]:
                field.setValue(float(values[key]))
            if "curve_speed" in values:
                self.curve_speed.setValue(float(values["curve_speed"]))
            if "overshoot_distance" in values:
                self.overshoot_distance.setValue(float(values["overshoot_distance"]))
            self.direction_mode.setCurrentText(values["direction_mode"])
            self._set_saved_route_mode(values["route_mode"])
            if self._canonical(values["direction_mode"]) == "Eigene Gradzahl":
                self.direction.setValue(float(values["direction"]))
            else:
                self._direction_mode_changed(values["direction_mode"])
            self.waypoint_action.setCurrentText(values["waypoint_action"])
            self.split_mode.setCurrentText(values["split_mode"])
            self.finish_action.setCurrentText(values.get("finish_action", self.finish_action.currentText()))
            self.signal_loss_action.setCurrentText(values.get("signal_loss_action", self.signal_loss_action.currentText()))
            self._set_saved_outside_area_mode(values.get("outside_area_mode", self.outside_area_mode.currentText()))
            self.no_fly_mode.setCurrentText(values.get("no_fly_mode", self.no_fly_mode.currentText()))
            self.reduced_support_button.setChecked(bool(values.get("reduced_support_points", False)))
            self.keep_support_inside_button.setChecked(bool(values.get("keep_support_route_inside", False)))
            self.reduced_overshoot_button.setChecked(bool(values.get("reduced_overshoot_points", False)))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            QMessageBox.warning(self, "Preset fehlerhaft", f"Das Preset konnte nicht geladen werden:\n{error}")
            return
        self.statusBar().showMessage(f"Preset „{name}“ geladen.", 3000)

    def choose_language(self):
        """Wechselt die sichtbare Oberfläche und speichert die Auswahl dauerhaft."""
        choices = ["Deutsch", "English"]
        current = 1 if self.settings.value("ui_language", "de") == "en" else 0
        choice, accepted = QInputDialog.getItem(self, "Sprache", "Oberflächensprache:", choices, current, False)
        if not accepted:
            return
        language = "en" if choice == "English" else "de"
        self.settings.setValue("ui_language", language)
        self.settings.sync()
        self.ui_language = language
        self._apply_language()

    def open_settings_dialog(self):
        """Zentrale Einstellungen für Profil, Oberfläche und UAS-Geozonen."""
        english = self.ui_language == "en"
        dialog = QDialog(self)
        dialog.setWindowTitle("Settings" if english else "Einstellungen")
        dialog.setMinimumWidth(440)
        layout = QVBoxLayout(dialog)

        settings_tabs = QTabWidget(dialog)
        layout.addWidget(settings_tabs)

        general = QWidget(settings_tabs)
        general_form = QFormLayout(general)
        drone_category = QComboBox(general)
        drone_category.addItem(
            "Consumer (e.g. DJI Mini 5 Pro, Lito)" if english else
            "Consumer (z. B. DJI Mini 5 Pro, Lito)",
            "consumer",
        )
        drone_category.addItem(
            "Prosumer / Enterprise (e.g. Matrice, RTK models)" if english else
            "Prosumer / Enterprise (z. B. Matrice, RTK-Modelle)",
            "prosumer_enterprise",
        )
        saved_category = str(self.settings.value("drone_category", "consumer"))
        drone_category.setCurrentIndex(1 if saved_category == "prosumer_enterprise" else 0)
        general_form.addRow("Drone category" if english else "Drohnenart", drone_category)
        general_note = QLabel(
            "This selection is saved as your drone profile and will be used for category-specific settings."
            if english else
            "Die Auswahl wird als Drohnenprofil gespeichert und dient künftig als Grundlage für kategorieabhängige Einstellungen."
        )
        general_note.setWordWrap(True)
        general_note.setStyleSheet("color:#596780;")
        general_form.addRow(general_note)
        settings_tabs.addTab(general, "General" if english else "Allgemein")

        geozone_tab = QWidget(settings_tabs)
        geozone_layout = QVBoxLayout(geozone_tab)
        language_row = QHBoxLayout()
        language_row.addWidget(QLabel("Language" if english else "Sprache"))
        language = QComboBox(dialog)
        language.addItem("Deutsch", "de")
        language.addItem("English", "en")
        language.setCurrentIndex(1 if self.ui_language == "en" else 0)
        language_row.addWidget(language, 1)
        geozone_layout.addLayout(language_row)

        geozones = QGroupBox("UAS geozones" if english else "UAS-Geozonen", geozone_tab)
        geozone_form = QFormLayout(geozones)
        opacity = QSpinBox(geozones)
        opacity.setRange(10, 100)
        opacity.setSuffix(" %")
        opacity.setValue(int(self.settings.value("geozone_opacity", 85)))
        geozone_form.addRow("Opacity" if english else "Deckkraft", opacity)
        local_opacity = QSpinBox(geozones)
        local_opacity.setRange(10, 100)
        local_opacity.setSuffix(" %")
        local_opacity.setValue(int(self.settings.value("local_rules_opacity", 35)))
        geozone_form.addRow("Local-rules opacity" if english else "Deckkraft lokaler Regeln", local_opacity)
        zone_method = QComboBox(geozones)
        zone_method.addItem("Global – full official area" if english else "Global – vollständige offizielle Fläche", "global")
        zone_method.addItem("Fine – clipped intersection areas" if english else "Fein – zugeschnittene Schnittflächen", "fine")
        zone_method.setCurrentIndex(1 if self.geozone_zone_method == "fine" else 0)
        geozone_form.addRow("No-fly zone method" if english else "Sperrgebiets-Methode", zone_method)
        geozone_layout.addWidget(geozones)

        note = (
            "Fine mode splits large official areas into their actual intersections with the flight area. "
            "The setting applies to the next geozone check."
            if english else
            "Der Feinmodus schneidet große offizielle Flächen auf ihre tatsächlichen Schnittflächen mit dem Flugbereich zu. "
            "Die Einstellung gilt für die nächste Geozonen-Prüfung."
        )
        note_label = QLabel(note)
        note_label.setWordWrap(True)
        geozone_layout.addWidget(note_label)
        geozone_layout.addStretch(1)
        settings_tabs.addTab(geozone_tab, "UAS geozones" if english else "UAS-Geozonen")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, parent=dialog)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.settings.setValue("drone_category", drone_category.currentData())
        self.settings.setValue("geozone_opacity", opacity.value())
        self.settings.setValue("local_rules_opacity", local_opacity.value())
        self.settings.setValue("geozone_zone_method", zone_method.currentData())
        self.settings.setValue("ui_language", language.currentData())
        self.settings.sync()
        self.geozone_zone_method = zone_method.currentData()
        self._configure_route_modes()
        self.js(f"setGeozoneOpacity({opacity.value()})")
        self.js(f"setLocalRulesOpacity({local_opacity.value()})")
        if self.ui_language != language.currentData():
            self.ui_language = language.currentData()
            self._apply_language()

    def set_geozone_opacity(self):
        value, accepted = QInputDialog.getInt(self, "Geozonen-Deckkraft", "Deckkraft in Prozent:", 85, 10, 100, 5)
        if accepted:
            self.js(f"setGeozoneOpacity({value})")

    def _set_geozones_enabled(self, enabled: bool):
        self.js(f"setGeozones({str(enabled).lower()})")
        # Mit vorhandener Flugfläche darf der Knopf die Prüfung nachträglich starten.
        # Ohne aktivierte UAS-Zonen bleibt er dagegen immer deaktiviert.
        self.geozone_review_button.setEnabled(bool(enabled) and len(self.points) >= 3)
        self.inspect_button.setEnabled(enabled)
        if not enabled and self.inspect_button.isChecked():
            self.inspect_button.setChecked(False)

    def _set_local_rules_enabled(self, enabled: bool):
        self.js(f"setLocalRules({str(enabled).lower()})")
        self.local_rules_inspect_button.setEnabled(enabled)
        if not enabled and self.local_rules_inspect_button.isChecked():
            self.local_rules_inspect_button.setChecked(False)

    def _apply_saved_map_opacities(self):
        self.js(f"setGeozoneOpacity({int(self.settings.value('geozone_opacity', 85))})")
        self.js(f"setLocalRulesOpacity({int(self.settings.value('local_rules_opacity', 35))})")

    def _show_local_rules_info(self):
        english = self.ui_language == "en"
        QMessageBox.information(
            self,
            "Local rules (Germany)" if english else "Lokale Bestimmungen (Deutschland)",
            (
                "This layer shows selected official BfN protected-area categories: landscape protection areas, nature parks, biosphere reserves and national natural monuments. "
                "It is a planning hint only, not a general no-fly layer. Local protection regulations, municipal rules, approvals and current restrictions can differ by area and must be checked separately."
                if english else
                "Dieser Layer zeigt ausgewählte offizielle BfN-Schutzgebietskategorien: Landschaftsschutzgebiete, Naturparke, Biosphärenreservate und Nationale Naturmonumente. "
                "Er ist nur ein Planungshinweis und keine pauschale Flugverbotskarte. Örtliche Schutzverordnungen, kommunale Regeln, Genehmigungen und aktuelle Einschränkungen können je Gebiet abweichen und müssen separat geprüft werden."
            ),
        )

    def _apply_language(self):
        """Übersetzt alle sichtbaren Standardtexte; interne Routenwerte bleiben kanonisch deutsch."""
        def translate(text: str) -> str:
            # Die Quelltexte der Oberfläche sind deutsch. Bei deutscher UI
            # darf keine Rückübersetzung stattfinden ("Export" ist sonst ein
            # Teilstring von "Exportieren").
            if self.ui_language != "en":
                return text
            replacements = UI_EN.items()
            for source, target in sorted(replacements, key=lambda item: len(item[0]), reverse=True):
                text = text.replace(source, target)
            return text

        self.file_menu.setTitle(translate("Datei"))
        self.settings_action.setText(translate("Einstellungen"))
        for action in self.findChildren(QAction):
            action.setText(translate(action.text()))
        for widget_type in (QLabel, QPushButton, QCheckBox):
            for widget in self.findChildren(widget_type):
                widget.setText(translate(widget.text()))
        for group_box in self.findChildren(QGroupBox):
            group_box.setTitle(translate(group_box.title()))
        for field in self.findChildren(QLineEdit):
            field.setPlaceholderText(translate(field.placeholderText()))
        for widget in self.findChildren(QWidget):
            if widget.toolTip():
                widget.setToolTip(translate(widget.toolTip()))
        for combo in self.findChildren(QComboBox):
            for index in range(combo.count()):
                combo.setItemText(index, translate(combo.itemText(index)))
        for tabs in self.findChildren(QTabWidget):
            for index in range(tabs.count()):
                tabs.setTabText(index, translate(tabs.tabText(index)))

    @staticmethod
    def _canonical(value: str) -> str:
        return canonical_ui_text(value)

    @staticmethod
    def _project_polygon(value, label: str) -> list[list[float]]:
        """Prüft die gespeicherte [Breite, Länge]-Geometrie eines Projekts."""
        if not isinstance(value, list):
            raise ValueError(f"{label} enthält keine Punktliste.")
        result = []
        for point in value:
            if not isinstance(point, list) or len(point) != 2:
                raise ValueError(f"{label} enthält einen ungültigen Punkt.")
            lat, lon = float(point[0]), float(point[1])
            if not -90 <= lat <= 90 or not -180 <= lon <= 180:
                raise ValueError(f"{label} enthält Koordinaten außerhalb des gültigen Bereichs.")
            result.append([lat, lon])
        return result

    def _apply_project_settings(self, values: dict):
        if not isinstance(values, dict):
            raise ValueError("Die Flugeinstellungen sind ungültig.")
        number_fields = [
            (self.altitude, "altitude"), (self.speed, "speed"), (self.curve_speed, "curve_speed"), (self.path_spacing, "path_spacing"),
            (self.direction, "direction"), (self.support_spacing, "support_spacing"), (self.overshoot_distance, "overshoot_distance"),
            (self.side_overlap, "side_overlap"), (self.forward_overlap, "forward_overlap"),
            (self.photo_distance, "photo_distance"), (self.gimbal_pitch, "gimbal_pitch"),
            (self.max_waypoints, "max_waypoints"), (self.max_flight_minutes, "max_flight_minutes"),
        ]
        for field, key in number_fields:
            if key in values:
                field.setValue(float(values[key]))
        combo_fields = [
            (self.direction_mode, "direction_mode"), (self.route_mode, "route_mode"),
            (self.waypoint_action, "waypoint_action"), (self.split_mode, "split_mode"),
            (self.finish_action, "finish_action"), (self.signal_loss_action, "signal_loss_action"),
        ]
        for field, key in combo_fields:
            if key in values and values[key] in [field.itemText(i) for i in range(field.count())]:
                field.setCurrentText(values[key])
        if "outside_area_mode" in values:
            self._set_saved_outside_area_mode(values["outside_area_mode"])
        self.reduced_support_button.setChecked(bool(values.get("reduced_support_points", False)))
        self.keep_support_inside_button.setChecked(bool(values.get("keep_support_route_inside", False)))
        self.reduced_overshoot_button.setChecked(bool(values.get("reduced_overshoot_points", False)))
        self._direction_mode_changed(self.direction_mode.currentText())
        self._route_mode_changed(self.route_mode.currentText())

    def save_project_as(self):
        default_name = "".join(char for char in self.mission_name.text().strip() if char.isalnum() or char in "-_ ") or "ACMP_Projekt"
        filename, _ = QFileDialog.getSaveFileName(
            self, "ACMP-Projekt speichern", f"{default_name}.acmp.json", "ACMP-Projekt (*.acmp.json);;JSON-Datei (*.json)"
        )
        if not filename:
            return
        destination = Path(filename)
        if not destination.name.lower().endswith((".acmp.json", ".json")):
            destination = destination.with_suffix(".acmp.json")
        project = {
            "format": "ACMP project",
            "version": 1,
            "active_zone": self.points,
            "no_fly_zones": self.no_fly_zones,
            "flight_settings": self._preset_values(),
            "export_settings": {
                "mission_name": self.mission_name.text(),
                "thumbnail_title": self.thumbnail_title.text(),
                "base_layer": self.base_layer.currentText(),
            },
            "generated_route": self.generated_route,
            "generated_missions": self.generated_missions,
            "mission_override": {"force_single_mission": self.force_single_mission},
        }
        try:
            destination.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as error:
            QMessageBox.critical(self, "Speichern fehlgeschlagen", f"Das Projekt konnte nicht gespeichert werden.\n\n{error}")
            return
        self.current_project_path = destination
        self.statusBar().showMessage(f"Projekt gespeichert: {destination.name}", 5000)

    def save_project(self):
        if self.current_project_path is None:
            self.save_project_as()
            return
        project = {
            "format": "ACMP project", "version": 1, "active_zone": self.points,
            "no_fly_zones": self.no_fly_zones, "flight_settings": self._preset_values(),
            "export_settings": {"mission_name": self.mission_name.text(), "thumbnail_title": self.thumbnail_title.text(), "base_layer": self.base_layer.currentText()},
            "generated_route": self.generated_route, "generated_missions": self.generated_missions,
            "mission_override": {"force_single_mission": self.force_single_mission},
        }
        try:
            self.current_project_path.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as error:
            QMessageBox.critical(self, "Speichern fehlgeschlagen", str(error)); return
        self.statusBar().showMessage(f"Projekt gespeichert: {self.current_project_path.name}", 5000)

    def new_project(self):
        self.current_project_path = None
        self.points, self.no_fly_zones, self.no_fly_names = [], [], []
        self.generated_route, self.generated_missions = [], []
        self.mission_name.setText("ACMP_Mapping_Mission")
        self.thumbnail_title.clear()
        self.js("clearAll(); clearMission();")
        self._refresh_geometry_ui()
        self.statusBar().showMessage("Neues Projekt erstellt.", 3000)

    def open_project(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "ACMP-Projekt öffnen", "", "ACMP-Projekt (*.acmp.json);;JSON-Datei (*.json)"
        )
        if not filename:
            return
        try:
            project = json.loads(Path(filename).read_text(encoding="utf-8"))
            if not isinstance(project, dict) or project.get("format") != "ACMP project":
                raise ValueError("Die Datei ist kein ACMP-Projekt.")
            points = self._project_polygon(project.get("active_zone", []), "Aktive Zone")
            zones = [self._project_polygon(zone, f"Sperrgebiet {index}") for index, zone in enumerate(project.get("no_fly_zones", []), 1)]
            if len(points) not in (0,) and len(points) < 3:
                raise ValueError("Die aktive Zone benötigt mindestens drei Punkte.")
            if any(len(zone) < 3 for zone in zones):
                raise ValueError("Jedes Sperrgebiet benötigt mindestens drei Punkte.")
            self._apply_project_settings(project.get("flight_settings", {}))
            export_settings = project.get("export_settings", {})
            if not isinstance(export_settings, dict):
                raise ValueError("Die Export-Einstellungen sind ungültig.")
            self.mission_name.setText(str(export_settings.get("mission_name", self.mission_name.text())))
            self.thumbnail_title.setText(str(export_settings.get("thumbnail_title", self.thumbnail_title.text())))
            if self._canonical(str(export_settings.get("base_layer", ""))) in ("Karte", "Satellit"):
                self.base_layer.setCurrentText(str(export_settings["base_layer"]))
            route = self._project_polygon(project.get("generated_route", []), "Generierte Route")
            missions = [self._project_polygon(mission, f"Teilmission {index}") for index, mission in enumerate(project.get("generated_missions", []), 1)]
            if any(len(mission) < 2 for mission in missions):
                raise ValueError("Eine gespeicherte Teilmission benötigt mindestens zwei Wegpunkte.")
            mission_override = project.get("mission_override", {})
            if not isinstance(mission_override, dict):
                raise ValueError("Die gespeicherte Missionsübersteuerung ist ungültig.")
            force_single_mission = bool(mission_override.get("force_single_mission", False))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
            QMessageBox.warning(self, "Öffnen fehlgeschlagen", f"Das Projekt konnte nicht geöffnet werden.\n\n{error}")
            return

        self.points, self.no_fly_zones = points, zones
        self.current_project_path = Path(filename)
        self.generated_route, self.generated_missions = route, missions
        self.force_single_mission = force_single_mission
        self._refresh_geometry_ui()
        self.force_one_button.setVisible(len(missions) > 1 and not force_single_mission)
        self.js(f"setProjectGeometry({json.dumps(points)}, {json.dumps(zones)});")
        if missions:
            self._show_missions(missions)
        else:
            self.js("clearMission();")
        self.statusBar().showMessage(f"Projekt geöffnet: {Path(filename).name}", 5000)

    def js(self, script: str):
        self.map_view.page().runJavaScript(script)

    @staticmethod
    def _handle_web_permission(permission: QWebEnginePermission):
        """Erlaubt ausschließlich den Standort; alle anderen Web-Rechte bleiben gesperrt."""
        if permission.permissionType() == QWebEnginePermission.PermissionType.Geolocation:
            permission.grant()
        else:
            permission.deny()

    def set_drawing(self, active: bool):
        self.draw_button.setText("Fertig" if active else "Polygon")
        if active and self.no_fly_button.isChecked():
            self.no_fly_button.setChecked(False)
        if active and self.inspect_button.isChecked():
            self.inspect_button.setChecked(False)
        if active and self.local_rules_inspect_button.isChecked():
            self.local_rules_inspect_button.setChecked(False)
        self.js(f"setDrawing({str(active).lower()})")
        # Die Prüfung gehört zum Abschluss der Fläche, nicht zu jedem Klick.
        if not active:
            QTimer.singleShot(100, self._queue_geozone_check)

    def set_no_fly_drawing(self, active: bool):
        self.no_fly_button.setText("Sperrgebiet abschließen" if active else "Sperrgebiet zeichnen")
        if active and self.draw_button.isChecked():
            self.draw_button.setChecked(False)
        if active and self.inspect_button.isChecked():
            self.inspect_button.setChecked(False)
        if active and self.local_rules_inspect_button.isChecked():
            self.local_rules_inspect_button.setChecked(False)
        self.js(f"setNoFlyDrawing({str(active).lower()})")

    def set_inspect_mode(self, active: bool):
        if active and self.draw_button.isChecked():
            self.draw_button.setChecked(False)
        if active and self.no_fly_button.isChecked():
            self.no_fly_button.setChecked(False)
        if active and self.local_rules_inspect_button.isChecked():
            self.local_rules_inspect_button.setChecked(False)
        self.js(f"setInspect({str(active).lower()})")
        if active:
            self.statusBar().showMessage("Auf einen Punkt in der Karte klicken, um die UAS-Geozonen zu prüfen.", 5000)

    def set_local_inspect_mode(self, active: bool):
        if active and self.inspect_button.isChecked():
            self.inspect_button.setChecked(False)
        if active and self.draw_button.isChecked():
            self.draw_button.setChecked(False)
        if active and self.no_fly_button.isChecked():
            self.no_fly_button.setChecked(False)
        self.js(f"setLocalInspect({str(active).lower()})")
        if active:
            self.statusBar().showMessage("Auf einen Punkt in der Karte klicken, um lokale Schutzgebietshinweise zu prüfen.", 5000)

    def start_shape(self, shape: str):
        if self.draw_button.isChecked():
            self.draw_button.setChecked(False)
        if self.no_fly_button.isChecked():
            self.no_fly_button.setChecked(False)
        if self.inspect_button.isChecked():
            self.inspect_button.setChecked(False)
        if self.local_rules_inspect_button.isChecked():
            self.local_rules_inspect_button.setChecked(False)
        label = "Rechteck" if shape == "rectangle" else "Kreis"
        self.statusBar().showMessage(f"{label}: Auf der Karte klicken, gedrückt halten und aufziehen.", 5000)
        self.js(f"setShapeDrawing('{shape}')")

    def _shape_completed(self):
        self.statusBar().showMessage("Flugzone erstellt. Die Route kann nun neu generiert werden.", 4000)
        QTimer.singleShot(100, self._queue_geozone_check)

    def _queue_geozone_check(self):
        """Prüft die fertig gezeichnete Flugfläche asynchron gegen dipul-WFS."""
        if not self.geozones_toggle.isChecked() or len(self.points) < 3:
            return
        self._geozone_check_id += 1
        check_id = self._geozone_check_id
        points = [(float(lat), float(lon)) for lat, lon in self.points]
        self.statusBar().showMessage("Prüfe UAS-Geozonen für die Flugfläche …", 2500)
        threading.Thread(
            target=self._run_geozone_check,
            args=(check_id, points),
            name="acmp-geozone-check",
            daemon=True,
        ).start()

    def _run_geozone_check(self, check_id: int, points: list[tuple[float, float]]):
        """Läuft außerhalb des UI-Threads; ein WFS-Ausfall blockiert die Karte nicht."""
        try:
            hits = self._query_geozone_features(points)
        except (OSError, ValueError, UnicodeError):
            hits = []
        self.geozone_check_finished.emit(check_id, hits)

    @staticmethod
    def _point_in_polygon(point: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
        """Ray-casting inklusive Rand; Koordinaten sind (Breite, Länge)."""
        lat, lon = point
        inside = False
        for index, (lat_a, lon_a) in enumerate(polygon):
            lat_b, lon_b = polygon[(index + 1) % len(polygon)]
            if ((lon_a > lon) != (lon_b > lon)) and lat < (lat_b - lat_a) * (lon - lon_a) / (lon_b - lon_a) + lat_a:
                inside = not inside
        return inside

    @staticmethod
    def _segments_intersect(
        first_a: tuple[float, float], first_b: tuple[float, float],
        second_a: tuple[float, float], second_b: tuple[float, float],
    ) -> bool:
        def orientation(a, b, c):
            value = (b[1] - a[1]) * (c[0] - b[0]) - (b[0] - a[0]) * (c[1] - b[1])
            return 0 if abs(value) < 1e-12 else (1 if value > 0 else -1)
        one = orientation(first_a, first_b, second_a)
        two = orientation(first_a, first_b, second_b)
        three = orientation(second_a, second_b, first_a)
        four = orientation(second_a, second_b, first_b)
        return one != two and three != four

    @staticmethod
    def _polygons_intersect(first: list[tuple[float, float]], second: list[tuple[float, float]]) -> bool:
        if any(MainWindow._point_in_polygon(point, second) for point in first):
            return True
        if any(MainWindow._point_in_polygon(point, first) for point in second):
            return True
        return any(
            MainWindow._segments_intersect(a, b, c, d)
            for index, a in enumerate(first)
            for b in [first[(index + 1) % len(first)]]
            for other_index, c in enumerate(second)
            for d in [second[(other_index + 1) % len(second)]]
        )

    @staticmethod
    def _feature_rings(feature: dict) -> list[list[tuple[float, float]]]:
        geometry = feature.get("geometry") or {}
        coordinates = geometry.get("coordinates") or []
        if geometry.get("type") == "Polygon":
            polygons = [coordinates]
        elif geometry.get("type") == "MultiPolygon":
            polygons = coordinates
        else:
            return []
        return [
            [(float(lat), float(lon)) for lon, lat, *_ in polygon[0]]
            for polygon in polygons if polygon and polygon[0]
        ]

    def _query_geozone_features(self, points: list[tuple[float, float]]) -> list[dict]:
        """Lädt echte GeoJSON-Flächen vom offiziellen WFS und filtert Schnittmengen."""
        latitudes, longitudes = zip(*points)
        bbox = f"{min(longitudes)},{min(latitudes)},{max(longitudes)},{max(latitudes)},EPSG:4326"
        flight_area = Polygon([(lon, lat) for lat, lon in points])

        def polygon_parts(geometry):
            if geometry.is_empty:
                return []
            if geometry.geom_type == "Polygon":
                return [geometry]
            if geometry.geom_type in {"MultiPolygon", "GeometryCollection"}:
                return [part for item in geometry.geoms for part in polygon_parts(item)]
            return []

        def load_layer(layer: str) -> list[dict]:
            params = {
                "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
                "typeNames": layer, "outputFormat": "application/json", "bbox": bbox, "count": 100,
            }
            with urlopen(f"https://uas-betrieb.de/geoservices/dipul/wfs?{urlencode(params)}", timeout=8.0) as response:
                payload = json.loads(response.read().decode("utf-8"))
            matching = []
            for feature in payload.get("features", []):
                geometry = shape(feature.get("geometry"))
                if not geometry.intersects(flight_area):
                    continue
                if self.geozone_zone_method == "fine":
                    for part_index, part in enumerate(polygon_parts(geometry.intersection(flight_area)), start=1):
                        clipped = json.loads(json.dumps(feature))
                        clipped["id"] = f"{feature.get('id', layer)}:part-{part_index}"
                        clipped["geometry"] = mapping(part)
                        clipped.setdefault("properties", {})["_acmp_label"] = GEOZONE_LABELS[layer]
                        matching.append(clipped)
                else:
                    feature.setdefault("properties", {})["_acmp_label"] = GEOZONE_LABELS[layer]
                    matching.append(feature)
            return matching

        features: list[dict] = []
        # Begrenzte Parallelität hält die Wartezeit kurz, ohne den öffentlichen Dienst zu überlasten.
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(load_layer, layer) for layer in GEOZONE_LABELS]
            for future in as_completed(futures):
                try:
                    features.extend(future.result())
                except (OSError, ValueError, UnicodeError, json.JSONDecodeError):
                    continue
        return features

    def _inspect_map_point(self, coordinate: list):
        """Empfängt den Klick des Kartenmodus 'Was ist hier?'."""
        if hasattr(self, "inspect_button") and self.inspect_button.isChecked():
            self.inspect_button.setChecked(False)
        self._start_context_geozone_check(coordinate)

    def _inspect_local_rules_point(self, coordinate: list):
        if self.local_rules_inspect_button.isChecked():
            self.local_rules_inspect_button.setChecked(False)
        if not isinstance(coordinate, list) or len(coordinate) != 2:
            return
        try:
            lat, lon = float(coordinate[0]), float(coordinate[1])
        except (TypeError, ValueError):
            return
        delta = 0.00002
        probe = [(lat - delta, lon - delta), (lat - delta, lon + delta),
                 (lat + delta, lon + delta), (lat + delta, lon - delta)]
        self.statusBar().showMessage("Prüfe lokale Schutzgebietshinweise an dieser Stelle …", 2500)
        threading.Thread(
            target=self._run_local_rules_check,
            args=(probe,),
            name="acmp-local-rules-check",
            daemon=True,
        ).start()

    def _run_local_rules_check(self, probe: list[tuple[float, float]]):
        try:
            latitudes, longitudes = zip(*probe)
            # Der BfN-WFS folgt für EPSG:4326 der offiziellen Achsenreihenfolge Breite/Länge.
            bbox = f"{min(latitudes)},{min(longitudes)},{max(latitudes)},{max(longitudes)},EPSG:4326"
            probe_shape = Polygon([(lon, lat) for lat, lon in probe])

            def load_layer(layer: str) -> list[dict]:
                params = {
                    "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
                    "typeNames": f"bfn_sch_Schutzgebiet:{layer}", "outputFormat": "GEOJSON", "bbox": bbox, "count": 30,
                }
                url = f"https://geodienste.bfn.de/ogc/wfs/schutzgebiet?{urlencode(params)}"
                with urlopen(url, timeout=8.0) as response:
                    data = json.loads(response.read().decode("utf-8"))
                return [
                    feature for feature in data.get("features", [])
                    if shape(feature.get("geometry")).intersects(probe_shape)
                ]

            found: list[tuple[str, dict]] = []
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {executor.submit(load_layer, layer): label for layer, label in LOCAL_RULE_LAYERS.items()}
                for future in as_completed(futures):
                    try:
                        found.extend((futures[future], feature) for feature in future.result())
                    except (OSError, TypeError, ValueError, UnicodeError, json.JSONDecodeError):
                        continue
        except (OSError, TypeError, ValueError, UnicodeError):
            found = []
        self.local_rules_check_finished.emit(found)

    def _show_local_rules_result(self, found: object):
        if not self.local_rules_toggle.isChecked():
            return
        english = self.ui_language == "en"
        title = "Local rules (Germany)" if english else "Lokale Bestimmungen (Deutschland)"
        if not found:
            QMessageBox.information(
                self, title,
                "No configured local-rule protected area was found at this position." if english
                else "An dieser Position wurde kein konfiguriertes Schutzgebiet für lokale Bestimmungen gefunden.",
            )
            return
        entries = []
        for label, feature in found:
            properties = feature.get("properties", {})
            name = properties.get("NAME") or properties.get("name") or properties.get("BEZEICHNUNG")
            entries.append(f"• {label}" + (f": {name}" if name else ""))
        notice = (
            "These are planning hints only. Local rules, protection regulations and approvals may differ and must be checked separately."
            if english else
            "Dies sind nur Planungshinweise. Örtliche Regeln, Schutzverordnungen und Genehmigungen können abweichen und müssen separat geprüft werden."
        )
        QMessageBox.information(self, title, "\n".join(entries) + f"\n\n{notice}")

    def _start_context_geozone_check(self, coordinate):
        if not isinstance(coordinate, list) or len(coordinate) != 2:
            return
        try:
            lat, lon = float(coordinate[0]), float(coordinate[1])
        except (TypeError, ValueError):
            return
        delta = 0.00002
        probe = [(lat - delta, lon - delta), (lat - delta, lon + delta),
                 (lat + delta, lon + delta), (lat + delta, lon - delta)]
        self.statusBar().showMessage("Prüfe UAS-Geozonen an dieser Stelle …", 2500)
        threading.Thread(
            target=self._run_context_geozone_check,
            args=(probe,),
            name="acmp-context-geozone-check",
            daemon=True,
        ).start()

    def _run_context_geozone_check(self, probe: list[tuple[float, float]]):
        try:
            features = self._query_geozone_features(probe)
        except (OSError, ValueError, UnicodeError):
            features = []
        self.context_geozone_check_finished.emit(features)

    def _show_context_geozone_result(self, features: object):
        if not self.geozones_toggle.isChecked():
            return
        english = self.ui_language == "en"
        title = "What's here?" if english else "Was ist hier?"
        if not features:
            QMessageBox.information(
                self, title,
                "No configured UAS geozone was found at this position. A flight may be permitted, but you must still check applicable rules, NOTAMs and local conditions." if english
                else "An dieser Position wurde keine konfigurierte UAS-Geozone gefunden. Ein Flug kann zulässig sein; prüfe dennoch geltende Regeln, NOTAMs und die örtlichen Bedingungen.",
            )
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setMinimumSize(560, 360)
        layout = QVBoxLayout(dialog)
        heading = "The following UAS geozones apply at this position:" if english else "An dieser Position gelten folgende UAS-Geozonen:"
        layout.addWidget(QLabel(heading))
        details = QTextBrowser(dialog)
        details.setOpenExternalLinks(True)
        items = []
        for feature in features:
            properties = feature.get("properties", {})
            label = escape(str(properties.get("_acmp_label", "Unknown" if english else "Unbekannt")))
            reference = escape(str(properties.get("legal_ref", "")))
            raw_reference = str(properties.get("legal_ref", "")).lower()
            # § 21h ist die amtliche Regelgrundlage für die meisten festen UAS-Gebiete.
            law_url = "https://www.gesetze-im-internet.de/luftvo_2015/__21h.html"
            dfs_url = (
                "https://dfs.de/homepage/en/drone-flight/applications-and-approvals/"
                if english else "https://dfs.de/homepage/de/drohnenflug/antraege-und-genehmigungen/"
            )
            primary_url = law_url if "21h" in raw_reference else dfs_url
            primary_label = "Official rule text" if english else "Amtlicher Regeltext"
            line = f"<li><b>{label}</b>"
            if reference:
                line += f" – {reference}"
            line += f' – <a href="{primary_url}">{primary_label}</a>'
            if "21h" not in raw_reference:
                line += f' · <a href="{law_url}">LuftVO § 21h</a>'
            line += "</li>"
            items.append(line)
        notice = (
            "The links are provided for orientation. Please also check current NOTAMs, local requirements, approvals and obstacles; this is not a binding flight clearance."
            if english else
            "Die Links dienen der Orientierung. Prüfe zusätzlich aktuelle NOTAMs, örtliche Vorgaben, Freigaben und Hindernisse; dies ist keine verbindliche Flugfreigabe."
        )
        details.setHtml("<ul>" + "".join(items) + f"</ul><p>{escape(notice)}</p>")
        layout.addWidget(details)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok, parent=dialog)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)
        dialog.exec()

    @staticmethod
    def _geozone_feature_key(feature: dict, index: int) -> str:
        return str(feature.get("id") or f"{feature.get('properties', {}).get('_acmp_label', 'zone')}:{index}")

    def _show_geozone_check_result(self, check_id: int, features: object):
        """Lässt jede einzelne, tatsächlich berührte WFS-Fläche separat behandeln."""
        if not self.geozones_toggle.isChecked() or check_id != self._geozone_check_id or not features:
            return
        if self._geozone_review_dialog and self._geozone_review_dialog.isVisible():
            self._geozone_review_dialog.close()
        self._last_geozone_features = list(features)
        self._geozone_review_decisions = {
            self._geozone_feature_key(feature, index): "ignore"
            for index, feature in enumerate(self._last_geozone_features)
        }

    def _restore_last_flight_settings(self):
        """Stellt die zuletzt automatisch gespeicherten Flugeinstellungen wieder her."""
        raw = self.settings.value("last_flight_settings", "")
        if not raw:
            return
        try:
            values = json.loads(raw) if isinstance(raw, str) else raw
            if not isinstance(values, dict):
                return
            number_fields = [
                (self.altitude, "altitude"), (self.speed, "speed"), (self.curve_speed, "curve_speed"), (self.path_spacing, "path_spacing"),
                (self.direction, "direction"), (self.support_spacing, "support_spacing"), (self.overshoot_distance, "overshoot_distance"),
                (self.side_overlap, "side_overlap"), (self.forward_overlap, "forward_overlap"),
                (self.photo_distance, "photo_distance"), (self.gimbal_pitch, "gimbal_pitch"),
                (self.max_waypoints, "max_waypoints"), (self.max_flight_minutes, "max_flight_minutes"),
            ]
            for field, key in number_fields:
                if key in values:
                    field.setValue(float(values[key]))
            for field, key in [
                (self.direction_mode, "direction_mode"), (self.route_mode, "route_mode"),
                (self.waypoint_action, "waypoint_action"), (self.split_mode, "split_mode"),
                (self.finish_action, "finish_action"), (self.signal_loss_action, "signal_loss_action"),
                (self.outside_area_mode, "outside_area_mode"), (self.no_fly_mode, "no_fly_mode"),
            ]:
                if key in values and values[key] in [field.itemText(index) for index in range(field.count())]:
                    field.setCurrentText(values[key])
            if "outside_area_mode" in values:
                self._set_saved_outside_area_mode(values["outside_area_mode"])
            self.reduced_support_button.setChecked(bool(values.get("reduced_support_points", False)))
            self.keep_support_inside_button.setChecked(bool(values.get("keep_support_route_inside", False)))
            self.reduced_overshoot_button.setChecked(bool(values.get("reduced_overshoot_points", False)))
            self._direction_mode_changed(self.direction_mode.currentText())
            self._route_mode_changed(self.route_mode.currentText())
        except (TypeError, ValueError, json.JSONDecodeError):
            return

    def _connect_flight_settings_autosave(self):
        number_fields = [
            self.altitude, self.speed, self.curve_speed, self.path_spacing, self.direction, self.support_spacing, self.overshoot_distance,
            self.side_overlap, self.forward_overlap, self.photo_distance, self.gimbal_pitch,
            self.max_waypoints, self.max_flight_minutes,
        ]
        combo_fields = [
            self.direction_mode, self.route_mode, self.waypoint_action, self.split_mode,
            self.finish_action, self.signal_loss_action, self.outside_area_mode, self.no_fly_mode,
        ]
        for field in number_fields:
            field.valueChanged.connect(self._save_last_flight_settings)
        for field in combo_fields:
            field.currentTextChanged.connect(self._save_last_flight_settings)

    def _save_last_flight_settings(self, *_args):
        self.settings.setValue("last_flight_settings", json.dumps(self._preset_values(), ensure_ascii=False))
        self.settings.sync()
        self._geozone_review_base_zones = json.loads(json.dumps(self.no_fly_zones))
        self._geozone_review_base_names = list(self.no_fly_names)
        self.geozone_review_button.setEnabled(True)
        self._open_geozone_review()

    def _open_geozone_review(self):
        """Öffnet die letzte Konfliktprüfung erneut, ohne die Karte neu zu zeichnen."""
        if not self.geozones_toggle.isChecked():
            return
        if not self._last_geozone_features:
            if len(self.points) >= 3:
                self._queue_geozone_check()
            return
        if self._geozone_review_dialog and self._geozone_review_dialog.isVisible():
            self._geozone_review_dialog.raise_()
            self._geozone_review_dialog.activateWindow()
            return
        features = self._last_geozone_features
        decisions = self._geozone_review_decisions
        base_zones = self._geozone_review_base_zones
        base_names = self._geozone_review_base_names
        english = self.ui_language == "en"

        dialog = QDialog(self)
        dialog.setWindowTitle("Review UAS geozones" if english else "UAS-Geozonen prüfen")
        dialog.setWindowModality(Qt.WindowModality.NonModal)
        dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        dialog.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        dialog.setMinimumWidth(680)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(
            "Each intersecting official area can be ignored, highlighted or added as a no-fly zone independently. "
            "Changes are shown immediately on the map."
            if english else
            "Jede berührte offizielle Fläche kann unabhängig ignoriert, markiert oder als Sperrgebiet übernommen werden. "
            "Änderungen werden sofort auf der Karte angezeigt."
        ))
        table = QTableWidget(len(features), 2, dialog)
        table.setHorizontalHeaderLabels(["Intersecting area", "Action"] if english else ["Berührte Fläche", "Behandlung"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setColumnWidth(0, 420)
        table.horizontalHeader().setStretchLastSection(True)
        for index, feature in enumerate(features):
            key = self._geozone_feature_key(feature, index)
            label = feature.get("properties", {}).get("_acmp_label", "UAS-Geozone")
            identifier = feature.get("id", f"Fläche {index + 1}")
            table.setItem(index, 0, QTableWidgetItem(f"{label} · {identifier}"))
            choice = QComboBox(table)
            choice.addItem("Ignore" if english else "Ignorieren", "ignore")
            choice.addItem("Highlight area" if english else "Bereich markieren", "mark")
            choice.addItem("Add as no-fly zone" if english else "Als Sperrgebiet", "block")
            choice.setCurrentIndex({"ignore": 0, "mark": 1, "block": 2}[decisions[key]])
            choice.currentIndexChanged.connect(
                lambda _value, feature_key=key, combo=choice: self._change_geozone_decision(
                    feature_key, combo.currentData(), decisions, features, base_zones, base_names
                )
            )
            table.setCellWidget(index, 1, choice)
        layout.addWidget(table)
        layout.addWidget(QLabel(
            "Please check current geozones, NOTAMs, local laws, approvals and obstacles. "
            "This is not a binding flight clearance."
            if english else
            "Bitte prüfe aktuelle Geozonen, NOTAMs, lokale Gesetze, Freigaben und Hindernisse. "
            "Dies ist keine verbindliche Flugfreigabe."
        ))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok, parent=dialog)
        buttons.accepted.connect(dialog.close)
        layout.addWidget(buttons)
        self._geozone_review_dialog = dialog
        dialog.finished.connect(lambda _result: setattr(self, "_geozone_review_dialog", None))
        dialog.show()
        dialog.raise_()

    def _change_geozone_decision(
        self, key: str, decision: str, decisions: dict[str, str], features: list[dict],
        base_zones: list, base_names: list[str],
    ):
        decisions[key] = decision
        self._apply_geozone_decisions(features, decisions, base_zones, base_names)

    def _apply_geozone_decisions(
        self, features: list[dict], decisions: dict[str, str], base_zones: list, base_names: list[str],
    ):
        """Aktualisiert Markierungen und temporär hinzugefügte Sperrgebiete live."""
        visible_features: list[dict] = []
        additions: list[list[list[float]]] = []
        names: list[str] = []
        for index, feature in enumerate(features):
            decision = decisions[self._geozone_feature_key(feature, index)]
            if decision == "ignore":
                continue
            rendered = json.loads(json.dumps(feature))
            rendered.setdefault("properties", {})["_acmp_decision"] = decision
            visible_features.append(rendered)
            if decision == "block":
                label = feature.get("properties", {}).get("_acmp_label", "UAS-Geozone")
                for ring in self._feature_rings(feature):
                    if len(ring) >= 3:
                        additions.append([[lat, lon] for lat, lon in ring])
                        names.append(f"UAS: {label}")
        self.no_fly_zones = json.loads(json.dumps(base_zones)) + additions
        self.no_fly_names = list(base_names) + names
        self._no_fly_changed(self.no_fly_zones)
        self.js(f"setProjectGeometry({json.dumps(self.points)}, {json.dumps(self.no_fly_zones)});")
        self.js(f"showGeozoneConflicts({json.dumps(visible_features)});")

    def _polygon_changed(self, points: list):
        self.points = points
        if self._geozone_review_dialog and self._geozone_review_dialog.isVisible():
            self._geozone_review_dialog.close()
        self._last_geozone_features = []
        self._geozone_review_decisions = {}
        if hasattr(self, "geozone_review_button"):
            self.geozone_review_button.setEnabled(False)
        if self._canonical(self.direction_mode.currentText()) in {"Optimal (längste Kante)", "Optimal (längste Kante, umgekehrt)"}:
            self._direction_mode_changed(self.direction_mode.currentText())
        self.generated_route = []
        self.generated_missions = []
        self.force_single_mission = False
        if hasattr(self, "force_one_button"):
            self.force_one_button.setVisible(False)
        self.js("clearMission()")
        self.js("clearGeozoneConflicts()")
        self._refresh_geometry_ui()

    def _refresh_geometry_ui(self):
        """Aktualisiert die Gebietsinformationen ohne die aktuelle Route zu verwerfen."""
        points = self.points
        self.count_label.setText(f"Punkte: {len(points)}")
        area = polygon_area_m2(points)
        if len(points) < 3:
            self.area_label.setText("Fläche: — (mindestens 3 Punkte)")
        elif area >= 1_000_000:
            effective = max(0, area - sum(polygon_area_m2(zone) for zone in self.no_fly_zones))
            self.area_label.setText(
                f"Fläche: {area / 1_000_000:,.3f} km² (effektiv: {effective / 1_000_000:,.3f} km²)"
                .replace(",", "X").replace(".", ",").replace("X", ".")
            )
        else:
            effective = max(0, area - sum(polygon_area_m2(zone) for zone in self.no_fly_zones))
            self.area_label.setText(f"Fläche: {area:,.0f} m² (effektiv: {effective:,.0f} m²)".replace(",", "."))
        self.coordinates.setPlainText("\n".join(f"{lat:.7f}, {lon:.7f}" for lat, lon in points))
        self.zone_list.clear()
        for index, zone in enumerate(self.no_fly_zones, start=1):
            name = self.no_fly_names[index-1] if index <= len(self.no_fly_names) else f"Sperrgebiet {index}"
            self.zone_list.addItem(f"{name} · {polygon_area_m2(zone):,.0f} m²".replace(",", "."))
        self._update_zone_summary()

    def _no_fly_changed(self, zones: list):
        self.no_fly_zones = zones
        self.no_fly_names = (self.no_fly_names + [f"Sperrgebiet {index}" for index in range(len(self.no_fly_names)+1, len(zones)+1)])[:len(zones)]
        self.generated_route = []
        self.generated_missions = []
        self.force_single_mission = False
        if hasattr(self, "force_one_button"):
            self.force_one_button.setVisible(False)
        self.js("clearMission()")
        self._refresh_geometry_ui()

    def _update_zone_summary(self):
        active_area = polygon_area_m2(self.points)
        area_text = "—" if len(self.points) < 3 else f"{active_area:,.0f} m²".replace(",", ".")
        self.zone_summary.setText(f"Aktive Zone: {area_text} · Sperrgebiete: {len(self.no_fly_zones)}")

    def delete_selected_no_fly(self):
        row = self.zone_list.currentRow()
        if row >= 0:
            self.js(f"deleteNoFly({row})")

    def rename_no_fly_zone(self, item):
        row = self.zone_list.row(item)
        if row < 0 or row >= len(self.no_fly_names):
            return
        name, accepted = QInputDialog.getText(self, "Sperrgebiet umbenennen", "Name:", text=self.no_fly_names[row])
        if accepted and name.strip():
            self.no_fly_names[row] = name.strip()
            self._refresh_geometry_ui()

    def _planning_direction(self) -> float:
        if self._canonical(self.direction_mode.currentText()) == "Optimal (kürzeste Flugzeit)":
            self.statusBar().showMessage("Optimiere Bahnausrichtung …")
            angle = shortest_route_direction_deg(self.points, self.path_spacing.value(), self.no_fly_zones)
            self.direction.setValue(angle)
            return angle
        return self.direction.value()

    def _coverage_route(self) -> list[list[float]]:
        # "Durchfliegen" lässt Sperrgebiete bewusst bei der Bahnberechnung aus.
        zones = [] if self.no_fly_mode.currentText() == "Sperrgebiet durchfliegen" else self.no_fly_zones
        mode = self._canonical(self.route_mode.currentText())
        use_overshoot = mode == "Overshooting"
        self.overshoot_paths = []
        planning_area = self._inset_support_area() if mode == "Stützpunkte für geradere Bahnen" and self.keep_support_route_inside else self.points
        route = generate_lawnmower_route(
            planning_area, self.path_spacing.value(), self._planning_direction(), zones,
            use_overshoot or self.outside_area_mode.currentText() == "Außerhalb erlaubt",
        )
        if mode == "Stützpunkte für geradere Bahnen":
            route = densify_route(route, self.support_spacing.value(), self.reduced_support_points)
        elif use_overshoot:
            route, self.overshoot_paths = add_overshoot_turns(
                route, self.overshoot_distance.value(), self.reduced_overshoot_points
            )
        return route

    def _inset_support_area(self):
        """Inset the planning area by one support distance for the safety option."""
        latitude_origin = sum(point[0] for point in self.points) / len(self.points)
        longitude_origin = sum(point[1] for point in self.points) / len(self.points)
        latitude_scale = 111_132.92
        longitude_scale = 111_319.49 * math.cos(math.radians(latitude_origin))
        local = [((lon - longitude_origin) * longitude_scale, (lat - latitude_origin) * latitude_scale) for lat, lon in self.points]
        inset = Polygon(local).buffer(-self.support_spacing.value())
        if inset.is_empty:
            self.statusBar().showMessage("Sicherheitsabstand zu groß: Es wird die ursprüngliche Flugfläche verwendet.", 5000)
            return self.points
        if inset.geom_type == "MultiPolygon":
            inset = max(inset.geoms, key=lambda geometry: geometry.area)
        if inset.geom_type != "Polygon" or len(inset.exterior.coords) < 4:
            self.statusBar().showMessage("Flugfläche konnte nicht sicher verkleinert werden.", 5000)
            return self.points
        return [[latitude_origin + y / latitude_scale, longitude_origin + x / longitude_scale] for x, y in list(inset.exterior.coords)[:-1]]

    def _waypoint_speeds(self, route):
        """Assign the lower speed before, through and just after tight turns."""
        normal_speed = self.speed.value()
        speeds = [normal_speed] * len(route)
        if self._canonical(self.route_mode.currentText()) not in {"Stützpunkte für geradere Bahnen", "Overshooting"}:
            return speeds
        curve_indices = set()
        latitude_scale = 111_132.92
        for index in range(1, len(route) - 1):
            previous, point, following = route[index - 1:index + 2]
            longitude_scale = 111_319.49 * math.cos(math.radians(point[0]))
            incoming = ((point[0] - previous[0]) * latitude_scale, (point[1] - previous[1]) * longitude_scale)
            outgoing = ((following[0] - point[0]) * latitude_scale, (following[1] - point[1]) * longitude_scale)
            incoming_length, outgoing_length = math.hypot(*incoming), math.hypot(*outgoing)
            if not incoming_length or not outgoing_length:
                continue
            cosine = (incoming[0] * outgoing[0] + incoming[1] * outgoing[1]) / (incoming_length * outgoing_length)
            if cosine < math.cos(math.radians(12)):
                curve_indices.update(range(max(0, index - 1), min(len(route), index + 2)))
        for index in curve_indices:
            speeds[index] = min(normal_speed, self.curve_speed.value())
        return speeds

    def _overshoot_zone_feature(self):
        """Build the visible exterior flight-zone allowance around overshoot paths."""
        if not self.overshoot_paths or len(self.points) < 3:
            return None
        all_points = self.points + [point for path in self.overshoot_paths for point in path]
        latitude_origin = sum(point[0] for point in all_points) / len(all_points)
        longitude_origin = sum(point[1] for point in all_points) / len(all_points)
        latitude_scale = 111_132.92
        longitude_scale = 111_319.49 * math.cos(math.radians(latitude_origin))

        def local(point):
            return ((point[1] - longitude_origin) * longitude_scale, (point[0] - latitude_origin) * latitude_scale)

        corridor = unary_union([LineString([local(point) for point in path]) for path in self.overshoot_paths])
        # The cyan zone is deliberately 2 m wider than the planned exterior
        # path, but clipped so the original user-drawn flight area stays clear.
        exterior = corridor.buffer(self.overshoot_distance.value() + 2.0).difference(Polygon([local(point) for point in self.points]))
        if exterior.is_empty:
            return None

        def ring(coordinates):
            return [[longitude_origin + x / longitude_scale, latitude_origin + y / latitude_scale] for x, y in coordinates]

        def polygon_coordinates(polygon):
            return [ring(polygon.exterior.coords)] + [ring(interior.coords) for interior in polygon.interiors]

        if exterior.geom_type == "Polygon":
            geometry = {"type": "Polygon", "coordinates": polygon_coordinates(exterior)}
        elif exterior.geom_type == "MultiPolygon":
            geometry = {"type": "MultiPolygon", "coordinates": [polygon_coordinates(polygon) for polygon in exterior.geoms]}
        else:
            return None
        return {"type": "Feature", "properties": {"kind": "overshoot_zone"}, "geometry": geometry}

    def _show_missions(self, missions):
        labels=[]
        for index, mission in enumerate(missions, start=1):
            seconds=estimated_route_seconds(mission, self.speed.value(), self._turn_delay_seconds())
            minutes, remainder=divmod(round(seconds),60)
            labels.append(f"Mission {index} · {len(mission)} WP · ≈ {minutes}:{remainder:02d} min")
        estimated_paths = (
            [centripetal_catmull_rom_route(mission) for mission in missions]
            if self.flight_path_preview.isChecked() else []
        )
        self.js(
            f"showMissions({json.dumps(missions)}, {json.dumps(labels)}, "
            f"{json.dumps(estimated_paths)}, {json.dumps(self.overshoot_paths)}, "
            f"{json.dumps(self._overshoot_zone_feature())});"
        )


    def _turn_delay_seconds(self) -> float:
        return 3.0 if self._canonical(self.route_mode.currentText()) == "WPML gerade / Punktstopp (nicht garantiert)" else 0.0

    def generate_mission(self):
        if len(self.points) < 3:
            QMessageBox.warning(self, "Polygon fehlt", "Bitte zeichne zuerst mindestens drei Punkte im Tab „Fluggebiet planen“.")
            return
        self.force_single_mission = False
        self.force_one_button.setVisible(False)
        route = self._coverage_route()
        if len(route) < 2:
            QMessageBox.warning(self, "Keine Route", "Für dieses Polygon konnten keine gültigen Flugbahnen erzeugt werden.")
            return
        self.generated_route = route
        self.generated_missions = plan_missions(
            route, int(self.max_waypoints.value()), self.max_flight_minutes.value() * 60,
            self.speed.value(), self.split_mode.currentText(), self._turn_delay_seconds(),
        )
        if not self.generated_missions:
            self.js(f"showMission({json.dumps(route)})")
            self.mission_summary.setText(f"{len(route)} Wegpunkte · keine gültige Teilung mit den aktuellen Grenzen möglich.")
            self.waypoint_warning.setText("⚠ Fehler: Eine Teilmission würde das Wegpunkt- oder Flugzeitlimit überschreiten.")
            self.waypoint_warning.setStyleSheet("color:#b42318;font-weight:600;")
            return
        self._show_missions(self.generated_missions)
        distance = sum(route_length_m(mission) for mission in self.generated_missions)
        turn_delay_s = self._turn_delay_seconds() * sum(count_direction_changes(mission) for mission in self.generated_missions)
        duration_s = sum(estimated_route_seconds(mission, self.speed.value(), self._turn_delay_seconds()) for mission in self.generated_missions)
        minutes, seconds = divmod(round(duration_s), 60)
        action = self._canonical(self.waypoint_action.currentText())
        photo_hint = ""
        if action == "Foto nach Distanzintervall":
            photo_hint = f" · ca. {max(1, round(distance / self.photo_distance.value()))} Auslösungen"
        elif action == "Foto bei jedem Wegpunkt":
            photo_hint = f" · {len(route)} Auslösungen"
        self.mission_summary.setText(
            f"{len(route)} Wegpunkte · {len(self.generated_missions)} Mission(en) · {distance:,.0f} m Flugstrecke · ≈ {minutes}:{seconds:02d} min{photo_hint}"
            .replace(",", ".")
        )
        if turn_delay_s:
            self.mission_summary.setText(
                self.mission_summary.text() + f" (inkl. ≈ {turn_delay_s:.0f} s für {turn_delay_s // 3:.0f} Stopp-Drehungen)"
            )
        limit_reasons = []
        if len(route) > int(self.max_waypoints.value()):
            limit_reasons.append(f"{len(route)} Wegpunkte über dem Limit von {int(self.max_waypoints.value())}")
        if estimated_route_seconds(route, self.speed.value(), self._turn_delay_seconds()) > self.max_flight_minutes.value() * 60:
            limit_reasons.append(f"Flugzeit über {int(self.max_flight_minutes.value())} min pro Mission")
        if len(self.generated_missions) > 1:
            self.waypoint_warning.setText(
                f"✓ {len(self.generated_missions)} Teilmissionen benötigt: " + " und ".join(limit_reasons) + "."
            )
            self.waypoint_warning.setStyleSheet("color:#167a36;font-weight:600;")
            self.force_one_button.setVisible(True)
        elif len(route) > 60:
            self.waypoint_warning.setText(
                f"⚠ Hinweis: {len(route)} Wegpunkte. Über 60 Wegpunkte sind für die Planung nicht empfohlen, "
                "liegen aber innerhalb der eingestellten harten Grenzen."
            )
            self.waypoint_warning.setStyleSheet("color:#b36b00;font-weight:600;")
        else:
            self.waypoint_warning.setText(f"✓ Kompakte Route: {len(route)} Wegpunkte in {len(self.generated_missions)} Mission(en).")
            self.waypoint_warning.setStyleSheet("color:#167a36;font-weight:600;")

    def force_one_mission(self):
        """Übersteuert nur für diese Route die Teilungsgrenzen, ohne Eingabewerte zu ändern."""
        if len(self.generated_route) < 2:
            return
        self.force_single_mission = True
        self.generated_missions = [self.generated_route]
        self._show_missions(self.generated_missions)
        duration_s = estimated_route_seconds(self.generated_route, self.speed.value(), self._turn_delay_seconds())
        minutes, seconds = divmod(round(duration_s), 60)
        self.mission_summary.setText(
            f"{len(self.generated_route)} Wegpunkte · 1 erzwungene Mission · ≈ {minutes}:{seconds:02d} min"
        )
        exceeded = []
        if len(self.generated_route) > int(self.max_waypoints.value()):
            exceeded.append(f"{len(self.generated_route)} > {int(self.max_waypoints.value())} Wegpunkte")
        if duration_s > self.max_flight_minutes.value() * 60:
            exceeded.append(f"≈ {duration_s / 60:.1f} > {int(self.max_flight_minutes.value())} min")
        reason_text = " · ".join(exceeded) or "Teilungsgrenze der Routenplanung"
        self.waypoint_warning.setText("⚠ Erzwungen trotz Missionsgrenze: " + reason_text + ".")
        self.waypoint_warning.setStyleSheet("color:#b36b00;font-weight:600;")
        self.force_one_button.setVisible(False)

    def _export_missions(self) -> list[list[list[float]]]:
        if len(self.points) < 3:
            QMessageBox.warning(self, "Keine Route", "Bitte zeichne ein Gebiet und generiere zuerst eine Route.")
            return []
        self.generated_route = self._coverage_route()
        if self.force_single_mission:
            self.generated_missions = [self.generated_route]
        else:
            self.generated_missions = plan_missions(
                self.generated_route, int(self.max_waypoints.value()), self.max_flight_minutes.value() * 60,
                self.speed.value(), self.split_mode.currentText(), self._turn_delay_seconds(),
            )
        if not self.generated_missions:
            QMessageBox.warning(self, "Export nicht möglich", "Die Route kann unter den aktuellen Wegpunkt- und Flugzeitgrenzen nicht aufgeteilt werden.")
            return []
        return self.generated_missions

    def _write_kmz(self, destination: Path, route: list[list[float]]):
        finish_actions = {
            "Schweben am letzten Wegpunkt": "noAction",
            "Rückkehr zum Startpunkt (Home)": "goHome",
            "Landen am letzten Wegpunkt": "autoLand",
            "Zum ersten Wegpunkt": "gotoFirstWaypoint",
        }
        signal_loss_actions = {
            "Schweben": "hover",
            "Rückkehr zum Startpunkt (Home)": "goBack",
            "Landen": "landing",
        }
        build_dji_kmz(
            destination, route, self.altitude.value(), self.speed.value(), self.gimbal_pitch.value(),
            self.waypoint_action.currentText(), self.photo_distance.value(), self.route_mode.currentText(),
            finish_actions[self._canonical(self.finish_action.currentText())], signal_loss_actions[self._canonical(self.signal_loss_action.currentText())],
            self._waypoint_speeds(route),
        )
        return True

    def _preview_image(self, missions: list[list[list[float]]], include_title: bool) -> QImage:
        """Rendert eine kompakte, DJI-ähnliche Missionsübersicht als 400×300-JPEG."""
        width, height, margin = 400, 300, 24
        image = QImage(width, height, QImage.Format.Format_RGB32)
        image.fill(QColor("#f7f9fc"))
        all_points = self.points + [point for zone in self.no_fly_zones for point in zone] + [point for mission in missions for point in mission]
        min_lat, max_lat = min(point[0] for point in all_points), max(point[0] for point in all_points)
        min_lon, max_lon = min(point[1] for point in all_points), max(point[1] for point in all_points)
        lat_span, lon_span = max(max_lat - min_lat, 1e-8), max(max_lon - min_lon, 1e-8)
        draw_top = margin + (28 if include_title else 0)
        available_width, available_height = width - 2 * margin, height - draw_top - margin
        scale = min(available_width / lon_span, available_height / lat_span)
        content_width, content_height = lon_span * scale, lat_span * scale
        offset_x = margin + (available_width - content_width) / 2
        offset_y = draw_top + (available_height - content_height) / 2

        def project(point):
            lat, lon = point
            return offset_x + (lon - min_lon) * scale, offset_y + (max_lat - lat) * scale

        def draw_area(painter, points, fill, outline, thickness=2):
            if len(points) < 3:
                return
            path = QPainterPath()
            x, y = project(points[0])
            path.moveTo(x, y)
            for point in points[1:]:
                path.lineTo(*project(point))
            path.closeSubpath()
            painter.setPen(QPen(QColor(outline), thickness))
            painter.setBrush(QColor(fill))
            painter.drawPath(path)

        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if include_title:
            title = self.thumbnail_title.text().strip() or self.mission_name.text().strip() or "ACMP-Mission"
            painter.setPen(QColor("#172b4d"))
            painter.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
            painter.drawText(margin, 7, width - 2 * margin, 22, 0, title)
        draw_area(painter, self.points, QColor(65, 150, 255, 58), "#1261a0", 2)
        for zone in self.no_fly_zones:
            draw_area(painter, zone, QColor(220, 38, 38, 75), "#c92525", 2)
        colors = ["#d13c10", "#7b3fb2", "#087f5b", "#9a6700", "#1261a0"]
        for mission_index, mission in enumerate(missions):
            color = QColor(colors[mission_index % len(colors)])
            painter.setPen(QPen(color, 2))
            for first, second in zip(mission, mission[1:]):
                x1, y1 = project(first)
                x2, y2 = project(second)
                painter.drawLine(int(x1), int(y1), int(x2), int(y2))
            # Kleine Punkte bleiben bei vielen Wegpunkten lesbar; Start/Ende sind größer.
            for point_index, point in enumerate(mission):
                x, y = project(point)
                radius = 3 if point_index in (0, len(mission) - 1) else 1.5
                painter.setPen(QPen(QColor("white"), 1))
                painter.setBrush(color)
                painter.drawEllipse(int(x - radius), int(y - radius), int(radius * 2), int(radius * 2))
        painter.end()
        return image

    def export_preview_image(self, include_title: bool):
        missions = self._export_missions()
        if not missions:
            return
        default_name = "".join(char for char in self.mission_name.text().strip() if char.isalnum() or char in "-_ ") or "ACMP_Mission"
        suffix = "_Vorschau_mit_Name" if include_title else "_Vorschau"
        filename, _ = QFileDialog.getSaveFileName(
            self, "Vorschaubild speichern", f"{default_name}{suffix}.jpg", "JPEG-Bild (*.jpg *.jpeg)"
        )
        if not filename:
            return
        destination = Path(filename)
        if destination.suffix.lower() not in {".jpg", ".jpeg"}:
            destination = destination.with_suffix(".jpg")
        if not self._preview_image(missions, include_title).save(str(destination), "JPEG", 95):
            QMessageBox.critical(self, "Vorschau fehlgeschlagen", "Das JPEG-Vorschaubild konnte nicht gespeichert werden.")
            return
        QMessageBox.information(self, "Vorschaubild gespeichert", f"JPEG-Vorschau (400 × 300 Pixel) gespeichert:\n{destination}")

    @staticmethod
    def _point_in_polygon(point, polygon):
        lat, lon = point; inside = False
        for index, (a_lat, a_lon) in enumerate(polygon):
            b_lat, b_lon = polygon[(index + 1) % len(polygon)]
            if (a_lat > lat) != (b_lat > lat) and lon < (b_lon-a_lon)*(lat-a_lat)/(b_lat-a_lat)+a_lon:
                inside = not inside
        return inside

    def _export_validation_errors(self, missions):
        errors=[]; enforce_area=(
            self._canonical(self.outside_area_mode.currentText()).startswith("Im Flugbereich bleiben")
            and self._canonical(self.route_mode.currentText()) != "Overshooting"
        )
        enforce_zones=self.no_fly_mode.currentText()=="Sperrgebiet umfliegen"
        for mission_number, mission in enumerate(missions, 1):
            for point_number, point in enumerate(mission, 1):
                if enforce_area and not self._point_in_polygon(point, self.points):
                    errors.append(f"Mission {mission_number}, WP {point_number}: außerhalb des Flugbereichs")
                if enforce_zones and any(self._point_in_polygon(point, zone) for zone in self.no_fly_zones):
                    errors.append(f"Mission {mission_number}, WP {point_number}: im Sperrgebiet")
            for first, second in zip(mission, mission[1:]):
                for step in range(1, 25):
                    sample=[first[0]+(second[0]-first[0])*step/25, first[1]+(second[1]-first[1])*step/25]
                    if enforce_area and not self._point_in_polygon(sample, self.points): errors.append(f"Mission {mission_number}: Strecke verlässt Flugbereich"); break
                    if enforce_zones and any(self._point_in_polygon(sample, zone) for zone in self.no_fly_zones): errors.append(f"Mission {mission_number}: Strecke kreuzt Sperrgebiet"); break
        return list(dict.fromkeys(errors))

    def export_kmz_file(self):
        missions = self._export_missions()
        if not missions:
            return
        errors=self._export_validation_errors(missions)
        if errors:
            text="Die Routenprüfung hat folgende Abweichungen gefunden:\n\n"+"\n".join(errors[:8])
            if len(errors)>8: text+=f"\n… und {len(errors)-8} weitere."
            text+="\n\nTrotzdem exportieren?"
            if QMessageBox.question(self,"Routenprüfung",text,QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:
                return
        name = "".join(char for char in self.mission_name.text().strip() if char.isalnum() or char in "-_ ") or "ACMP_Mission"
        filename, _ = QFileDialog.getSaveFileName(self, "DJI-KMZ speichern", f"{name}.kmz", "DJI-Mission (*.kmz)")
        if not filename:
            return
        destination = Path(filename)
        if destination.suffix.lower() != ".kmz":
            destination = destination.with_suffix(".kmz")
        try:
            if len(missions) == 1:
                self._write_kmz(destination, missions[0])
            else:
                for index, mission in enumerate(missions, start=1):
                    self._write_kmz(destination.with_name(f"{destination.stem}_{index:02d}.kmz"), mission)
        except OSError as error:
            QMessageBox.critical(self, "Export fehlgeschlagen", f"Die KMZ-Datei konnte nicht gespeichert werden.\n\n{error}")
            return
        if len(missions) == 1:
            message = f"DJI-WPML-KMZ gespeichert:\n{destination}"
        else:
            message = f"{len(missions)} DJI-WPML-KMZ-Teilmissionen gespeichert:\n{destination.parent}"
        QMessageBox.information(self, "KMZ gespeichert", message)

    def use_current_location(self):
        self.js("""
        if (!navigator.geolocation) { alert('Standortfunktion wird von der Kartenansicht nicht unterstützt.'); }
        else navigator.geolocation.getCurrentPosition(
          position => goTo(position.coords.latitude, position.coords.longitude, 17),
          error => alert('Standort konnte nicht ermittelt werden. Bitte Standortfreigabe in Windows erlauben.')
        );
        """)

    def search(self):
        query = self.search_input.text().strip()
        if not query:
            self.search_input.setFocus()
            return
        self.search_input.setEnabled(False)
        self.search_input.setPlaceholderText("Suche läuft …")
        escaped = json.dumps(query)
        script = f"""
        fetch('https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&q=' + encodeURIComponent({escaped}), {{headers:{{'Accept-Language':'de'}}}})
          .then(r => r.json()).then(data => {{
            if (data.length) {{ goTo(parseFloat(data[0].lat), parseFloat(data[0].lon), 16); console.log('ACMP_SEARCH:ok'); }}
            else console.log('ACMP_SEARCH:none');
          }}).catch(() => console.log('ACMP_SEARCH:error'));
        """
        # Re-enable after a short, fixed browser-side delay. Search feedback remains non-blocking.
        self.js(script)
        self.search_input.setEnabled(True)
        self.search_input.setPlaceholderText("z. B. Brandenburger Tor, Berlin")

    def copy_coordinates(self):
        if not self.points:
            return
        QApplication.clipboard().setText(self.coordinates.toPlainText())
        self.statusBar().showMessage("Koordinaten wurden in die Zwischenablage kopiert.", 3000)

    def _show_about(self):
        QMessageBox.information(self, "ACMP", "ACMP – Aerial Capture Mission Planner\n\nDie optionalen UAS-Geozonen stammen aus dem dipul/DFS-WMS und dienen ausschließlich der Orientierung. Sie ersetzen keine verbindliche Prüfung aktueller Geozonen, NOTAMs, örtlicher Vorschriften, Freigaben oder Hindernisse.\n\nDer Betrieb erfolgt eigenverantwortlich; ACMP übernimmt keine Haftung für Flugplanung oder Flugdurchführung.")
