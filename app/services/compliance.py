"""
Compliance engine: evaluate donor eligibility from merged_data.
Returns status (ELIGIBLE | REVIEW | PENDING) and list of flag strings.
"""
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

REQUIRED_DOCUMENTS = ["Has_Authorization", "Has_DRAI", "Has_Infectious_Disease_Labs"]
AGE_MIN = 15
AGE_MAX = 76
SEROLOGY_FLAG_VALUES = ("Positive", "Reactive", "Equivocal", "Indeterminate")


def evaluate_eligibility(merged_data: dict) -> Tuple[str, list[str]]:
    """
    Evaluate eligibility from merged donor data.
    Returns (status, flags) where status is ELIGIBLE, REVIEW, or PENDING.
    """
    flags: list[str] = []
    data = merged_data or {}

    # Age: 15-76 (Skin/Musculoskeletal per plan)
    identity = data.get("Identity") or {}
    age = identity.get("Age")
    if age is not None:
        try:
            age_int = int(age)
            if age_int < AGE_MIN or age_int > AGE_MAX:
                flags.append(f"AGE: {age_int} (outside eligible range {AGE_MIN}-{AGE_MAX})")
        except (TypeError, ValueError):
            flags.append("AGE: invalid or missing")

    # Documents: mandatory Auth, DRAI, Labs
    docs = data.get("Document_Inventory") or {}
    missing = [d for d in REQUIRED_DOCUMENTS if not docs.get(d)]
    if missing:
        flags.append(f"MISSING DOCUMENTS: {', '.join(missing)}")

    # Serology: flag Positive, Reactive, Equivocal, Indeterminate — ignore CMV IgG
    serology = data.get("Serology_Panel") or {}
    tests = serology.get("Tests") or []
    for test in tests:
        result = (test.get("Result") or "").strip()
        interpretation = (test.get("Interpretation") or "").strip()
        name = (test.get("Test_Name") or "").strip()
        if result in SEROLOGY_FLAG_VALUES or interpretation in SEROLOGY_FLAG_VALUES:
            if "CMV" in name and "IgG" in name:
                continue
            flags.append(f"INFECTIOUS DISEASE: {name} ({result or interpretation})")

    # Infection markers: Sepsis, Bacteremia, WBC > 15
    clinical = data.get("Clinical_Summary") or {}
    infection_markers = clinical.get("Infection_Markers") or []
    if infection_markers:
        flags.append(f"INFECTION MARKERS: {', '.join(infection_markers)}")

    # Post-transfusion without Plasma Dilution form
    details = serology.get("Sample_Details") or {}
    transfusion_status = (details.get("Transfusion_Status") or "").lower()
    if "post" in transfusion_status and not docs.get("Has_Plasma_Dilution"):
        flags.append("Post-transfusion sample but Plasma Dilution form missing")

    # High-risk drug use
    social = clinical.get("Social_History") or {}
    drug_use = social.get("Drug_Use")
    if drug_use and any(
        x in str(drug_use).lower() for x in ("iv", "heroin", "injection", "meth")
    ):
        flags.append(f"HIGH RISK: Drug use detected ({drug_use})")

    # Plasma dilution unacceptable
    plasma = data.get("Plasma_Dilution_Details") or {}
    if plasma.get("Outcome") == "Unacceptable":
        flags.append("PLASMA DILUTION: Outcome is Unacceptable")

    if not flags:
        status = "ELIGIBLE"
    else:
        status = "REVIEW"
    return status, flags
