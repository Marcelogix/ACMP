# ACMP – Polygon-Karte für DJI-Missionsvorbereitung

Eine kleine Desktop-Anwendung zum Suchen von Adressen und Einzeichnen eines Gebiets auf einer interaktiven Karte.

## Start

```powershell
py -3.12 -m pip install -r requirements.txt
py -3.12 main.py
```

## Struktur und EXE-Build

Die Startdatei [`main.py`](main.py) ist bewusst schlank; die Anwendung liegt als Paket unter [`acmp/`](acmp/). Die Qt-Oberfläche liegt in [`acmp/ui/main_window.py`](acmp/ui/main_window.py), Sprachhilfen in [`acmp/i18n.py`](acmp/i18n.py).

Für eine Windows-EXE kann optional [`build_exe.bat`](build_exe.bat) gestartet werden. Das Skript installiert bei Bedarf PyInstaller und erzeugt anschließend `dist\ACMP\ACMP.exe` im robusteren *one-folder*-Format. Die erzeugten Ordner `build/`, `dist/` und die Datei `ACMP.spec` gehören nicht in Git.

Beim ersten Start benötigt die Karte eine Internetverbindung (Kartenkacheln und die Adresssuche werden online geladen).

## Bedienung

1. Im Tab **Karte & Gebiet** Adresse bzw. Ort eingeben und auf **Suchen** drücken; **Mein Standort** zentriert die Karte nach Freigabe des Windows-Standorts.
2. Mit **Polygon** Punkte per Linksklick setzen. Für eine schnellere Flugzone stehen daneben **Rechteck** und **Kreis** bereit; auf der Karte jeweils klicken, gedrückt halten und aufziehen.
3. Ab dem dritten Punkt erscheint die geschlossene Fläche automatisch. Mit **Punkt rückgängig** oder **Alles löschen** lässt sie sich anpassen.
4. Mit **Sperrgebiet zeichnen** lassen sich mehrere rote Ausschlussflächen anlegen. Jedes kann in der Liste einzeln ausgewählt und gelöscht werden; die Berechnung lässt dort keine Abdeckungswegpunkte entstehen und führt geteilte Bahnen mit einem kleinen Randabstand außen herum.
5. Im Tab **Flugeinstellungen** Höhe, Geschwindigkeit, Bahnabstand und Richtung festlegen. **Route generieren** zeichnet die resultierende Zickzack-Route mit nummerierten, gerichteten Wegpunkten auf der Karte.
6. Die Planung prüft Wegpunktzahl und Flugzeit je Teilmission. Über 60 Wegpunkte erscheint ein orangefarbener Hinweis; eine Teilung erfolgt erst beim Überschreiten einer dieser harten Grenzen. Bei Bedarf wird die Route nach der gewählten Methode auf mehrere zusammenhängende Teilmissionen verteilt. Kameraauslösung, Überlappungen und Gimbal-Neigung sind für den späteren DJI/KMZ-Export hinterlegt.
7. Im Tab **Exportieren** lässt sich eine DJI-WPML-KMZ speichern. Bei per USB angeschlossenen DJI-RC-Controllern erfolgt der anschließende Import über die Dateiverwaltung bzw. die DJI-App.
8. Über **Datei → Speichern unter …** wird ein bearbeitbares ACMP-Projekt (`.acmp.json`) mit Fluggebiet, Sperrgebieten, Flugeinstellungen, Exportnamen und der gegebenenfalls bereits erzeugten Route gespeichert. Mit **Datei → Öffnen …** kann es später wiederhergestellt werden.

Die Punkte werden im WGS84-Format (`latitude`, `longitude`) gehalten – die übliche Grundlage für spätere DJI-/KMZ-Exportfunktionen. Die aktuelle Route ist eine visuelle Planungsroute; vor einem Drohnenflug müssen Fluggerät, Kamera, örtliche Vorschriften, Hindernisse und die erzeugte KMZ-Mission geprüft werden.

Ein direkter Dateizugriff auf den Controller ist nicht enthalten: Windows bindet viele DJI-RC-Controller als Android-MTP-Gerät und nicht als normalen Dateisystempfad ein. Vor dem Einsatz die Mission in DJI Fly bzw. DJI Pilot prüfen.

Für die Bahnrichtung stehen feste Himmelsrichtungen, eine eigene Gradzahl sowie zwei Optimierungen zur Verfügung: **Optimal (längste Kante)** ist eine schnelle Heuristik; **Optimal (kürzeste Flugzeit)** bewertet die erzeugte Route inklusive Sperrgebiets-Umwegen über alle Ausrichtungen und wählt die kürzeste. Bei konstanter Geschwindigkeit entspricht sie der kürzesten Flugzeit. Über die obere Leiste lassen sich Flugeinstellungen als benannte Presets speichern und laden.

Unter **Routenmodus** kann zwischen glatten DJI-Kurven, dem WPML-Modus mit Punktstopp (modellabhängig) und zusätzlichen Stützpunkten gewählt werden. Der Stützpunktmodus nähert die Sollbahn an, erhöht aber Wegpunktzahl und kann dadurch weitere Teilmissionen erzeugen. Für den Punktstoppmodus rechnet die Zeitprognose mit einem sichtbaren, groben Zuschlag von etwa drei Sekunden pro deutlichem Richtungswechsel.

Unter **Missionsgrenze** lassen sich außerdem die Aktion bei Flugende (Home, Schweben, Landen oder erster Wegpunkt) und bei Signalverlust (Home, Schweben oder Landen) festlegen. Diese Einstellungen werden als WPML-Missionsparameter exportiert; der Controller bzw. die Drohne kann sie abhängig von Modell, Firmware und Sicherheitsvorgaben abweichend behandeln.

Der Export-Tab erzeugt auf Wunsch ein JPEG-Vorschaubild in 400 × 300 Pixeln – optional mit einem separat eingegebenen, längeren Vorschaunamen. Es ist für die Zuordnung zu einer DJI-Fly-Mission gedacht; DJI Fly aktualisiert sein internes Thumbnail nach einem externen KMZ-Austausch nicht zwingend automatisch.

## Hinweis zur Suche

Die Suchfunktion verwendet den öffentlichen Nominatim-Dienst von OpenStreetMap. Bitte keine automatisierten Massenanfragen ausführen.
