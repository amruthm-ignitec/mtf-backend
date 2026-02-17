"""
Merge donor extraction chunks into a single master record.
Identity from first non-empty; lists merged with set(); Serology by Test_Name (overwrite if Positive/Reactive); Inventory = OR.
"""
import copy
import logging

logger = logging.getLogger(__name__)


def _deep_update_list_unique(master: list, new: list) -> list:
    """Merge lists: unique values only (order from master then new)."""
    if not new:
        return list(master) if master else []
    if not master:
        return list(new) if new else []
    seen = set(master)
    out = list(master)
    for x in new:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _merge_serology_tests(master_tests: list[dict], new_tests: list[dict]) -> list[dict]:
    """Serology: key by Test_Name. Overwrite only if new result is Positive/Reactive."""
    by_name: dict[str, dict] = {}
    for t in master_tests or []:
        name = (t.get("Test_Name") or "").strip() or str(id(t))
        by_name[name] = dict(t)
    for t in new_tests or []:
        name = (t.get("Test_Name") or "").strip() or str(id(t))
        new_res = (t.get("Result") or "").strip()
        new_interp = (t.get("Interpretation") or "").strip()
        is_positive = new_res in ("Positive", "Reactive") or new_interp in (
            "Reactive",
            "Equivocal",
            "Indeterminate",
        )
        if name not in by_name or is_positive:
            by_name[name] = dict(t)
    return list(by_name.values())


def _merge_inventory(master_inv: dict | None, new_inv: dict | None) -> dict:
    """Document inventory: boolean OR — present if true in any chunk."""
    out = dict(master_inv or {})
    for k, v in (new_inv or {}).items():
        if isinstance(v, bool) and v:
            out[k] = True
        elif k not in out:
            out[k] = v
    return out


def _is_empty_identity(ident: dict | None) -> bool:
    if not ident:
        return True
    return not any(
        ident.get(k) not in (None, "", [])
        for k in ("Donor_ID", "UNOS_ID", "Tissue_ID", "Date_Of_Birth", "Age")
    )


def merge_donor_data(master: dict, new_chunk: dict) -> dict:
    """
    Merge new_chunk into master. Returns a new dict (does not mutate master).
    - Identity: update only if master identity is empty.
    - Lists (e.g. Past_Medical_History, Medications_Administered): unique merge via set.
    - Serology Tests: key by Test_Name; overwrite only if new result is Positive/Reactive.
    - Document_Inventory: boolean OR (present if true in any chunk).
    """
    result = copy.deepcopy(master) if master else {}

    # Identity: fill only when master is empty
    ident_m = result.get("Identity") or {}
    ident_n = new_chunk.get("Identity") or {}
    if _is_empty_identity(ident_m) and not _is_empty_identity(ident_n):
        result["Identity"] = copy.deepcopy(ident_n)
    elif ident_n and not ident_m:
        result["Identity"] = copy.deepcopy(ident_n)

    # Clinical_Summary: merge lists, merge Infection_Markers
    cs_m = result.get("Clinical_Summary") or {}
    cs_n = new_chunk.get("Clinical_Summary") or {}
    merged_cs = dict(cs_m)
    for list_key in ("Past_Medical_History", "Medications_Administered", "Infection_Markers"):
        if list_key in cs_n and isinstance(cs_n[list_key], list):
            merged_cs[list_key] = _deep_update_list_unique(
                cs_m.get(list_key) or [], cs_n[list_key]
            )
    for k, v in cs_n.items():
        if k in ("Past_Medical_History", "Medications_Administered", "Infection_Markers", "Social_History"):
            continue
        if v not in (None, "", []):
            merged_cs[k] = v
    if cs_n.get("Social_History"):
        merged_cs["Social_History"] = {**(cs_m.get("Social_History") or {}), **(cs_n["Social_History"] or {})}
    result["Clinical_Summary"] = merged_cs

    # Serology: merge tests by Test_Name
    sero_m = result.get("Serology_Panel") or {}
    sero_n = new_chunk.get("Serology_Panel") or {}
    merged_sero = dict(sero_m)
    merged_sero["Tests"] = _merge_serology_tests(sero_m.get("Tests") or [], sero_n.get("Tests") or [])
    if sero_n.get("Sample_Details"):
        merged_sero["Sample_Details"] = {**(sero_m.get("Sample_Details") or {}), **(sero_n["Sample_Details"])}
    if sero_n.get("Overall_Interpretation"):
        merged_sero["Overall_Interpretation"] = sero_n["Overall_Interpretation"]
    result["Serology_Panel"] = merged_sero

    # Document_Inventory: OR
    result["Document_Inventory"] = _merge_inventory(
        result.get("Document_Inventory"), new_chunk.get("Document_Inventory")
    )

    # Other sections: prefer new if present (simple deep merge for non-list/non-special)
    for section in ("Cultures", "HLA_Typing_Panel", "Plasma_Dilution_Details", "Conditional_Tests", "Timestamps"):
        new_val = new_chunk.get(section)
        if new_val and isinstance(new_val, dict):
            existing = result.get(section) or {}
            if isinstance(existing, dict):
                result[section] = {**existing, **new_val}
            else:
                result[section] = copy.deepcopy(new_val)
        elif result.get(section) is None and new_val is not None:
            result[section] = copy.deepcopy(new_val)

    return result
