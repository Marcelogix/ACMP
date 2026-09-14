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
    # A direction derived from the longest edge can differ by a few
    # centimetres because the local longitude scale is an approximation. Snap
    # near-equal extreme values so that edge is treated as one full first pass,
    # rather than as a short line growing out of one corner.
    raw_lo, raw_hi = min(point[1] for point in poly), max(point[1] for point in poly)
    boundary_tolerance_m = 0.25
    poly=[
        (u, raw_lo if abs(v - raw_lo) <= boundary_tolerance_m else raw_hi if abs(v - raw_hi) <= boundary_tolerance_m else v)
        for u, v in poly
    ]
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
        v=lo+min(row*spacing_m,hi-lo)
        if row == 0 and hi > lo:
            # The first pass must run alongside the lowest boundary, not start
            # at a single corner.  A 1-cm inward offset avoids floating-point
            # ambiguity when that boundary is parallel to the chosen direction.
            v += min(0.01, (hi-lo) / 2)
        seg=spans(v, poly)
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
        # Tangential contacts at a single vertex are not scan paths.
        seg=[(start,end) for start,end in seg if abs(end-start) > 0.05]
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
    # A scanline that only touches a polygon vertex can produce two identical
    # endpoints.  Besides being a useless waypoint, that zero-length segment
    # prevents the first/second-row overshoot turn from being recognised.
    deduplicated=[]
    for point in out:
        if not deduplicated or distance(deduplicated[-1], point) > 0.05:
            deduplicated.append(point)
    out=deduplicated
    if allow_outside:
        # Die Abdeckungsbahnen behalten ihre Endpunkte am Flächenrand; die
        # Verbindung zwischen getrennten Armen darf direkt außerhalb erfolgen.
        return out
    safe=[out[0]] if out else []
    for point in out[1:]: safe.extend(detour(safe[-1],point))
    return safe
def densify_route(route, support_distance_m, reduced=False, return_curve_speed_indices=False):
    """Add one support waypoint before and after each genuine route turn.

    Unlike ordinary densification, straight survey passes stay untouched.  The
    two extra points sit on the incoming/outgoing path around a turn and help
    smoothing controllers begin and finish the turn nearer its intended place.
    """
    if len(route) < 3 or support_distance_m <= 0:
        result=[point[:] for point in route]
        return (result, set()) if return_curve_speed_indices else result
    latitude_scale = 111_132.92

    def vector(start, end):
        longitude_scale = 111_319.49 * math.cos(math.radians((start[0] + end[0]) / 2))
        return ((end[0] - start[0]) * latitude_scale, (end[1] - start[1]) * longitude_scale)

    def interpolate(start, end, fraction):
        return [
            start[0] + (end[0] - start[0]) * fraction,
            start[1] + (end[1] - start[1]) * fraction,
        ]

    result = [route[0][:]]
    curve_speed_indices = set()
    index = 1
    while index < len(route) - 1:
        previous, turn, following = route[index - 1:index + 2]
        incoming = vector(previous, turn)
        outgoing = vector(turn, following)
        incoming_length, outgoing_length = math.hypot(*incoming), math.hypot(*outgoing)
        if not incoming_length or not outgoing_length:
            result.append(turn[:])
            index += 1
            continue
        cosine = (incoming[0] * outgoing[0] + incoming[1] * outgoing[1]) / (incoming_length * outgoing_length)
        # Ignore almost straight passes; every normal lawnmower U-turn has two
        # roughly 90-degree corners and receives exactly two support points.
        is_turn = cosine < math.cos(math.radians(20))
        # Two consecutive opposing turns form a normal lawnmower U-turn.
        # Sparmodus combines the two inner support points into one midpoint.
        if reduced and index + 2 < len(route):
            next_turn, after_next = route[index + 1:index + 3]
            next_incoming, next_outgoing = vector(turn, next_turn), vector(next_turn, after_next)
            next_incoming_length, next_outgoing_length = math.hypot(*next_incoming), math.hypot(*next_outgoing)
            if next_incoming_length and next_outgoing_length:
                reverse_cosine = (incoming[0] * next_outgoing[0] + incoming[1] * next_outgoing[1]) / (incoming_length * next_outgoing_length)
                if is_turn and reverse_cosine < -0.7:
                    first_curve_index = len(result) - 1
                    before_distance = min(support_distance_m, incoming_length * 0.45)
                    after_distance = min(support_distance_m, next_outgoing_length * 0.45)
                    result.extend([
                        interpolate(previous, turn, 1 - before_distance / incoming_length), turn[:],
                        interpolate(turn, next_turn, 0.5), next_turn[:],
                        interpolate(next_turn, after_next, after_distance / next_outgoing_length),
                    ])
                    # Slow from the last straight-leg waypoint through the
                    # second corner. The final outgoing support point resumes
                    # normal speed for the next scan leg.
                    curve_speed_indices.update(range(first_curve_index, first_curve_index + 5))
                    index += 2
                    continue
        if is_turn:
            first_curve_index = len(result) - 1
            before_distance = min(support_distance_m, incoming_length * 0.45)
            after_distance = min(support_distance_m, outgoing_length * 0.45)
            result.append(interpolate(previous, turn, 1 - before_distance / incoming_length))
            result.append(turn[:])
            result.append(interpolate(turn, following, after_distance / outgoing_length))
            curve_speed_indices.update(range(first_curve_index, first_curve_index + 3))
        else:
            result.append(turn[:])
        index += 1
    result.append(route[-1][:])
    return (result, curve_speed_indices) if return_curve_speed_indices else result

