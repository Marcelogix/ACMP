"""Portable DJI WPML/KMZ export service."""
from __future__ import annotations
import time
import zipfile
from pathlib import Path
from acmp.i18n import canonical_ui_text

def build_dji_kmz(destination: Path, route, altitude_m, speed_mps, gimbal_pitch, photo_mode, photo_distance_m, route_mode, finish_action, signal_loss_action, waypoint_speeds=None, use_point_gimbal_pitch=True):
    if len(route) < 2: raise ValueError("Mindestens zwei Wegpunkte werden benötigt.")
    photo_mode=canonical_ui_text(photo_mode); route_mode=canonical_ui_text(route_mode); stamp=int(time.time()*1000)
    turn="toPointAndStopWithDiscontinuityCurvature" if route_mode=="WPML gerade / Punktstopp (nicht garantiert)" else "toPointAndPassWithContinuityCurvature"
    config=f"<wpml:missionConfig><wpml:flyToWaylineMode>safely</wpml:flyToWaylineMode><wpml:finishAction>{finish_action}</wpml:finishAction><wpml:exitOnRCLost>executeLostAction</wpml:exitOnRCLost><wpml:executeRCLostAction>{signal_loss_action}</wpml:executeRCLostAction><wpml:takeOffSecurityHeight>20</wpml:takeOffSecurityHeight><wpml:globalTransitionalSpeed>{speed_mps:.1f}</wpml:globalTransitionalSpeed></wpml:missionConfig>"
    if waypoint_speeds is None: waypoint_speeds=[speed_mps]*len(route)
    if len(waypoint_speeds)!=len(route): raise ValueError("Für jeden Wegpunkt muss eine Geschwindigkeit vorhanden sein.")
    marks=[]
    for i,(lat,lon) in enumerate(route):
        action=""
        if photo_mode=="Foto bei jedem Wegpunkt": action=f"<wpml:actionGroup><wpml:actionGroupId>{i}</wpml:actionGroupId><wpml:actionGroupStartIndex>{i}</wpml:actionGroupStartIndex><wpml:actionGroupEndIndex>{i}</wpml:actionGroupEndIndex><wpml:actionGroupMode>sequence</wpml:actionGroupMode><wpml:actionTrigger><wpml:actionTriggerType>reachPoint</wpml:actionTriggerType></wpml:actionTrigger><wpml:action><wpml:actionId>0</wpml:actionId><wpml:actionActuatorFunc>takePhoto</wpml:actionActuatorFunc><wpml:actionActuatorFuncParam><wpml:payloadPositionIndex>0</wpml:payloadPositionIndex></wpml:actionActuatorFuncParam></wpml:action></wpml:actionGroup>"
        waypoint_speed=min(float(speed_mps),max(.5,float(waypoint_speeds[i])))
        # DJI Fly's own working missions rotate the gimbal through an explicit
        # action at waypoint 0.  A bare point-pitch tag is not equivalent on
        # all controllers and can be ignored by DJI Fly.
        gimbal_action = ""
        if i == 0 and use_point_gimbal_pitch:
            gimbal_action = (
                "<wpml:actionGroup><wpml:actionGroupId>10000</wpml:actionGroupId>"
                "<wpml:actionGroupStartIndex>0</wpml:actionGroupStartIndex><wpml:actionGroupEndIndex>0</wpml:actionGroupEndIndex>"
                "<wpml:actionGroupMode>parallel</wpml:actionGroupMode><wpml:actionTrigger><wpml:actionTriggerType>reachPoint</wpml:actionTriggerType></wpml:actionTrigger>"
                "<wpml:action><wpml:actionId>0</wpml:actionId><wpml:actionActuatorFunc>gimbalRotate</wpml:actionActuatorFunc>"
                "<wpml:actionActuatorFuncParam><wpml:gimbalHeadingYawBase>aircraft</wpml:gimbalHeadingYawBase>"
                "<wpml:gimbalRotateMode>absoluteAngle</wpml:gimbalRotateMode><wpml:gimbalPitchRotateEnable>1</wpml:gimbalPitchRotateEnable>"
                f"<wpml:gimbalPitchRotateAngle>{gimbal_pitch:.1f}</wpml:gimbalPitchRotateAngle>"
                "<wpml:gimbalRollRotateEnable>0</wpml:gimbalRollRotateEnable><wpml:gimbalRollRotateAngle>0</wpml:gimbalRollRotateAngle>"
                "<wpml:gimbalYawRotateEnable>0</wpml:gimbalYawRotateEnable><wpml:gimbalYawRotateAngle>0</wpml:gimbalYawRotateAngle>"
                "<wpml:gimbalRotateTimeEnable>0</wpml:gimbalRotateTimeEnable><wpml:gimbalRotateTime>0</wpml:gimbalRotateTime>"
                "<wpml:payloadPositionIndex>0</wpml:payloadPositionIndex></wpml:actionActuatorFuncParam></wpml:action></wpml:actionGroup>"
            )
        marks.append(f"<Placemark><Point><coordinates>{lon:.8f},{lat:.8f}</coordinates></Point><wpml:index>{i}</wpml:index><wpml:executeHeight>{altitude_m:.1f}</wpml:executeHeight><wpml:waypointSpeed>{waypoint_speed:.1f}</wpml:waypointSpeed><wpml:waypointTurnParam><wpml:waypointTurnMode>{turn}</wpml:waypointTurnMode><wpml:waypointTurnDampingDist>0</wpml:waypointTurnDampingDist></wpml:waypointTurnParam>{gimbal_action}{action}</Placemark>")
    interval=""
    if photo_mode=="Foto nach Distanzintervall": interval=f"<wpml:actionGroup><wpml:actionGroupId>0</wpml:actionGroupId><wpml:actionGroupStartIndex>0</wpml:actionGroupStartIndex><wpml:actionGroupEndIndex>{len(route)-1}</wpml:actionGroupEndIndex><wpml:actionGroupMode>sequence</wpml:actionGroupMode><wpml:actionTrigger><wpml:actionTriggerType>multipleDistance</wpml:actionTriggerType><wpml:actionTriggerParam>{photo_distance_m:.1f}</wpml:actionTriggerParam></wpml:actionTrigger><wpml:action><wpml:actionId>0</wpml:actionId><wpml:actionActuatorFunc>takePhoto</wpml:actionActuatorFunc><wpml:actionActuatorFuncParam><wpml:payloadPositionIndex>0</wpml:payloadPositionIndex></wpml:actionActuatorFuncParam></wpml:action></wpml:actionGroup>"
    ns='xmlns="http://www.opengis.net/kml/2.2" xmlns:wpml="http://www.dji.com/wpmz/1.0.2"'
    folder=f"<Folder><wpml:templateId>0</wpml:templateId><wpml:waylineId>0</wpml:waylineId><wpml:autoFlightSpeed>{speed_mps:.1f}</wpml:autoFlightSpeed>{interval}{''.join(marks)}</Folder>"
    xml=f'<?xml version="1.0" encoding="UTF-8"?><kml {ns}><Document><wpml:createTime>{stamp}</wpml:createTime>{config}{folder}</Document></kml>'
    with zipfile.ZipFile(destination,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("wpmz/template.kml",xml); z.writestr("wpmz/waylines.wpml",xml)

__all__ = ["build_dji_kmz"]
