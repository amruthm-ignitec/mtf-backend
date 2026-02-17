"""Unit tests for compliance engine: age 15-76, CMV IgG ignored, Infection_Markers, documents."""
import pytest

from app.services.compliance import evaluate_eligibility


def test_eligible_no_flags():
    data = {
        "Identity": {"Age": 45},
        "Document_Inventory": {"Has_Authorization": True, "Has_DRAI": True, "Has_Infectious_Disease_Labs": True},
        "Serology_Panel": {"Tests": [{"Test_Name": "HIV", "Result": "Negative"}]},
        "Clinical_Summary": {"Infection_Markers": []},
    }
    status, flags = evaluate_eligibility(data)
    assert status == "ELIGIBLE"
    assert flags == []


def test_age_15_76_in_range():
    for age in (15, 76, 50):
        data = {
            "Identity": {"Age": age},
            "Document_Inventory": {"Has_Authorization": True, "Has_DRAI": True, "Has_Infectious_Disease_Labs": True},
            "Serology_Panel": {"Tests": []},
            "Clinical_Summary": {},
        }
        status, flags = evaluate_eligibility(data)
        assert status == "ELIGIBLE", f"Age {age} should be eligible"
        assert not any("AGE" in f for f in flags)


def test_age_outside_range():
    data = {
        "Identity": {"Age": 14},
        "Document_Inventory": {"Has_Authorization": True, "Has_DRAI": True, "Has_Infectious_Disease_Labs": True},
        "Serology_Panel": {"Tests": []},
        "Clinical_Summary": {},
    }
    status, flags = evaluate_eligibility(data)
    assert status == "REVIEW"
    assert any("AGE" in f for f in flags)


def test_cmv_igg_positive_not_flagged():
    """CMV IgG Positive must NOT be flagged as rejection (plan acceptance criteria)."""
    data = {
        "Identity": {"Age": 40},
        "Document_Inventory": {"Has_Authorization": True, "Has_DRAI": True, "Has_Infectious_Disease_Labs": True},
        "Serology_Panel": {
            "Tests": [
                {"Test_Name": "CMV IgG", "Result": "Positive", "Interpretation": "Reactive"},
            ]
        },
        "Clinical_Summary": {"Infection_Markers": []},
    }
    status, flags = evaluate_eligibility(data)
    assert status == "ELIGIBLE"
    assert not any("CMV" in f or "INFECTIOUS DISEASE" in f for f in flags)


def test_infection_markers_flagged():
    """Sepsis/Bacteremia/WBC > 15 in Clinical_Summary.Infection_Markers -> REVIEW."""
    data = {
        "Identity": {"Age": 40},
        "Document_Inventory": {"Has_Authorization": True, "Has_DRAI": True, "Has_Infectious_Disease_Labs": True},
        "Serology_Panel": {"Tests": []},
        "Clinical_Summary": {"Infection_Markers": ["Sepsis", "Bacteremia"]},
    }
    status, flags = evaluate_eligibility(data)
    assert status == "REVIEW"
    assert any("INFECTION MARKERS" in f for f in flags)


def test_missing_documents():
    data = {
        "Identity": {"Age": 40},
        "Document_Inventory": {"Has_Authorization": False, "Has_DRAI": True, "Has_Infectious_Disease_Labs": True},
        "Serology_Panel": {"Tests": []},
        "Clinical_Summary": {},
    }
    status, flags = evaluate_eligibility(data)
    assert status == "REVIEW"
    assert any("MISSING DOCUMENTS" in f for f in flags)


def test_positive_serology_flagged():
    data = {
        "Identity": {"Age": 40},
        "Document_Inventory": {"Has_Authorization": True, "Has_DRAI": True, "Has_Infectious_Disease_Labs": True},
        "Serology_Panel": {
            "Tests": [{"Test_Name": "HIV", "Result": "Positive", "Interpretation": "Reactive"}]
        },
        "Clinical_Summary": {},
    }
    status, flags = evaluate_eligibility(data)
    assert status == "REVIEW"
    assert any("INFECTIOUS DISEASE" in f for f in flags)
