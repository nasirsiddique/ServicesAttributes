# -*- coding: utf-8 -*-
# copy_data.py — export rows, project to WGS84, and write as GEOGRAPHY

import os
import arcpy

WGS84 = arcpy.SpatialReference(4326)
CONFIG_KEYWORD = "GEOGRAPHY"    # SQL Server: store as GEOGRAPHY
GLOBAL_WHERE   = None           # e.g., "Status='Active'"

def export_rows(service_url: str) -> str:
    """Copy ALL (or filtered) rows to in_memory in native SR."""
    out = os.path.join("in_memory", "src_rows")
    if arcpy.Exists(out):
        arcpy.management.Delete(out)
    arcpy.conversion.FeatureClassToFeatureClass(service_url, "in_memory", "src_rows", GLOBAL_WHERE)
    return out

def project_to_wgs(in_fc: str) -> str:
    """Project to WGS84 (4326) if needed."""
    wkid = getattr(getattr(arcpy.Describe(in_fc), "spatialReference", None), "factoryCode", None)
    if wkid == 4326:
        return in_fc
    out = os.path.join("in_memory", "src_rows_wgs84")
    if arcpy.Exists(out):
        arcpy.management.Delete(out)
    arcpy.management.Project(in_fc, out, WGS84)
    return out

def create_new_table_with_rows(container_ws: str, out_name: str, proj_rows_fc: str) -> str:
    """
    Create a new feature class in the Enterprise GDB and copy all rows.
    Ensures storage as GEOGRAPHY (WGS84).
    """
    out_path = os.path.join(container_ws, out_name)
    if arcpy.Exists(out_path):
        arcpy.management.Delete(out_path)
    arcpy.conversion.FeatureClassToFeatureClass(
        proj_rows_fc, container_ws, out_name,
        field_mapping="", config_keyword=CONFIG_KEYWORD
    )
    return out_path
