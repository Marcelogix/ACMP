"""Read-only access to DJI Fly waypoint missions on a Windows MTP/WPD device.

The DJI RC 2 normally has no drive letter.  Windows exposes it in its Portable
Devices namespace, which is also used by Explorer.  Keeping that Windows-shell
detail here prevents the UI and later export code from depending on MTP paths.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
from dataclasses import dataclass


WAYPOINT_PATH = ("Android", "data", "dji.go.v5", "files", "waypoint")


@dataclass(frozen=True)
class RC2Mission:
    device_name: str
    uuid: str
    kmz_name: str
    size_bytes: int | None
    modified: str


@dataclass(frozen=True)
class RC2ScanResult:
    devices: tuple[str, ...]
    missions: tuple[RC2Mission, ...]
    error: str | None = None
    waypoint_uuids: tuple[str, ...] = ()


class RC2Manager:
    """Encapsulates Windows Portable Devices (MTP/WPD) mission discovery."""

    def find_waypoint_missions(self) -> RC2ScanResult:
        if os.name != "nt":
            return RC2ScanResult((), (), "Der RC2-Scan ist nur unter Windows verfügbar.")
        try:
            records = self._run_windows_shell_scan()
        except (OSError, RuntimeError, subprocess.SubprocessError, ValueError, json.JSONDecodeError) as error:
            return RC2ScanResult((), (), f"Windows-MTP/WPD-Abfrage fehlgeschlagen: {error}")

        devices = tuple(dict.fromkeys(str(record.get("deviceName", "Unbekanntes Gerät")) for record in records))
        missions = tuple(
            RC2Mission(
                device_name=str(record.get("deviceName", "Unbekanntes Gerät")),
                uuid=str(record.get("uuid", "")),
                kmz_name=str(record.get("kmzName", "")),
                size_bytes=self._as_int(record.get("sizeBytes")),
                modified=str(record["modified"]) if record.get("modified") is not None else "",
            )
            for record in records
            if record.get("kmzName")
        )
        uuids = tuple(dict.fromkeys(str(record.get("uuid", "")) for record in records if record.get("uuid")))
        return RC2ScanResult(devices, missions, waypoint_uuids=uuids)

    def overwrite_mission_bundle(self, device_name: str, mission_uuid: str, kmz_path, preview_path) -> None:
        """Replace KMZ and JPEG within an existing DJI Fly mission slot."""
        if os.name != "nt":
            raise OSError("Der RC2-Upload ist nur unter Windows verfügbar.")
        kmz_path, preview_path = os.path.abspath(os.fspath(kmz_path)), os.path.abspath(os.fspath(preview_path))
        if not os.path.isfile(kmz_path) or not os.path.isfile(preview_path):
            raise OSError("KMZ- oder JPEG-Datei für den RC2-Upload fehlt.")
        def ps_literal(value: str) -> str:
            return "'" + str(value).replace("'", "''") + "'"
        device, uuid, kmz, preview = (ps_literal(value) for value in (device_name, mission_uuid, kmz_path, preview_path))
        script = rf'''
$ErrorActionPreference = 'Stop'
$shell = New-Object -ComObject Shell.Application
function Existing-Folder($parent, $name) {{
  $item = $parent.ParseName($name)
  if ($null -eq $item) {{ throw "DJI-Fly-Missionsordner nicht gefunden: $name" }}
  return $item.GetFolder()
}}
function Copy-IntoFolder($parent, $localPath) {{
  $sourceFolder = $shell.Namespace((Split-Path -Parent $localPath)); $fileName = Split-Path -Leaf $localPath
  if ($null -eq $sourceFolder) {{ throw "Lokaler Quellordner nicht verfügbar: $localPath" }}
  $source = $sourceFolder.ParseName($fileName)
  if ($null -eq $source) {{ throw "Lokale Datei nicht verfügbar: $fileName" }}
  # The RC2's MTP shell provider cancels silent replacements instead of
  # overwriting. Delete first, then wait until the provider exposes the slot
  # as free before copying the replacement.
  $oldFile = $parent.ParseName($fileName)
  if ($null -ne $oldFile) {{
    $oldFile.InvokeVerb('delete')
    for ($attempt = 0; $attempt -lt 50; $attempt++) {{ if ($null -eq $parent.ParseName($fileName)) {{ break }}; Start-Sleep -Milliseconds 200 }}
    if ($null -ne $parent.ParseName($fileName)) {{ throw "Bestehende RC2-Datei konnte nicht ersetzt werden: $fileName" }}
  }}
  $parent.CopyHere($source, 20)
  for ($attempt = 0; $attempt -lt 100; $attempt++) {{ if ($null -ne $parent.ParseName($fileName)) {{ return }}; Start-Sleep -Milliseconds 200 }}
  throw "Upload zum RC2 hat zu lange gedauert: $fileName"
}}
$computer = $shell.Namespace(17); $deviceItem = @($computer.Items() | Where-Object {{ $_.Name -eq {device} }} | Select-Object -First 1)
if ($null -eq $deviceItem) {{ throw 'Der RC2 ist nicht mehr verbunden.' }}
$root = $deviceItem.GetFolder(); $android = $root.ParseName('Android')
if ($null -eq $android) {{ foreach ($storage in @($root.Items())) {{ if ($storage.IsFolder) {{ $candidate = $storage.GetFolder().ParseName('Android'); if ($null -ne $candidate) {{ $android = $candidate; break }} }} }} }}
if ($null -eq $android) {{ throw 'Der Android-Speicher des RC2 ist nicht verfügbar.' }}
$waypoint = $android.GetFolder()
foreach ($part in @('data','dji.go.v5','files','waypoint')) {{ $item = $waypoint.ParseName($part); if ($null -eq $item) {{ throw "DJI-Fly-Pfad nicht gefunden: $part" }}; $waypoint = $item.GetFolder() }}
$missionFolder = Existing-Folder $waypoint {uuid}; Copy-IntoFolder $missionFolder {kmz}
$previewRoot = Existing-Folder $waypoint 'map_preview'; $previewFolder = Existing-Folder $previewRoot {uuid}; Copy-IntoFolder $previewFolder {preview}
'''
        encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        completed = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded], check=False, capture_output=True, text=False, timeout=50)
        if completed.returncode:
            raise OSError(self._decode_windows_output(completed.stderr).strip() or "Mission konnte nicht auf den RC2 hochgeladen werden.")

    def download_mission(self, mission: RC2Mission, destination) -> None:
        """Copy one KMZ from the RC2 WPD namespace into a caller-owned folder."""
        if os.name != "nt":
            raise OSError("Der RC2-Download ist nur unter Windows verfügbar.")
        destination = os.fspath(destination)
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        def ps_literal(value: str) -> str:
            return "'" + str(value).replace("'", "''") + "'"
        device_name, uuid, kmz_name, target = (ps_literal(value) for value in (mission.device_name, mission.uuid, mission.kmz_name, destination))
        script = rf'''
$ErrorActionPreference = 'Stop'
$shell = New-Object -ComObject Shell.Application
$computer = $shell.Namespace(17)
$device = @($computer.Items() | Where-Object {{ $_.Name -eq {device_name} }} | Select-Object -First 1)
if ($null -eq $device) {{ throw 'Der zuvor gefundene RC2 ist nicht mehr verbunden.' }}
$folder = $device.GetFolder(); $android = $folder.ParseName('Android')
if ($null -eq $android) {{ foreach ($storage in @($folder.Items())) {{ if ($storage.IsFolder) {{ $candidate = $storage.GetFolder().ParseName('Android'); if ($null -ne $candidate) {{ $android = $candidate; break }} }} }} }}
if ($null -eq $android) {{ throw 'Der Android-Speicher des RC2 ist nicht verfügbar.' }}
$folder = $android.GetFolder()
foreach ($part in @('data', 'dji.go.v5', 'files', 'waypoint', {uuid})) {{ $item = $folder.ParseName($part); if ($null -eq $item) {{ throw "Mission-Ordner nicht gefunden: $part" }}; $folder = $item.GetFolder() }}
$source = $folder.ParseName({kmz_name})
if ($null -eq $source) {{ throw 'Die ausgewählte KMZ-Datei wurde auf dem RC2 nicht gefunden.' }}
$targetPath = {target}; $targetDirectory = Split-Path -Parent $targetPath
$targetFolder = $shell.Namespace($targetDirectory)
if ($null -eq $targetFolder) {{ throw "Temporärer Zielordner konnte nicht geöffnet werden: $targetDirectory" }}
$targetFolder.CopyHere($source, 20)
for ($attempt = 0; $attempt -lt 75; $attempt++) {{ if (Test-Path -LiteralPath $targetPath) {{ exit 0 }}; Start-Sleep -Milliseconds 200 }}
throw 'Der KMZ-Download vom RC2 hat zu lange gedauert.'
'''
        encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        completed = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded], check=False, capture_output=True, text=False, timeout=20)
        if completed.returncode:
            message = self._decode_windows_output(completed.stderr).strip()
            raise OSError(message or "KMZ-Datei konnte nicht vom RC2 geladen werden.")

    @staticmethod
    def _as_int(value) -> int | None:
        try:
            number = int(value)
            # MTP commonly reports zero when a device does not publish a size.
            return number if number > 0 else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _decode_windows_output(value: bytes | None) -> str:
        """Decode PowerShell output without using the Windows ANSI code page."""
        text = (value or b"").decode("utf-8-sig", errors="replace")
        # PowerShell serializes non-interactive errors as CLIXML. Extracting
        # its error fields keeps an MTP failure readable in the Qt dialog.
        if "<Objs" in text and 'S="Error"' in text:
            import re
            errors = re.findall(r'<S S="Error">(.*?)</S>', text, flags=re.DOTALL)
            if errors:
                cleaned = re.sub(r"_x000D__x000A_", "\n", errors[0])
                return cleaned
        return text

    @staticmethod
    def _run_windows_shell_scan() -> list[dict]:
        # Shell.Application is the supported Explorer-facing WPD namespace. It
        # reaches MTP devices without relying on an assigned filesystem letter.
        script = r'''
$ErrorActionPreference = 'Stop'
$shell = New-Object -ComObject Shell.Application
$computer = $shell.Namespace(17)
if ($null -eq $computer) { throw 'Windows-Geräteansicht konnte nicht geöffnet werden.' }
$pathParts = @('Android', 'data', 'dji.go.v5', 'files', 'waypoint')
$result = @()
foreach ($device in @($computer.Items())) {
    if (-not $device.IsFolder) { continue }
    # Avoid opening every local/network drive. DJI RC 2 is presented by Windows
    # as a portable phone/MTP device; the name check remains locale-independent.
    $deviceType = [string]$device.Type
    if ($device.Name -notmatch '(?i)DJI\s*RC\s*2' -and $deviceType -notmatch '(?i)portable|mobiltelefon|phone|mtp') { continue }
    $currentFolder = $device.GetFolder()
    # Some Android devices expose an additional, localized storage level (for
    # example "Internal shared storage") before the actual Android folder.
    $androidItem = $currentFolder.ParseName('Android')
    if ($null -eq $androidItem) {
        foreach ($storage in @($currentFolder.Items())) {
            if (-not $storage.IsFolder) { continue }
            $candidate = $storage.GetFolder().ParseName('Android')
            if ($null -ne $candidate) { $androidItem = $candidate; break }
        }
    }
    if ($null -eq $androidItem) { continue }
    $currentFolder = $androidItem.GetFolder()
    $found = $true
    foreach ($part in $pathParts[1..($pathParts.Count - 1)]) {
        if ($null -eq $currentFolder) { $found = $false; break }
        $nextItem = $currentFolder.ParseName($part)
        if ($null -eq $nextItem) { $found = $false; break }
        $currentFolder = $nextItem.GetFolder()
    }
    if (-not $found -or $null -eq $currentFolder) { continue }
    foreach ($missionFolder in @($currentFolder.Items())) {
        if (-not $missionFolder.IsFolder) { continue }
        if ($missionFolder.Name -notmatch '^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$') { continue }
        $result += [PSCustomObject]@{ deviceName = $device.Name; uuid = $missionFolder.Name; kmzName = $null; sizeBytes = $null; modified = $null }
        $missionItems = $missionFolder.GetFolder()
        if ($null -eq $missionItems) { continue }
        foreach ($file in @($missionItems.Items())) {
            if ($file.IsFolder -or $file.Name -notmatch '(?i)\.kmz$') { continue }
            $size = $null
            try { $size = [int64]$file.Size } catch { }
            # ``ModifyDate`` is empty for many MTP providers.  The Shell
            # property system exposes the actual device timestamp separately.
            $modified = $null
            try { $modified = $file.ExtendedProperty('System.DateModified') } catch { }
            if ($null -eq $modified -or [string]::IsNullOrWhiteSpace([string]$modified)) {
                try { $modified = $file.ExtendedProperty('System.ItemDate') } catch { }
            }
            if ($modified -is [datetime]) { $modified = $modified.ToString('yyyy-MM-dd HH:mm:ss') }
            elseif ($null -ne $modified) { $modified = [string]$modified }
            if ([string]::IsNullOrWhiteSpace($modified)) { $modified = [string]$file.ModifyDate }
            # The MTP provider uses the OLE zero-date when it has no timestamp.
            if ($modified -match '(^|/)12/30/1899|(^|/)30\.12\.1899') { $modified = $null }
            $result += [PSCustomObject]@{
                deviceName = $device.Name
                uuid       = $missionFolder.Name
                kmzName    = $file.Name
                sizeBytes  = $size
                modified   = $modified
            }
        }
    }
}
@($result) | ConvertTo-Json -Compress -Depth 4
'''
        encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            check=False, capture_output=True, text=False, timeout=12,
        )
        if completed.returncode:
            message = RC2Manager._decode_windows_output(completed.stderr).strip() or "PowerShell konnte die Windows-Geräteansicht nicht abfragen."
            raise RuntimeError(message)
        output = RC2Manager._decode_windows_output(completed.stdout).strip()
        if not output or output == "null":
            return []
        decoded = json.loads(output)
        return decoded if isinstance(decoded, list) else [decoded]


__all__ = ["RC2Manager", "RC2Mission", "RC2ScanResult", "WAYPOINT_PATH"]
