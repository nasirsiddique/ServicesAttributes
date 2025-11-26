# -*- coding: utf-8 -*-
"""
compare_data.py — Schema & SR compare helpers (ArcPy only)

Behavior:
- Compares source vs target schema (geometry type + fields).
- TARGET SR must be WGS84 (WKID 4326).
- Tolerates ONLY those target-only extra fields explicitly listed
  in conf.ALLOWED_EXTRA_IN_TARGET (case-insensitive).
- Robust field matching: normalize names (lower, trim spaces, trim 1 trailing underscore)
  and fall back to alias matching when names differ.
- Provides detailed comparison results and a field dump helper.

Exports:
  script_dir, open_sde, load_conf, split_target, make_schema_only_source,
  sr_wkid, geom_type, schema_equal, schema_compare_details, dump_fields
"""

import os
import sys
import importlib
from typing import Dict, Optional, Set, Tuple, List

import arcpy

# Treat these as system and ignore in comparisons (case-insensitive)
SYSTEM_FIELD_NAMES: Set[str] = {"objectid", "shape", "globalid", "shape_area", "shape_length"}


# ---------------- basics ----------------

def script_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def open_sde(sde_filename: str) -> str:
    """Resolve .sde next to this script, touch it via ListFeatureClasses, and return the path."""
    sde_path = os.path.join(script_dir(), sde_filename)
    if not arcpy.Exists(sde_path):
        raise RuntimeError(f".sde not found or not recognized by ArcPy: {sde_path}")
    arcpy.env.workspace = sde_path
    _ = arcpy.ListFeatureClasses()  # touch
    return sde_path


def load_conf():
    """Import conf.py (must be next to this script) and return SERVICE_TO_TARGET mapping."""
    base = script_dir()
    if base not in sys.path:
        sys.path.insert(0, base)
    cfg = importlib.import_module("conf")
    mapping = getattr(cfg, "SERVICE_TO_TARGET", None)
    if not isinstance(mapping, dict) or not mapping:
        raise ValueError("conf.SERVICE_TO_TARGET must be a non-empty dict.")
    return mapping


def split_target(sde_ws: str, target_str: str):
    """
    Convert "FeatureDataset.FeatureClass" or "FeatureClass" to
    (container_workspace, base_name, full_catalog_path).
    """
    target_str = (target_str or "").strip()
    if "." in target_str:
        ds, fc = target_str.split(".", 1)
        container = os.path.join(sde_ws, ds)
        return container, fc, os.path.join(container, fc)
    return sde_ws, target_str, os.path.join(sde_ws, target_str)


# ---------------- describe helpers ----------------

def make_schema_only_source(service_url: str) -> str:
    """
    Create an in_memory FC with only the source schema (no rows),
    via a temp Feature Layer filtered with '1=2'.
    """
    tmp_lyr = "tmp_schema_lyr"
    out_fc = os.path.join("in_memory", "src_schema_tmp")
    if arcpy.Exists(tmp_lyr):
        arcpy.management.Delete(tmp_lyr)
    if arcpy.Exists(out_fc):
        arcpy.management.Delete(out_fc)
    arcpy.management.MakeFeatureLayer(service_url, tmp_lyr, "1=2")
    arcpy.conversion.FeatureClassToFeatureClass(tmp_lyr, "in_memory", "src_schema_tmp")
    arcpy.management.Delete(tmp_lyr)
    return out_fc


def sr_wkid(desc_obj) -> Optional[int]:
    sr = getattr(desc_obj, "spatialReference", None)
    return getattr(sr, "factoryCode", None) if sr else None


def geom_type(desc_obj) -> Optional[str]:
    return getattr(desc_obj, "shapeType", None)


# ---------------- field utilities ----------------

def _norm_name(s: Optional[str]) -> str:
    """Lowercase, trim spaces, and trim a single trailing underscore (common tracking quirk)."""
    if not s:
        return ""
    s = s.strip().lower()
    if s.endswith("_"):
        s = s[:-1]
    return s


def dump_fields(desc_obj) -> List[dict]:
    """Return a list of dicts with raw field info (name/alias/type/length/editable) for debugging."""
    out: List[dict] = []
    for f in desc_obj.fields:
        out.append({
            "name": f.name,
            "alias": getattr(f, "aliasName", ""),
            "type": f.type,
            "length": getattr(f, "length", None) if f.type == "String" else None,
            "editable": getattr(f, "editable", None),
        })
    return out


def _list_user_fields_rich(desc_obj) -> Dict[str, dict]:
    """
    Return a dict keyed by **normalized name** with rich info:
      { norm_name: {'name':orig,'alias':alias,'type':type,'length':len_or_None,'alias_norm':norm_alias} }
    Skips system + Geometry/OID/GlobalID/Blob/Raster/XML.
    """
    out: Dict[str, dict] = {}
    for fld in desc_obj.fields:
        name = (fld.name or "").strip()
        lname = name.lower()
        if lname in SYSTEM_FIELD_NAMES:
            continue
        ftype = fld.type
        if ftype in ("OID", "Geometry", "GlobalID", "Blob", "Raster", "XML"):
            continue
        alias = getattr(fld, "aliasName", None) or ""
        key = _norm_name(name)
        out[key] = {
            "name": name,
            "alias": alias,
            "type": ftype,
            "length": getattr(fld, "length", None) if ftype == "String" else None,
            "norm": key,
            "alias_norm": _norm_name(alias),
        }
    return out


