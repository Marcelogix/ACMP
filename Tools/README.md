# Tools

## RC Remote Tool

`run_rc_remote_tool.bat` starten oder aus dem Projektordner ausführen:

```powershell
python Tools\rc_remote_tool.py
```

Das Werkzeug ist schreibgeschützt: Es sucht DJI-RC-2-Missionsslots über
Windows-MTP, lädt eine ausgewählte KMZ temporär herunter, zeigt genau diese
eine Mission georeferenziert auf OpenStreetMap an und zoomt auf deren gesamte
Ausdehnung. **Ausgewählte KMZ debuggen** öffnet den Inhalt des KMZ-ZIP-Archivs
und formatiert KML/WPML als lesbaren XML-Text.
