# Return all vertices of the FIRST feature (native SR and WGS84)
import arcpy

SERVICE_URL = r"https://gis.ashghal.gov.qa/FSDMGP/rest/services/DNMC/FMPActiveProjects/MapServer/0"
TMP_LYR     = "first_feat_lyr"
WGS84       = arcpy.SpatialReference(4326)

def vertices_by_part(geom, drop_closing_duplicate=True, include_z=False):
    """
    Returns a list of parts; each part is a list of (x,y) or (x,y,z) tuples.
    - Works for Polygon, Polyline, Point (Point → one part, single tuple)
    - drop_closing_duplicate=True removes the last point if it duplicates the first (common in rings)
    """
    parts = []
    if geom is None:
        return parts

    gtype = geom.type.lower()

    # Points: single vertex
    if gtype == "point":
        pt = geom.firstPoint
        if pt:
            if include_z and geom.hasZ:
                parts.append([(pt.X, pt.Y, pt.Z)])
            else:
                parts.append([(pt.X, pt.Y)])
        return parts

    # Polylines/Polygons: iterate parts (rings for polygons)
    for part in geom:  # each 'part' is an arcpy.Array of Point objects
        ring = []
        for pt in part:
            if pt is None:
                # None can appear as a separator in some multipart geometries
                if ring:
                    if drop_closing_duplicate and len(ring) > 1 and ring[0] == ring[-1]:
                        ring.pop()
                    parts.append(ring)
                    ring = []
                continue
            if include_z and geom.hasZ:
                ring.append((pt.X, pt.Y, pt.Z))
            else:
                ring.append((pt.X, pt.Y))
        if ring:
            if drop_closing_duplicate and len(ring) > 1 and ring[0] == ring[-1]:
                ring.pop()
            parts.append(ring)

    return parts

# --- Build a feature layer and fetch the FIRST row ---
if arcpy.Exists(TMP_LYR):
    arcpy.management.Delete(TMP_LYR)
arcpy.management.MakeFeatureLayer(SERVICE_URL, TMP_LYR)

# Native SR vertices
with arcpy.da.SearchCursor(TMP_LYR, ["OID@", "SHAPE@"]) as cur:
    row = next(cur, None)
    if not row:
        raise RuntimeError("No features found.")
    oid_native, geom_native = row
    sr_native = arcpy.Describe(TMP_LYR).spatialReference
    native_vertices = vertices_by_part(geom_native, drop_closing_duplicate=True, include_z=False)

# WGS84 (on-the-fly reprojection in cursor)
with arcpy.da.SearchCursor(TMP_LYR, ["OID@", "SHAPE@"], spatial_reference=WGS84) as cur_wgs:
    row = next(cur_wgs, None)
    oid_wgs, geom_wgs = row
    wgs_vertices = vertices_by_part(geom_wgs, drop_closing_duplicate=True, include_z=False)

# Cleanup temp layer
arcpy.management.Delete(TMP_LYR)

# ---- Results ----
print(f"First feature OID (native) : {oid_native}")
print(f"Source SR (native)         : {getattr(sr_native, 'name', '(unknown)')} (WKID {getattr(sr_native, 'factoryCode', None)})")
print(f"Parts (native) / total pts : {len(native_vertices)} / {sum(len(p) for p in native_vertices)}")
print(f"Parts (WGS84)  / total pts : {len(wgs_vertices)} / {sum(len(p) for p in wgs_vertices)}")

# If you want to see coordinates, print them (comment out if large):
for i, part in enumerate(native_vertices, 1):
    print(f"\nNative part {i} ({len(part)} pts):")
    for xy in part:
        print(xy)

for i, part in enumerate(wgs_vertices, 1):
    print(f"\nWGS84 part {i} ({len(part)} pts):")
    for xy in part:
        print(xy)