# ---------------- comparison core ----------------

def _compare_fields_core(
    src_desc,
    tgt_desc,
    allowed_extra_in_target: Optional[Set[str]] = None,
) -> Tuple[bool, dict]:
    """
    Compare fields with robust matching:
      - match by normalized NAME first; if missing, try matching by normalized ALIAS
      - tolerate target-only extras ONLY if listed in 'allowed_extra_in_target' (case-insensitive)
    Returns (ok, details)
    """
    allowed_names_lc = {f.lower() for f in (allowed_extra_in_target or set())}

    s = _list_user_fields_rich(src_desc)
    t = _list_user_fields_rich(tgt_desc)

    # Reverse maps for alias matching
    s_by_alias = {info["alias_norm"]: k for k, info in s.items() if info["alias_norm"]}
    t_by_alias = {info["alias_norm"]: k for k, info in t.items() if info["alias_norm"]}

    # First match by normalized name
    matched_src = set()
    matched_tgt = set()
    for sk in s.keys():
        if sk in t:
            matched_src.add(sk)
            matched_tgt.add(sk)

    # Then match by alias where names didn't match
    for sk in set(s.keys()) - matched_src:
        salias = s[sk]["alias_norm"]
        if not salias:
            continue
        tk = t_by_alias.get(salias)
        if tk is not None:
            matched_src.add(sk)
            matched_tgt.add(tk)

    # Compute missing and extras after matching
    missing_src_keys = sorted(set(s.keys()) - matched_src)   # source fields missing in target
    extra_tgt_keys   = sorted(set(t.keys()) - matched_tgt)   # target-only fields

    # Apply allow-list to extras (by actual target field names, case-insensitive)
    extras_not_allowed = []
    extras_allowed_ignored = []
    for tk in extra_tgt_keys:
        tname_lc = t[tk]["name"].lower()
        if tname_lc in allowed_names_lc:
            extras_allowed_ignored.append(t[tk]["name"])
        else:
            extras_not_allowed.append(t[tk]["name"])

    # Type/length mismatches among matched pairs
    mismatches = []
    for sk in matched_src:
        # find corresponding target key (by name or alias)
        if sk in t:
            tk = sk
        else:
            salias = s[sk]["alias_norm"]
            tk = t_by_alias.get(salias)
            if tk is None:
                continue

        s_info = s[sk]; t_info = t[tk]
        if s_info["type"] != t_info["type"]:
            mismatches.append(f"{s_info['name']} ↔ {t_info['name']}: type {s_info['type']} != {t_info['type']}")
        elif s_info["type"] == "String":
            sl, tl = (s_info["length"] or 0), (t_info["length"] or 0)
            if sl != tl:
                mismatches.append(f"{s_info['name']} ↔ {t_info['name']}: length {sl} != {tl}")

    ok = (not missing_src_keys) and (not extras_not_allowed) and (not mismatches)
    details = {
        "missing_in_target": [s[k]["name"] for k in missing_src_keys],
        "extras_not_allowed": extras_not_allowed,
        "type_length_mismatches": mismatches,
        "extras_allowed_ignored": extras_allowed_ignored,
    }
    return ok, details


def schema_compare_details(
    src_schema_fc: str,
    tgt_fc: str,
    allowed_extra_in_target: Optional[Set[str]] = None,
) -> Dict[str, object]:
    """
    Full schema comparison with details.
    Returns dict with keys:
      sr_ok, tgt_wkid, geom_ok, src_geom, tgt_geom, fields_ok, field_details,
      src_fields, tgt_fields (for debugging).
    """
    s_desc = arcpy.Describe(src_schema_fc)
    t_desc = arcpy.Describe(tgt_fc)

    src_geom = str(geom_type(s_desc))
    tgt_geom = str(geom_type(t_desc))
    geom_ok = (src_geom.lower() == tgt_geom.lower())

    tgt_wkid = sr_wkid(t_desc)
    sr_ok = (tgt_wkid == 4326)

    fields_ok, field_details = _compare_fields_core(
        s_desc, t_desc, allowed_extra_in_target=allowed_extra_in_target
    )

    return {
        "sr_ok": sr_ok,
        "tgt_wkid": tgt_wkid,
        "geom_ok": geom_ok,
        "src_geom": src_geom,
        "tgt_geom": tgt_geom,
        "fields_ok": fields_ok,
        "field_details": field_details,
        "src_fields": dump_fields(s_desc),
        "tgt_fields": dump_fields(t_desc),
    }


def schema_equal(
    src_schema_fc: str,
    tgt_fc: str,
    allowed_extra_in_target: Optional[Set[str]] = None,
) -> bool:
    """Boolean wrapper around schema_compare_details()."""
    res = schema_compare_details(
        src_schema_fc, tgt_fc,
        allowed_extra_in_target=allowed_extra_in_target
    )
    return res["sr_ok"] and res["geom_ok"] and res["fields_ok"]
