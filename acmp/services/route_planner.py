"""Pure geometry and route-planning functions."""
from __future__ import annotations
import math

def polygon_area_m2(points):
    if len(points) < 3: return 0.0
    radius, total = 6_378_137.0, 0.0
    for i, (lat1, lon1) in enumerate(points):
        lat2, lon2 = points[(i + 1) % len(points)]
        total += math.radians(lon2-lon1)*(2+math.sin(math.radians(lat1))+math.sin(math.radians(lat2)))
    return abs(total)*radius*radius/2

def route_length_m(route):
    radius,total=6_378_137.0,0.0
    for (a,b),(c,d) in zip(route,route[1:]):
        x,y=math.radians(c-a),math.radians(d-b); h=math.sin(x/2)**2+math.cos(math.radians(a))*math.cos(math.radians(c))*math.sin(y/2)**2
        total += 2*radius*math.asin(math.sqrt(h))
    return total

def count_direction_changes(route):
    count=0
    for a,b,c in zip(route,route[1:],route[2:]):
        x=(b[1]-a[1],b[0]-a[0]); y=(c[1]-b[1],c[0]-b[0]); m=math.hypot(*x)*math.hypot(*y)
        if m and (x[0]*y[0]+x[1]*y[1])/m < .7: count+=1
    return count

def estimated_route_seconds(route,speed_mps,turn_delay_s=0): return route_length_m(route)/speed_mps+count_direction_changes(route)*turn_delay_s
def optimal_direction_deg(points):
    if len(points)<2:return 0.0
    scale=math.cos(math.radians(sum(p[0] for p in points)/len(points)))
    _,x,y=max((math.hypot((b[1]-a[1])*scale,b[0]-a[0]),(b[1]-a[1])*scale,b[0]-a[0]) for a,b in zip(points,points[1:]+points[:1]))
    return math.degrees(math.atan2(y,x))%180
