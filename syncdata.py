# -*- coding: utf-8 -*-
"""
syncdata.py — nightly sync with strict schema guard:
- If target FC is missing: CREATE it (project to WGS84 & store as GEOGRAPHY), copy all rows.
- If schema differs: log "Schema is different, syncing cannot be continued." and SKIP.
- If schema matches: TRUNCATE -> APPEND projected (WGS84) rows.

Requires:
  compare_data.py  (load_conf, open_sde, split_target, make_schema_only_source, schema_equal)
  copy_data.py     (export_rows, project_to_wgs, create_new_table_with_rows)
  conf.py          (SERVICE_TO_TARGET)

Run in ArcGIS Pro Python.
"""

import os
import arcpy
from compare_data import (
    load_conf, open_sde, split_target, make_schema_only_source, schema_equal
)

import importlib
cfg = importlib.import_module("conf")
ALLOWED_EXTRA = set(getattr(cfg, "ALLOWED_EXTRA_IN_TARGET", set()))
SDE_FILENAME = "PROD-SDE ODW esrigeodb.sde"

def truncate_then_append(src_fc: str, tgt_fc: str):
    """Truncate target; then append rows from src."""
    try:
        arcpy.management.TruncateTable(tgt_fc)
    except Exception:
        # Fallback if truncate blocked by rules/locks
        with arcpy.da.UpdateCursor(tgt_fc, ["OID@"]) as cur:
            for _ in cur:
                cur.deleteRow()
    arcpy.management.Append(src_fc, tgt_fc, schema_type="NO_TEST")

def process_pair(service_url: str, target_str: str, sde_ws: str):
    # Delay import to avoid any accidental circulars
    from copy_data import export_rows, project_to_wgs, create_new_table_with_rows

    container_ws, base_name, base_path = split_target(sde_ws, target_str)

    print("\n" + "=" * 78)
    print("Source :", service_url)
    print("Target :", base_path)

    src_schema = rows_native = rows_wgs = None
    try:
        # Build schema-only FC from source (no rows)
        src_schema = make_schema_only_source(service_url)

        # --- If target is MISSING: create it now (WGS84 / GEOGRAPHY) and copy all rows ---
        if not arcpy.Exists(base_path):
            print("ℹ️  Target feature class does not exist — creating it (WGS84 / GEOGRAPHY) and loading rows…")
            rows_native = export_rows(service_url)
            rows_wgs    = project_to_wgs(rows_native)
            created = create_new_table_with_rows(container_ws, base_name, rows_wgs)
            try:
                cnt = int(arcpy.management.GetCount(created)[0])
                print(f"✅ Created {created} with {cnt} rows (stored as GEOGRAPHY; SRID 4326).")
            except Exception:
                print("✅ Created target (count unavailable).")
            return

        # --- Target exists: strict guard — if schema differs, DO NOT SYNC ---
        src_schema = make_schema_only_source(service_url)
        if not schema_equal(src_schema, base_path, allowed_extra_in_target=ALLOWED_EXTRA):
        # (Optional) print details to see exactly why:
            from compare_data import schema_compare_details
            det = schema_compare_details(src_schema, base_path, allowed_extra_in_target=ALLOWED_EXTRA)
            print("❌ Schema is different. Details:", det["field_details"])
            return

        # --- Schema matches: export -> project (to WGS84) -> truncate→append ---
        rows_native = export_rows(service_url)
        rows_wgs    = project_to_wgs(rows_native)

        print("Schema matches → TRUNCATE → APPEND (projected to WGS84)…")
        truncate_then_append(rows_wgs, base_path)

        # Report count
        try:
            cnt = int(arcpy.management.GetCount(base_path)[0])
            print(f"✅ Sync complete. {cnt} rows in {base_path}")
        except Exception:
            pass

    except Exception as e:
        print("❌ Failed:", e)
        print(arcpy.GetMessages())
    finally:
        # Cleanup in_memory scratch
        for p in (
            src_schema, rows_native, rows_wgs,
            os.path.join("in_memory", "src_schema_tmp"),
            os.path.join("in_memory", "src_rows"),
            os.path.join("in_memory", "src_rows_wgs84"),
        ):
            try:
                if p and arcpy.Exists(p):
                    arcpy.management.Delete(p)
            except Exception:
                pass

def main():
    mapping = load_conf()
    sde_ws  = open_sde(SDE_FILENAME)
    print("SDE workspace:", sde_ws)

    for service_url, target_str in mapping.items():
        process_pair(service_url, target_str, sde_ws)

if __name__ == "__main__":
    main()