def add_overshoot_turns(route, overshoot_distance_m, reduced=False):
    """Move lawnmower U-turns outside the survey area with two extra points.

    Each compatible U-turn gets two exterior points (or one midpoint in
    Sparmodus): one continuing past the first row end and one before
    re-entering the next row. Thus the in-area row ends remain collinear for a
    spline preview.
    A single lead-in and lead-out point give the first and last scan path the
    same collinear spline guidance. Returns the augmented route and exterior
    path fragments for map rendering.
    """
    if len(route) < 4 or overshoot_distance_m <= 0:
        return [point[:] for point in route], []
    latitude_scale = 111_132.92

    def vector(start, end):
        longitude_scale = 111_319.49 * math.cos(math.radians((start[0] + end[0]) / 2))
        return ((end[0] - start[0]) * latitude_scale, (end[1] - start[1]) * longitude_scale)

    def offset(point, direction, distance):
        length = math.hypot(*direction)
        if not length:
            return point[:]
        lat = point[0] + direction[0] / length * distance / latitude_scale
        longitude_scale = 111_319.49 * math.cos(math.radians(point[0]))
        lon = point[1] + direction[1] / length * distance / longitude_scale
        return [lat, lon]

    first_direction = vector(route[0], route[1])
    last_direction = vector(route[-2], route[-1])
    entry_distance = min(overshoot_distance_m, math.hypot(*first_direction) * 0.45)
    exit_distance = min(overshoot_distance_m, math.hypot(*last_direction) * 0.45)
    entry = offset(route[0], (-first_direction[0], -first_direction[1]), entry_distance)
    result, exterior_paths = [entry, route[0][:]], [[entry, route[0][:]]]
    index = 1
    while index < len(route):
        if index + 2 < len(route):
            before, first_end, second_end, after = route[index - 1:index + 3]
            incoming, cross_row, outgoing = vector(before, first_end), vector(first_end, second_end), vector(second_end, after)
            incoming_length, cross_length, outgoing_length = (
                math.hypot(*incoming), math.hypot(*cross_row), math.hypot(*outgoing)
            )
            if incoming_length and cross_length and outgoing_length:
                reverse_cosine = (incoming[0] * outgoing[0] + incoming[1] * outgoing[1]) / (incoming_length * outgoing_length)
                # Consecutive survey passes that run in opposite directions are
                # a lawnmower U-turn.  At slanted/tapered polygon edges their
                # connecting segment is not necessarily a perfect 90° corner,
                # so requiring two right angles used to miss one side.
                if reverse_cosine < -0.7:
                    distance = min(overshoot_distance_m, incoming_length * 0.45, outgoing_length * 0.45)
                    outside_first = offset(first_end, incoming, distance)
                    outside_second = offset(second_end, (-outgoing[0], -outgoing[1]), distance)
                    if reduced:
                        midpoint = [(outside_first[0] + outside_second[0]) / 2, (outside_first[1] + outside_second[1]) / 2]
                        result.extend([first_end[:], midpoint, second_end[:]])
                        exterior_paths.append([first_end[:], midpoint, second_end[:]])
                    else:
                        result.extend([first_end[:], outside_first, outside_second, second_end[:]])
                        exterior_paths.append([first_end[:], outside_first, outside_second, second_end[:]])
                    index += 2
                    continue
        result.append(route[index][:])
        index += 1
    exit_point = offset(route[-1], last_direction, exit_distance)
    result.append(exit_point)
    exterior_paths.append([route[-1][:], exit_point])
    return result, exterior_paths