def generate_lawnmower_route(points,spacing_m,direction_deg,no_fly_zones=None,allow_outside=False):
    if len(points)<3:return []
    lat0,lon0=sum(p[0] for p in points)/len(points),sum(p[1] for p in points)/len(points); latm=111132.92; lonm=111319.49*math.cos(math.radians(lat0)); a=math.radians(direction_deg); c,s=math.cos(a),math.sin(a)
    def rotate(zone):
        return [((lon-lon0)*lonm*c+(lat-lat0)*latm*s,-(lon-lon0)*lonm*s+(lat-lat0)*latm*c) for lat,lon in zone]
    poly=rotate(points)
    blocked=[rotate(zone) for zone in (no_fly_zones or []) if len(zone)>=3]
    def local_inside(u,v):
        hit=False
        for i,(u1,v1) in enumerate(poly):
            u2,v2=poly[(i+1)%len(poly)]
            if (v1>v)!=(v2>v) and u < (u2-u1)*(v-v1)/(v2-v1)+u1: hit=not hit
        return hit
    def spans(v, polygon):
        h=[]
        for i,(u1,v1) in enumerate(polygon):
            u2,v2=polygon[(i+1)%len(polygon)]
            if (v1<=v<v2)or(v2<=v<v1):h.append(u1+(v-v1)*(u2-u1)/(v2-v1))
        h.sort();return [(h[i],h[i+1]) for i in range(0,len(h)-1,2)]
    lo,hi=min(p[1] for p in poly),max(p[1] for p in poly); out=[]
    for row in range(max(1,math.ceil((hi-lo)/spacing_m))+1):
        v=lo+min(row*spacing_m,hi-lo); seg=spans(v, poly)
        # Schneidet Sperrgebiete mit zwei Metern Sicherheitszugabe aus jeder Bahn.
        for zone in blocked:
            for block_start, block_end in spans(v, zone):
                remaining=[]
                for start,end in seg:
                    if block_end+2 <= start or block_start-2 >= end:
                        remaining.append((start,end))
                    else:
                        if start < block_start-2: remaining.append((start,block_start-2))
                        if block_end+2 < end: remaining.append((block_end+2,end))
                seg=remaining
        seg=[(b,a) for a,b in reversed(seg)] if row%2 else seg
        previous_end=None
        for u1,u2 in seg:
            # Zwei getrennte Teilstücke derselben Bahn dürfen nicht direkt
            # verbunden werden: Die Verbindung wird außen um das Sperrgebiet geführt.
            if previous_end is not None:
                for zone in blocked:
                    crossing=any(min(previous_end,u1)<end and max(previous_end,u1)>start for start,end in spans(v,zone))
                    if crossing:
                        low,high=min(p[1] for p in zone),max(p[1] for p in zone)
                        candidates=[low-2, high+2]
                        # Bevorzugt die kürzere Seite, aber nur wenn beide
                        # zusätzlichen Umwegpunkte innerhalb der Außenfläche liegen.
                        candidates.sort(key=lambda value: abs(v-value))
                        detour_v=next((value for value in candidates if all(local_inside(u,value) for u in (previous_end,u1))), None)
                        if detour_v is None:
                            # Keine sichere Umfahrung auf dieser Seite: Die
                            # Außenflächen-Verbindung wird später über Kanten
                            # aufgelöst, statt den Flugbereich zu verlassen.
                            break
                        for u in (previous_end,u1):
                            x,y=u*c-detour_v*s,u*s+detour_v*c;out.append([lat0+y/latm,lon0+x/lonm])
                        break
            for u in (u1,u2):
                x,y=u*c-v*s,u*s+v*c;out.append([lat0+y/latm,lon0+x/lonm])
            previous_end=u2
    # Jede Verbindung wird danach geprüft. Bei konkaven Flächen (z. B. U-Form)
    # darf die Drohne nicht quer durch den ausgesparten Bereich abkürzen.
    def inside(point, polygon):
        x,y=point[1],point[0]; hit=False
        for i,(py,px) in enumerate(polygon):
            qy,qx=polygon[(i+1)%len(polygon)]
            if min(px,qx)-1e-10<=x<=max(px,qx)+1e-10 and min(py,qy)-1e-10<=y<=max(py,qy)+1e-10:
                if abs((qx-px)*(y-py)-(qy-py)*(x-px))<1e-10:return True
            if (py>y)!=(qy>y) and x < (qx-px)*(y-py)/(qy-py)+px: hit=not hit
        return hit
    def allowed(a,b):
        # Mehrere Proben erkennen auch Verbindungen, die aus einer konkaven
        # Fläche hinaus und später wieder hinein führen.
        for i in range(1,25):
            t=i/25; p=[a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t]
            if not inside(p,points) or any(inside(p,z) for z in (no_fly_zones or [])): return False
        return True
    def distance(a,b): return math.hypot((a[0]-b[0])*latm,(a[1]-b[1])*lonm)
    def detour(start,end):
        if allowed(start,end): return [end]
        # Sichtbarkeitsgraph aus Außenkanten und 2-m-versetzten
        # Sperrgebietsecken. Die versetzten Ecken verhindern einen Weg genau
        # auf der Sperrgebietsgrenze.
        nodes=[start,end]+points[:]
        for zone in no_fly_zones or []:
            center_lat=sum(p[0] for p in zone)/len(zone); center_lon=sum(p[1] for p in zone)/len(zone)
            for lat,lon in zone:
                dx,dy=lon-center_lon,lat-center_lat; length=math.hypot(dx,dy) or 1.0
                candidate=[lat+dy/length*2/111132.92, lon+dx/length*2/(111319.49*math.cos(math.radians(lat)))]
                if inside(candidate,points) and not any(inside(candidate,z) for z in (no_fly_zones or [])):
                    nodes.append(candidate)
        edges=[[] for _ in nodes]
        for i in range(len(nodes)):
            for j in range(i+1,len(nodes)):
                if allowed(nodes[i],nodes[j]):
                    d=distance(nodes[i],nodes[j]); edges[i].append((j,d)); edges[j].append((i,d))
        best=[float('inf')]*len(nodes); previous=[None]*len(nodes); best[0]=0; pending=set(range(len(nodes)))
        while pending:
            current=min(pending,key=lambda n:best[n]); pending.remove(current)
            if current==1 or best[current]==float('inf'): break
            for nxt,cost in edges[current]:
                if nxt in pending and best[current]+cost<best[nxt]: best[nxt]=best[current]+cost; previous[nxt]=current
        if previous[1] is None: return [end]  # Ungültige Geometrie; keine künstliche Route erfinden.
        path=[]; current=1
        while current is not None: path.append(nodes[current]); current=previous[current]
        return list(reversed(path))[1:]
    if allow_outside:
        # Die Abdeckungsbahnen behalten ihre Endpunkte am Flächenrand; die
        # Verbindung zwischen getrennten Armen darf direkt außerhalb erfolgen.
        return out
    safe=[out[0]] if out else []
    for point in out[1:]: safe.extend(detour(safe[-1],point))
    return safe
def densify_route(route,maximum_segment_m): return route
def shortest_route_direction_deg(points,spacing_m,no_fly_zones=None): return min(range(180),key=lambda x:route_length_m(generate_lawnmower_route(points,spacing_m,x,no_fly_zones))) if len(points)>=3 else 0
def plan_missions(route,max_points,max_seconds,speed_mps,mode,turn_delay_s=0):
    if len(route)<2:return []
    result=[];current=[route[0]]
    for p in route[1:]:
        if len(current)+1>max_points or estimated_route_seconds(current+[p],speed_mps,turn_delay_s)>max_seconds:
            if len(current)<2:return []
            result.append(current);current=[p]
        else:current.append(p)
    return result+[current] if len(current)>=2 else result

__all__ = [
    "count_direction_changes", "densify_route", "estimated_route_seconds",
    "generate_lawnmower_route", "optimal_direction_deg", "plan_missions",
    "polygon_area_m2", "route_length_m", "shortest_route_direction_deg",
]
