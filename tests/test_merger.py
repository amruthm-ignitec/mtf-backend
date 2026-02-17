"""Unit tests for merge_donor_data: identity, lists, serology by Test_Name, inventory OR."""
from app.services.merger import merge_donor_data


def test_identity_from_first_non_empty():
    master = {}
    new = {"Identity": {"Donor_ID": "0042510891", "Age": 50}}
    merged = merge_donor_data(master, new)
    assert merged["Identity"]["Donor_ID"] == "0042510891"
    assert merged["Identity"]["Age"] == 50


def test_identity_not_overwritten_when_master_has_it():
    master = {"Identity": {"Donor_ID": "0042510891", "Age": 50}}
    new = {"Identity": {"Donor_ID": "other", "Age": 99}}
    merged = merge_donor_data(master, new)
    assert merged["Identity"]["Donor_ID"] == "0042510891"


def test_lists_merged_unique():
    master = {"Clinical_Summary": {"Past_Medical_History": ["Hypertension"]}}
    new = {"Clinical_Summary": {"Past_Medical_History": ["Hypertension", "Diabetes"]}}
    merged = merge_donor_data(master, new)
    assert set(merged["Clinical_Summary"]["Past_Medical_History"]) == {"Hypertension", "Diabetes"}


def test_serology_positive_overwrites():
    master = {
        "Serology_Panel": {
            "Tests": [{"Test_Name": "HIV", "Result": "Negative", "Interpretation": "Nonreactive"}]
        }
    }
    new = {
        "Serology_Panel": {
            "Tests": [{"Test_Name": "HIV", "Result": "Positive", "Interpretation": "Reactive"}]
        }
    }
    merged = merge_donor_data(master, new)
    tests = {t["Test_Name"]: t for t in merged["Serology_Panel"]["Tests"]}
    assert tests["HIV"]["Result"] == "Positive"


def test_inventory_or_logic():
    master = {"Document_Inventory": {"Has_Authorization": False, "Has_DRAI": False}}
    new = {"Document_Inventory": {"Has_Authorization": True, "Has_DRAI": False}}
    merged = merge_donor_data(master, new)
    assert merged["Document_Inventory"]["Has_Authorization"] is True
    assert merged["Document_Inventory"]["Has_DRAI"] is False