def centripetal_catmull_rom_route(route, samples_per_segment=12):
    """Return a local-metric, centripetal Catmull-Rom approximation for map preview only."""
    if len(route) < 3:
        return [point[:] for point in route]
    latitude_origin = sum(point[0] for point in route) / len(route)
    longitude_origin = sum(point[1] for point in route) / len(route)
    latitude_scale = 111_132.92
    longitude_scale = 111_319.49 * math.cos(math.radians(latitude_origin))
    points = [((lon - longitude_origin) * longitude_scale, (lat - latitude_origin) * latitude_scale) for lat, lon in route]

    def extrapolate(anchor, neighbour):
        return (2 * anchor[0] - neighbour[0], 2 * anchor[1] - neighbour[1])

    def knot(a, b, previous):
        # alpha=.5 is the centripetal parameterization. The lower bound also
        # makes repeated controller waypoints harmless.
        return previous + max(math.hypot(b[0] - a[0], b[1] - a[1]), 1e-6) ** 0.5

    def interpolate(a, b, ta, tb, t):
        if abs(tb - ta) < 1e-12:
            return a
        ratio = (t - ta) / (tb - ta)
        return (a[0] + (b[0] - a[0]) * ratio, a[1] + (b[1] - a[1]) * ratio)

    result = []
    samples = max(2, int(samples_per_segment))
    for index in range(len(points) - 1):
        p1, p2 = points[index], points[index + 1]
        p0 = points[index - 1] if index else extrapolate(p1, p2)
        p3 = points[index + 2] if index + 2 < len(points) else extrapolate(p2, p1)
        t0 = 0.0
        t1 = knot(p0, p1, t0)
        t2 = knot(p1, p2, t1)
        t3 = knot(p2, p3, t2)
        for sample in range(samples):
            t = t1 + (t2 - t1) * sample / samples
            a1 = interpolate(p0, p1, t0, t1, t)
            a2 = interpolate(p1, p2, t1, t2, t)
            a3 = interpolate(p2, p3, t2, t3, t)
            b1 = interpolate(a1, a2, t0, t2, t)
            b2 = interpolate(a2, a3, t1, t3, t)
            point = interpolate(b1, b2, t1, t2, t)
            result.append([latitude_origin + point[1] / latitude_scale, longitude_origin + point[0] / longitude_scale])
    result.append(route[-1][:])
    return result
def shortest_route_direction_deg(points,spacing_m,no_fly_zones=None): return min(range(180),key=lambda x:route_length_m(generate_lawnmower_route(points,spacing_m,x,no_fly_zones))) if len(points)>=3 else 0
def plan_missions(route,max_points,max_seconds,speed_mps,mode,turn_delay_s=0):
    if len(route)<2:return []
    result=[];current=[route[0]]
    for p in route[1:]:
        if len(current)+1>max_points or estimated_route_seconds(current+[p],speed_mps,turn_delay_s)>max_seconds:
            if len(current)<2:return []
            # Den Übergangspunkt in beide Missionen aufnehmen. So setzt die
            # Folgemission exakt am Ende der vorherigen an.
            result.append(current);current=[current[-1],p]
        else:current.append(p)
    return result+[current] if len(current)>=2 else result

__all__ = [
    "add_overshoot_turns", "centripetal_catmull_rom_route", "count_direction_changes", "densify_route", "estimated_route_seconds",
    "generate_lawnmower_route", "optimal_direction_deg", "plan_missions",
    "polygon_area_m2", "route_length_m", "shortest_route_direction_deg",
]
