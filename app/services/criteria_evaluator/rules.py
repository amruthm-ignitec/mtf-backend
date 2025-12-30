"""
Evaluation rule functions for each criterion type.
Each function evaluates extracted data and lab results against acceptance criteria rules.
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from app.models.criteria_evaluation import EvaluationResult
from app.models.laboratory_result import LaboratoryResult, TestType

logger = logging.getLogger(__name__)


def evaluate_age_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Evaluate age criteria.
    Returns result for both tissue types.
    """
    age = donor_info.get('age') or extracted_data.get('donor_age')
    tissue_type = extracted_data.get('tissue_type', '')
    gender = donor_info.get('gender', '')
    
    if not age:
        return {
            'result': EvaluationResult.MD_DISCRETION,
            'reasoning': 'Age not available'
        }
    
    age = int(age)
    
    # Check musculoskeletal rules
    ms_result = EvaluationResult.UNACCEPTABLE
    ms_reasoning = []
    
    if 15 <= age <= 75:
        ms_result = EvaluationResult.ACCEPTABLE
        ms_reasoning.append("Age 15-75 years (inclusive)")
    elif 12 <= age <= 70:
        ms_result = EvaluationResult.ACCEPTABLE
        ms_reasoning.append("Age 12-70 years (inclusive)")
    else:
        ms_reasoning.append(f"Age {age} outside standard criteria")
    
    # Check skin rules
    skin_result = EvaluationResult.UNACCEPTABLE
    skin_reasoning = []
    
    if 12 <= age <= 70:
        skin_result = EvaluationResult.ACCEPTABLE
        skin_reasoning.append("Age 12-70 years (inclusive)")
    else:
        skin_reasoning.append(f"Age {age} outside standard criteria")
    
    # For now, return MD_DISCRETION if either tissue type needs review
    # The actual tissue-specific evaluation happens in the main evaluator
    if ms_result == EvaluationResult.ACCEPTABLE and skin_result == EvaluationResult.ACCEPTABLE:
        return {
            'result': EvaluationResult.ACCEPTABLE,
            'reasoning': f"Age {age} meets criteria for both tissue types"
        }
    elif ms_result == EvaluationResult.ACCEPTABLE or skin_result == EvaluationResult.ACCEPTABLE:
        return {
            'result': EvaluationResult.MD_DISCRETION,
            'reasoning': f"Age {age}: MS={ms_result.value}, Skin={skin_result.value}"
        }
    else:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': f"Age {age} does not meet criteria for either tissue type"
        }


def evaluate_cancer_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate cancer criteria."""
    cancer_type = (extracted_data.get('cancer_type') or '').lower()
    diagnosis_date = extracted_data.get('diagnosis_date')
    treatment = extracted_data.get('treatment', '')
    recurrence = extracted_data.get('recurrence', False)
    time_since_death = extracted_data.get('time_since_death')
    
    # Check for unacceptable cancers (regardless of time)
    unacceptable_cancers = [
        'breast', 'colon', 'melanoma', 'hematologic', 'unknown primary',
        'metastasizing cns', 'glioblastoma', 'astrocytoma', 'medulloblastoma'
    ]
    
    if any(uc in cancer_type for uc in unacceptable_cancers):
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': f"History of {cancer_type} - unacceptable regardless of time"
        }
    
    # Check for malignancy within 5 years
    if diagnosis_date and time_since_death:
        try:
            # Parse dates and check if within 5 years
            # This is simplified - actual implementation would parse dates properly
            if '5' in str(time_since_death) or 'within' in str(time_since_death).lower():
                return {
                    'result': EvaluationResult.UNACCEPTABLE,
                    'reasoning': f"Malignancy within 5 years of death"
                }
        except:
            pass
    
    # Check for acceptable benign brain neoplasms
    acceptable_neoplasms = [
        'pituitary adenoma', 'optic nerve glioma', 'hemangioblastoma',
        'schwannoma', 'neurofibroma', 'hamartoma', 'meningioma',
        'colloid cyst', 'dermoid cyst', 'craniopharyngioma', 'lipoma'
    ]
    
    if any(an in cancer_type for an in acceptable_neoplasms) and 'benign' in str(extracted_data.get('benign', '')).lower():
        return {
            'result': EvaluationResult.ACCEPTABLE,
            'reasoning': f"Benign brain neoplasm: {cancer_type}"
        }
    
    # Check for MD discretion cases
    if 'basal' in cancer_type or 'squamous' in cancer_type:
        if not recurrence and '6 months' in str(extracted_data.get('recurrence_period', '')):
            return {
                'result': EvaluationResult.MD_DISCRETION,
                'reasoning': f"Localized, treated {cancer_type} with no recurrence within 6 months"
            }
    
    if 'cervical' in cancer_type and 'intraepithelial' in cancer_type:
        return {
            'result': EvaluationResult.MD_DISCRETION,
            'reasoning': "Well-documented cervical intraepithelial neoplasia"
        }
    
    # Default to MD discretion if cancer history exists but doesn't match clear rules
    if cancer_type:
        return {
            'result': EvaluationResult.MD_DISCRETION,
            'reasoning': f"Cancer history requires medical director review: {cancer_type}"
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No cancer history found'
    }


def evaluate_hiv_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate HIV criteria."""
    # Check lab results for HIV tests
    hiv_tests = [lr for lr in lab_results 
                 if lr.test_type == TestType.SEROLOGY and 'hiv' in lr.test_name.lower()]
    
    # Check for positive/reactive results
    for test in hiv_tests:
        result_lower = test.result.lower()
        if any(positive in result_lower for positive in ['positive', 'reactive', 'detected']):
            return {
                'result': EvaluationResult.UNACCEPTABLE,
                'reasoning': f"Positive HIV test result: {test.test_name} = {test.result}"
            }
    
    # Check extracted data for HIV history/exposure
    hiv_history = extracted_data.get('hiv_history', False)
    hiv_exposure = extracted_data.get('hiv_exposure', False)
    exposed_12_months = extracted_data.get('exposed_to_hiv_12_months', False)
    needle_tracks = extracted_data.get('needle_tracks', False)
    
    if hiv_history or hiv_exposure or exposed_12_months:
        if exposed_12_months:
            return {
                'result': EvaluationResult.UNACCEPTABLE,
                'reasoning': 'Exposed to HIV in preceding 12 months'
            }
        else:
            return {
                'result': EvaluationResult.MD_DISCRETION,
                'reasoning': 'HIV exposure history requires review'
            }
    
    if needle_tracks:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Needle tracks or signs of IV drug abuse'
        }
    
    # If all tests negative and no history, acceptable
    if hiv_tests:
        all_negative = all('negative' in test.result.lower() or 'non-reactive' in test.result.lower() 
                          for test in hiv_tests)
        if all_negative:
            return {
                'result': EvaluationResult.ACCEPTABLE,
                'reasoning': 'All HIV tests negative/non-reactive'
            }
    
    return {
        'result': EvaluationResult.MD_DISCRETION,
        'reasoning': 'HIV status unclear - requires review'
    }


def evaluate_hiv_aids_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate HIV/AIDS criteria."""
    aids_diagnosed = extracted_data.get('aids_diagnosed', False)
    hiv_infected = extracted_data.get('hiv_infected', False)
    positive_test = extracted_data.get('positive_test', False)
    needle_tracks = extracted_data.get('needle_tracks', False)
    iv_drug_abuse = extracted_data.get('iv_drug_abuse', False)
    
    if aids_diagnosed or hiv_infected or positive_test or needle_tracks or iv_drug_abuse:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Diagnosed with AIDS/HIV or signs of IV drug abuse'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No AIDS/HIV diagnosis or IV drug abuse signs'
    }


def evaluate_hepatitis_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Hepatitis criteria."""
    # Check lab results for hepatitis tests
    hep_tests = [lr for lr in lab_results 
                 if lr.test_type == TestType.SEROLOGY and 
                 any(hep in lr.test_name.lower() for hep in ['hepatitis', 'hbsag', 'hbv', 'hcv', 'anti-hbc', 'anti-hcv'])]
    
    # Check for positive/reactive results
    for test in hep_tests:
        result_lower = test.result.lower()
        if any(positive in result_lower for positive in ['positive', 'reactive', 'detected']):
            return {
                'result': EvaluationResult.UNACCEPTABLE,
                'reasoning': f"Positive hepatitis test result: {test.test_name} = {test.result}"
            }
    
    # Check extracted data
    resided_with_hepatitis = extracted_data.get('resided_with_hepatitis_person_12_months', False)
    hepatitis_c_treated_cured = extracted_data.get('hepatitis_c_treated_cured', False)
    unexplained_liver_disease = extracted_data.get('unexplained_liver_disease_symptoms', False)
    active_hepatitis = extracted_data.get('active_hepatitis_diagnosis', False)
    hepatitis_b_vaccine = extracted_data.get('hepatitis_b_vaccine', False)
    hbsab_positive = extracted_data.get('hbsab_positive', False)
    
    if resided_with_hepatitis:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Resided with hepatitis person in preceding 12 months'
        }
    
    if hepatitis_c_treated_cured:
        return {
            'result': EvaluationResult.ACCEPTABLE,
            'reasoning': 'Hepatitis C treated and cured'
        }
    
    if unexplained_liver_disease or active_hepatitis:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Unexplained liver disease or active hepatitis'
        }
    
    if hepatitis_b_vaccine or hbsab_positive:
        return {
            'result': EvaluationResult.ACCEPTABLE,
            'reasoning': 'Hepatitis B vaccine received or HBsAb positive'
        }
    
    # If all tests negative, acceptable
    if hep_tests:
        all_negative = all('negative' in test.result.lower() or 'non-reactive' in test.result.lower() 
                          for test in hep_tests)
        if all_negative:
            return {
                'result': EvaluationResult.ACCEPTABLE,
                'reasoning': 'All hepatitis tests negative/non-reactive'
            }
    
    return {
        'result': EvaluationResult.MD_DISCRETION,
        'reasoning': 'Hepatitis status unclear - requires review'
    }


def evaluate_sepsis_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Sepsis criteria."""
    sepsis_diagnosed = extracted_data.get('sepsis_diagnosis', False)
    bacteremia = extracted_data.get('bacteremia', False)
    septicemia = extracted_data.get('septicemia', False)
    sepsis_syndrome = extracted_data.get('sepsis_syndrome', False)
    systemic_infection = extracted_data.get('systemic_infection', False)
    septic_shock = extracted_data.get('septic_shock', False)
    
    if sepsis_diagnosed or bacteremia or septicemia or sepsis_syndrome or systemic_infection or septic_shock:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Documented medical diagnosis of sepsis or clinical evidence consistent with sepsis'
        }
    
    # Check blood culture results
    blood_cultures = [lr for lr in lab_results 
                     if lr.test_type == TestType.CULTURE and 'blood' in lr.test_name.lower()]
    
    for culture in blood_cultures:
        result_lower = culture.result.lower()
        if 'no growth' not in result_lower and 'negative' not in result_lower:
            # Positive blood culture - could indicate sepsis
            return {
                'result': EvaluationResult.MD_DISCRETION,
                'reasoning': f'Positive blood culture result: {culture.result} - requires review for sepsis'
            }
    
    uncertainty = extracted_data.get('uncertainty_regarding_sepsis', False)
    if uncertainty:
        return {
            'result': EvaluationResult.MD_DISCRETION,
            'reasoning': 'Uncertainty regarding sepsis findings'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No sepsis diagnosis or evidence found'
    }


def evaluate_septicemia_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Septicemia criteria."""
    septicemia_evidence = extracted_data.get('septicemia_evidence', False)
    positive_blood_culture = extracted_data.get('positive_blood_culture', False)
    
    # Check blood culture results
    blood_cultures = [lr for lr in lab_results 
                     if lr.test_type == TestType.CULTURE and 'blood' in lr.test_name.lower()]
    
    for culture in blood_cultures:
        result_lower = culture.result.lower()
        if 'no growth' not in result_lower and 'negative' not in result_lower:
            # Check if it might be contamination
            contamination_possibility = extracted_data.get('contamination_possibility', False)
            if contamination_possibility:
                return {
                    'result': EvaluationResult.MD_DISCRETION,
                    'reasoning': f'Positive blood culture may indicate contamination: {culture.result}'
                }
            else:
                return {
                    'result': EvaluationResult.UNACCEPTABLE,
                    'reasoning': f'Positive blood culture indicative of septicemia: {culture.result}'
                }
    
    if septicemia_evidence or positive_blood_culture:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Evidence or medical diagnosis of septicemia'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No septicemia evidence found'
    }


def evaluate_tuberculosis_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Tuberculosis criteria."""
    tb_diagnosis = extracted_data.get('tb_diagnosis', False)
    tb_symptoms = extracted_data.get('tb_symptoms_history', False)
    tb_test_positive = extracted_data.get('tb_test_positive', False)
    active_tb = extracted_data.get('active_tb_infection', False)
    
    if tb_diagnosis or tb_symptoms:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Diagnosis or history of symptoms associated with TB'
        }
    
    if active_tb:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Evidence of significant active TB infection'
        }
    
    if tb_test_positive:
        # Check if it's just a positive test without diagnosis/symptoms
        no_diagnosis = not extracted_data.get('tb_diagnosed', False)
        no_symptoms = not extracted_data.get('tb_symptoms', False)
        
        if no_diagnosis and no_symptoms:
            return {
                'result': EvaluationResult.MD_DISCRETION,
                'reasoning': 'Positive TB test but no diagnosis or symptoms - requires review'
            }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No TB diagnosis or symptoms found'
    }


def evaluate_high_risk_behavior_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate High Risk Behavior criteria."""
    sex_for_money_drugs_12_months = extracted_data.get('sex_for_money_drugs_12_months', False)
    female_male_partner_msm_5_years = extracted_data.get('female_male_partner_msm_5_years', False)
    sex_with_iv_drug_user_12_months = extracted_data.get('sex_with_iv_drug_user_12_months', False)
    sex_with_hiv_hepatitis_12_months = extracted_data.get('sex_with_hiv_hepatitis_12_months', False)
    sex_for_money_drugs_5_years = extracted_data.get('sex_for_money_drugs_5_years', False)
    male_msm_5_years = extracted_data.get('male_msm_5_years', False)
    iv_drug_use_5_years = extracted_data.get('iv_drug_use_5_years', False)
    iv_drug_use_more_than_5_years = extracted_data.get('iv_drug_use_more_than_5_years', False)
    
    # Unacceptable behaviors (12 months)
    if sex_for_money_drugs_12_months or female_male_partner_msm_5_years or sex_with_iv_drug_user_12_months or sex_with_hiv_hepatitis_12_months:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'High risk behavior in preceding 12 months'
        }
    
    # Unacceptable behaviors (5 years)
    if sex_for_money_drugs_5_years or male_msm_5_years or iv_drug_use_5_years:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'High risk behavior in past 5 years'
        }
    
    # MD discretion (more than 5 years ago)
    if iv_drug_use_more_than_5_years:
        return {
            'result': EvaluationResult.MD_DISCRETION,
            'reasoning': 'IV drug use more than 5 years ago - requires review'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No high risk behaviors identified'
    }


def evaluate_iv_drug_use_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate IV Drug Use criteria."""
    iv_drug_use_5_years = extracted_data.get('iv_drug_use_5_years', False)
    iv_drug_use_more_than_5_years = extracted_data.get('iv_drug_use_more_than_5_years', False)
    drug_type = extracted_data.get('drug_type', '')
    route = extracted_data.get('route', '')
    duration = extracted_data.get('duration', '')
    
    if iv_drug_use_5_years:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Injected drugs for non-medical reason in preceding five years'
        }
    
    if iv_drug_use_more_than_5_years:
        return {
            'result': EvaluationResult.MD_DISCRETION,
            'reasoning': f'IV drug use more than 5 years ago - type: {drug_type}, route: {route}, duration: {duration}'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No IV drug use history'
    }


def evaluate_incarceration_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Incarceration criteria."""
    incarceration_72_hours_12_months = extracted_data.get('incarceration_72_hours_12_months', False)
    incarceration_1_year = extracted_data.get('incarceration_1_year', False)
    incarceration_length = extracted_data.get('incarceration_length', '')
    incarceration_circumstances = extracted_data.get('incarceration_circumstances', '')
    
    if incarceration_72_hours_12_months:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Incarcerated for more than 72 consecutive hours in preceding 12 months'
        }
    
    if incarceration_1_year:
        return {
            'result': EvaluationResult.MD_DISCRETION,
            'reasoning': f'Incarcerated within one year - length: {incarceration_length}, circumstances: {incarceration_circumstances}'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No incarceration history in relevant time period'
    }


def evaluate_syphilis_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Syphilis criteria."""
    # Check lab results
    syphilis_tests = [lr for lr in lab_results 
                     if lr.test_type == TestType.SEROLOGY and 'syphilis' in lr.test_name.lower()]
    
    for test in syphilis_tests:
        result_lower = test.result.lower()
        if any(positive in result_lower for positive in ['positive', 'reactive', 'detected']):
            return {
                'result': EvaluationResult.UNACCEPTABLE,
                'reasoning': f"Positive syphilis test result: {test.test_name} = {test.result}"
            }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No positive syphilis test results'
    }


def evaluate_htlv_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate HTLV I/II criteria."""
    # Check lab results
    htlv_tests = [lr for lr in lab_results 
                  if lr.test_type == TestType.SEROLOGY and 'htlv' in lr.test_name.lower()]
    
    for test in htlv_tests:
        result_lower = test.result.lower()
        if any(positive in result_lower for positive in ['positive', 'reactive', 'detected']):
            return {
                'result': EvaluationResult.UNACCEPTABLE,
                'reasoning': f"Positive HTLV I/II test result: {test.test_name} = {test.result}"
            }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No positive HTLV I/II test results'
    }


def evaluate_west_nile_virus_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate West Nile Virus criteria."""
    wnv_diagnosis = extracted_data.get('wnv_diagnosis', False)
    wnv_onset_date = extracted_data.get('wnv_onset_date')
    days_since_diagnosis = extracted_data.get('days_since_diagnosis_or_onset', 999)
    days_since_test = extracted_data.get('days_since_test', 999)
    
    # Check lab results
    wnv_tests = [lr for lr in lab_results 
                 if lr.test_type == TestType.SEROLOGY and 'west nile' in lr.test_name.lower()]
    
    for test in wnv_tests:
        result_lower = test.result.lower()
        if any(positive in result_lower for positive in ['positive', 'reactive', 'detected']):
            if days_since_test <= 120:
                return {
                    'result': EvaluationResult.UNACCEPTABLE,
                    'reasoning': f"Positive WNV test in preceding 120 days: {test.test_name} = {test.result}"
                }
    
    if wnv_diagnosis and days_since_diagnosis <= 120:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': f"WNV diagnosis within 120 days: {days_since_diagnosis} days ago"
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No WNV diagnosis or positive test in preceding 120 days'
    }


def evaluate_infection_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Infection criteria."""
    sores_cutaneous_infection = extracted_data.get('sores_cutaneous_infection_breakdown', False)
    significant_active_infection = extracted_data.get('significant_active_infection', False)
    active_bacterial_viral_meningitis_encephalitis = extracted_data.get('active_bacterial_viral_meningitis_encephalitis', False)
    meningitis_resolved_6_months = extracted_data.get('meningitis_resolved_6_months', False)
    herpes_zoster_inactive_healed = extracted_data.get('herpes_zoster_inactive_healed', False)
    
    # Skin-specific: sores/cutaneous infection
    if sores_cutaneous_infection:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Sores and/or sites of cutaneous infection and/or breakdown'
        }
    
    if significant_active_infection:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Diagnosis of significant active infections'
        }
    
    if active_bacterial_viral_meningitis_encephalitis:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Active bacterial or viral meningitis or encephalitis'
        }
    
    if meningitis_resolved_6_months:
        return {
            'result': EvaluationResult.ACCEPTABLE,
            'reasoning': 'Meningitis infection resolved and clinical symptoms have not recurred within past six months'
        }
    
    if herpes_zoster_inactive_healed:
        return {
            'result': EvaluationResult.ACCEPTABLE,
            'reasoning': 'Herpes zoster (inactive or healed)'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No significant active infections found'
    }


def evaluate_cooling_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Cooling criteria."""
    cooling_time = extracted_data.get('cooling_time')
    cardiac_death_time = extracted_data.get('cardiac_death_time')
    skin_prep_time = extracted_data.get('skin_prep_time')
    
    # Simplified evaluation - actual implementation would parse and compare times
    cooled_within_12_hours = extracted_data.get('cooled_within_12_hours', False)
    skin_prep_within_24_hours = extracted_data.get('skin_prep_within_24_hours', False)
    not_cooled_within_12_hours = extracted_data.get('not_cooled_within_12_hours', False)
    skin_prep_within_15_hours = extracted_data.get('skin_prep_within_15_hours', False)
    cooled_then_not_cooled = extracted_data.get('cooled_then_not_cooled', False)
    not_cooled_time = extracted_data.get('not_cooled_time_cumulative', 0)
    
    if cooled_within_12_hours and skin_prep_within_24_hours:
        return {
            'result': EvaluationResult.ACCEPTABLE,
            'reasoning': 'Body cooled within 12 hours of cardiac death, skin prep within 24 hours'
        }
    
    if not_cooled_within_12_hours and skin_prep_within_15_hours:
        return {
            'result': EvaluationResult.ACCEPTABLE,
            'reasoning': 'Body not cooled within 12 hours, skin prep within 15 hours'
        }
    
    if cooled_then_not_cooled and not_cooled_time <= 15:
        return {
            'result': EvaluationResult.ACCEPTABLE,
            'reasoning': f'Body cooled then not cooled, not cooled time ({not_cooled_time}h) does not exceed 15 cumulative hours'
        }
    
    return {
        'result': EvaluationResult.MD_DISCRETION,
        'reasoning': 'Cooling criteria unclear - requires review'
    }


def evaluate_autopsy_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Autopsy criteria."""
    autopsy_performed = extracted_data.get('autopsy_performed', False)
    autopsy_type = extracted_data.get('autopsy_type', '')
    tissue_type = extracted_data.get('tissue_type', '')
    
    # For skin: autopsy is acceptable
    if tissue_type == 'skin':
        return {
            'result': EvaluationResult.ACCEPTABLE,
            'reasoning': 'Autopsy is acceptable for skin'
        }
    
    # For musculoskeletal: en bloc and OA grafts require limited autopsy
    if tissue_type in ['en_bloc_oa_grafts']:
        if autopsy_performed and 'limited' not in autopsy_type.lower():
            return {
                'result': EvaluationResult.MD_DISCRETION,
                'reasoning': 'En bloc and OA grafts require limited autopsy (head only, toxicology only)'
            }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'Autopsy criteria met'
    }


def evaluate_toxicology_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Toxicology criteria."""
    toxicology_performed = extracted_data.get('toxicology_performed', False)
    toxicology_positive = extracted_data.get('toxicology_positive', False)
    
    if toxicology_positive:
        return {
            'result': EvaluationResult.MD_DISCRETION,
            'reasoning': 'Positive toxicology screen or test'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No positive toxicology results'
    }


def evaluate_autoimmune_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Autoimmune diseases criteria."""
    autoimmune_type = (extracted_data.get('autoimmune_disease_type') or '').lower()
    skin_manifestations = extracted_data.get('skin_manifestations', False)
    tissue_type = extracted_data.get('tissue_type', '')
    
    # Unacceptable for both
    unacceptable_autoimmune = ['polyarteritis nodosa', 'sarcoidosis', 'progressive systemic sclerosis', 'scleroderma']
    if any(ua in autoimmune_type for ua in unacceptable_autoimmune):
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': f'History of {autoimmune_type} - unacceptable for both tissue types'
        }
    
    # MD discretion for skin if no skin manifestations
    md_discretion_autoimmune = [
        'rheumatoid arthritis', 'systemic lupus erythematosus', 'lupus', 'sle',
        'polymyositis', 'sjogren', 'ankylosing spondylitis', 'psoriatic arthritis', 'reiters'
    ]
    
    if any(md in autoimmune_type for md in md_discretion_autoimmune):
        if tissue_type == 'skin' and not skin_manifestations:
            return {
                'result': EvaluationResult.MD_DISCRETION,
                'reasoning': f'History of {autoimmune_type} with no skin manifestations - MD discretion for skin'
            }
        else:
            return {
                'result': EvaluationResult.UNACCEPTABLE,
                'reasoning': f'History of {autoimmune_type} - unacceptable for musculoskeletal'
            }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No autoimmune disease history'
    }


def evaluate_dementia_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Dementia criteria."""
    dementia_unknown_etiology = extracted_data.get('dementia_unknown_etiology', False)
    memory_loss_unknown_etiology = extracted_data.get('memory_loss_unknown_etiology', False)
    dementia_caused_by_cva_brain_tumor_trauma_toxic = extracted_data.get('dementia_caused_by_cva_brain_tumor_trauma_toxic', False)
    no_tse_evidence = extracted_data.get('no_tse_evidence', False)
    
    if dementia_unknown_etiology or memory_loss_unknown_etiology:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Diagnosis of neurological or demyelinating diseases of unknown etiology'
        }
    
    if dementia_caused_by_cva_brain_tumor_trauma_toxic and no_tse_evidence:
        return {
            'result': EvaluationResult.MD_DISCRETION,
            'reasoning': 'Confirmed diagnosis caused by CVA, brain tumor, head trauma, or toxic/metabolic dementia with no TSE evidence'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No dementia diagnosis or acceptable cause identified'
    }


def evaluate_bleeding_disorder_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Bleeding Disorder (Hemophilia) criteria."""
    clotting_factor_concentrates_more_than_5_years_ago = extracted_data.get('clotting_factor_concentrates_more_than_5_years_ago', False)
    
    if clotting_factor_concentrates_more_than_5_years_ago:
        return {
            'result': EvaluationResult.MD_DISCRETION,
            'reasoning': 'Receipt of human-derived clotting factor concentrates more than 5 years ago'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No bleeding disorder history found'
    }


def evaluate_bone_disease_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Bone Disease criteria."""
    bone_disease_type = (extracted_data.get('bone_disease_type') or '').lower()
    tissue_type = extracted_data.get('tissue_type', '')
    
    unacceptable_bone_diseases = ['osteomalacia', 'metabolic_bone_disease', 'osteoporosis']
    acceptable_bone_diseases = ['osteoarthritis', 'overuse']
    
    if any(ubd in bone_disease_type for ubd in unacceptable_bone_diseases):
        if tissue_type == 'musculoskeletal':
            return {
                'result': EvaluationResult.UNACCEPTABLE,
                'reasoning': f'History of {bone_disease_type} - unacceptable for musculoskeletal'
            }
    
    if any(abd in bone_disease_type for abd in acceptable_bone_diseases):
        return {
            'result': EvaluationResult.ACCEPTABLE,
            'reasoning': f'Stiff and sore joints caused by {bone_disease_type} - acceptable'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No bone disease history found'
    }


def evaluate_bowel_perforation_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Bowel Perforation criteria."""
    perforation_during_dissection = extracted_data.get('perforation_during_dissection', False)
    bowel_contents_observed = extracted_data.get('bowel_contents_observed', False)
    post_autopsy = extracted_data.get('post_autopsy', False)
    tissue_separating_hemipelvis = extracted_data.get('tissue_separating_hemipelvis', False)
    
    if perforation_during_dissection or bowel_contents_observed:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Bowel perforation during dissection or observation of bowel contents'
        }
    
    if post_autopsy and tissue_separating_hemipelvis:
        return {
            'result': EvaluationResult.ACCEPTABLE,
            'reasoning': 'Post-autopsy case with tissue separating hemi-pelvis from abdominal cavity'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No bowel perforation issues found'
    }


def evaluate_chagas_disease_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Chagas disease criteria."""
    chagas_treated_within_3_years = extracted_data.get('chagas_treated_within_3_years', False)
    
    if chagas_treated_within_3_years:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Donors treated for trypanosoma cruzi within past 3 years'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No Chagas disease treatment within past 3 years'
    }


def evaluate_chicken_pox_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Chicken Pox criteria."""
    significant_active_infection = extracted_data.get('significant_active_infection', False)
    chicken_pox_active = extracted_data.get('chicken_pox_active', False)
    
    if significant_active_infection or chicken_pox_active:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Evidence of significant active infections'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No active chicken pox infection found'
    }


def evaluate_contamination_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Contamination criteria."""
    tissue_dropped_outside_sterile_field = extracted_data.get('tissue_dropped_outside_sterile_field', False)
    
    if tissue_dropped_outside_sterile_field:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Tissue dropped outside sterile field shall be returned to body at end of case'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No contamination issues found'
    }


def evaluate_covid_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate COVID criteria."""
    covid_symptoms = extracted_data.get('covid_symptoms', False)
    covid_risk_factors = extracted_data.get('covid_risk_factors', False)
    
    if covid_symptoms or covid_risk_factors:
        return {
            'result': EvaluationResult.MD_DISCRETION,
            'reasoning': 'Donors with clinical symptoms or risk factors'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No COVID symptoms or risk factors found'
    }


def evaluate_creutzfeldt_jakob_disease_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Creutzfeldt-Jakob disease criteria."""
    cjd_diagnosis = extracted_data.get('cjd_diagnosis', False)
    cjd_family_history_non_iatrogenic = extracted_data.get('cjd_family_history_non_iatrogenic', False)
    dura_mater_transplant = extracted_data.get('dura_mater_transplant', False)
    pituitary_growth_hormone = extracted_data.get('pituitary_growth_hormone', False)
    cjd_blood_relatives = extracted_data.get('cjd_blood_relatives', False)
    gene_sequencing_no_mutation = extracted_data.get('gene_sequencing_no_mutation', False)
    
    if cjd_diagnosis or cjd_family_history_non_iatrogenic:
        if gene_sequencing_no_mutation:
            return {
                'result': EvaluationResult.ACCEPTABLE,
                'reasoning': 'Laboratory testing shows no mutation associated with familial CJD'
            }
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Diagnosis of CJD or history of non-iatrogenic CJD in a blood relative'
        }
    
    if dura_mater_transplant or pituitary_growth_hormone or cjd_blood_relatives:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Donors with increased risk: receipt of non-synthetic dura mater transplant, human pituitary-derived growth hormone, or blood relatives diagnosed with CJD'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No CJD diagnosis or risk factors found'
    }


def evaluate_delirium_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Delirium criteria."""
    delirium_caused_by_toxic_metabolic = extracted_data.get('delirium_caused_by_toxic_metabolic', False)
    delirium_caused_by_head_trauma = extracted_data.get('delirium_caused_by_head_trauma', False)
    
    if delirium_caused_by_toxic_metabolic or delirium_caused_by_head_trauma:
        return {
            'result': EvaluationResult.MD_DISCRETION,
            'reasoning': 'Diagnosis caused by toxic/metabolic diseases or recent head trauma should be evaluated'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No delirium diagnosis found'
    }


def evaluate_diabetes_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Diabetes criteria."""
    amputation_diabetic_foot_ulcer_osteomyelitis = extracted_data.get('amputation_diabetic_foot_ulcer_osteomyelitis', False)
    surgery_resolution_greater_than_12_months = extracted_data.get('surgery_resolution_greater_than_12_months', False)
    
    if amputation_diabetic_foot_ulcer_osteomyelitis and surgery_resolution_greater_than_12_months:
        return {
            'result': EvaluationResult.MD_DISCRETION,
            'reasoning': 'Amputation for diabetic foot ulcer with underlying osteomyelitis if surgery and resolution is greater than 12 months'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No diabetes-related amputation issues found'
    }


def evaluate_drowning_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Drowning criteria."""
    drowning_occurred = extracted_data.get('drowning_occurred', False)
    tissue_type = extracted_data.get('tissue_type', '')
    
    if drowning_occurred and tissue_type == 'skin':
        return {
            'result': EvaluationResult.MD_DISCRETION,
            'reasoning': 'Drowning occurred - evaluated on a case-by-case basis for skin donors. Consider: type of water, time in water, resuscitation success, survival length, signs of infection/sepsis'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No drowning incident found'
    }


def evaluate_encephalitis_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Encephalitis criteria."""
    encephalitis_current = extracted_data.get('encephalitis_current', False)
    encephalitis_past = extracted_data.get('encephalitis_past', False)
    
    if encephalitis_current or encephalitis_past:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Current or past history of encephalitis'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No encephalitis history found'
    }


def evaluate_fracture_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Fracture criteria."""
    fracture_type = (extracted_data.get('fracture_type') or '').lower()
    
    if 'open' in fracture_type:
        return {
            'result': EvaluationResult.ACCEPTABLE,
            'reasoning': 'Open fractures shall be draped out of operative field and tissues involved shall not be recovered'
        }
    
    if 'simple' in fracture_type and 'closed' in fracture_type:
        return {
            'result': EvaluationResult.ACCEPTABLE,
            'reasoning': 'Simple closed fractures should be recovered last but prior to the hemi-pelvis'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No fracture issues found'
    }


def evaluate_gout_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Gout criteria."""
    acute_gout = extracted_data.get('acute_gout', False)
    gout_diagnosis = extracted_data.get('gout_diagnosis', False)
    
    if acute_gout:
        return {
            'result': EvaluationResult.MD_DISCRETION,
            'reasoning': 'Acute gout will necessitate exclusion of musculoskeletal soft tissues and fresh soft tissue grafts'
        }
    
    if gout_diagnosis:
        return {
            'result': EvaluationResult.MD_DISCRETION,
            'reasoning': 'Gout diagnosis - obtain details: when diagnosed, how treated, current status, which joints affected'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No gout diagnosis found'
    }


def evaluate_growth_hormone_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Growth Hormone criteria."""
    human_pituitary_growth_hormone = extracted_data.get('human_pituitary_growth_hormone', False)
    recombinant_growth_hormone = extracted_data.get('recombinant_growth_hormone', False)
    
    if human_pituitary_growth_hormone:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Receipt of human pituitary-derived growth hormone (pit-hGH)'
        }
    
    if recombinant_growth_hormone:
        return {
            'result': EvaluationResult.ACCEPTABLE,
            'reasoning': 'Receipt of recombinant growth hormone - acceptable'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No growth hormone receipt found'
    }


def evaluate_guillain_barre_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Guillain-Barré syndrome criteria."""
    guillain_barre_past_history = extracted_data.get('guillain_barre_past_history', False)
    medically_treated = extracted_data.get('medically_treated', False)
    full_recovery = extracted_data.get('full_recovery', False)
    no_recurrence = extracted_data.get('no_recurrence', False)
    
    if guillain_barre_past_history and medically_treated and full_recovery and no_recurrence:
        return {
            'result': EvaluationResult.MD_DISCRETION,
            'reasoning': 'Well-documented, past history that was medically treated with full recovery and no recurrence'
        }
    
    if guillain_barre_past_history:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Guillain-Barré syndrome history without documented full recovery'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No Guillain-Barré syndrome history found'
    }


def evaluate_hemodialysis_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Hemodialysis criteria."""
    short_term_hemodialysis_acute_renal_failure = extracted_data.get('short_term_hemodialysis_acute_renal_failure', False)
    long_term_hemodialysis_chronic_kidney_failure = extracted_data.get('long_term_hemodialysis_chronic_kidney_failure', False)
    
    if long_term_hemodialysis_chronic_kidney_failure:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'History of long-term hemodialysis for treatment of chronic kidney failure'
        }
    
    if short_term_hemodialysis_acute_renal_failure:
        return {
            'result': EvaluationResult.MD_DISCRETION,
            'reasoning': 'Short term hemodialysis for acute renal failure prior to death'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No hemodialysis history found'
    }


def evaluate_herpes_ii_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Herpes II (genital herpes) criteria."""
    significant_active_infection = extracted_data.get('significant_active_infection', False)
    herpes_ii_active = extracted_data.get('herpes_ii_active', False)
    
    if significant_active_infection or herpes_ii_active:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Evidence of significant active infections'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No active herpes II infection found'
    }


def evaluate_high_risk_non_iv_drug_use_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate High Risk Non-IV Related Drug Use criteria."""
    non_iv_drug_use = extracted_data.get('non_iv_drug_use', False)
    
    if non_iv_drug_use:
        return {
            'result': EvaluationResult.MD_DISCRETION,
            'reasoning': 'Past or present history of illegal use of drugs or drug addiction - factors in determining donor suitability include: type of medication/drug, route of administration, source, length of use, current use, reliability of social history, health and physical status, cause of death, circumstances surrounding death, sexual activity, toxicology results'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No non-IV related drug use found'
    }


def evaluate_hiv_group_o_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate HIV Group O criteria."""
    born_lived_africa_countries = extracted_data.get('born_lived_africa_countries', False)
    sexual_partner_africa_countries = extracted_data.get('sexual_partner_africa_countries', False)
    blood_transfusion_africa = extracted_data.get('blood_transfusion_africa', False)
    medical_treatment_africa = extracted_data.get('medical_treatment_africa', False)
    
    # Africa countries: Cameroon, Central African Republic, Chad, Congo, Equatorial Guinea, Gabon, Niger, Nigeria, Senegal, Togo, Zambia, Benin, Kenya (after 1977)
    if born_lived_africa_countries or sexual_partner_africa_countries:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Donors or their sexual partners who were born or lived in certain countries of Africa'
        }
    
    if blood_transfusion_africa or medical_treatment_africa:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Receipt of a blood transfusion or any medical treatment that involved blood in countries of Africa'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No HIV Group O risk factors found'
    }


def evaluate_hiv_hepatitis_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate HIV/Hepatitis criteria."""
    medications_unknown_reason = extracted_data.get('medications_unknown_reason', False)
    aids_prophylactic_treatment = extracted_data.get('aids_prophylactic_treatment', False)
    hepatitis_prophylactic_treatment = extracted_data.get('hepatitis_prophylactic_treatment', False)
    
    if medications_unknown_reason or aids_prophylactic_treatment or hepatitis_prophylactic_treatment:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Medication(s) taken for unknown reason or treatment or prophylactic treatment of AIDS or hepatitis B or C'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No HIV/Hepatitis medication concerns found'
    }


def evaluate_hiv_hepatitis_communicable_disease_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate HIV/Hepatitis/active relevant communicable disease criteria."""
    physical_evidence_hiv = extracted_data.get('physical_evidence_hiv', False)
    physical_evidence_hepatitis = extracted_data.get('physical_evidence_hepatitis', False)
    physical_evidence_communicable_disease = extracted_data.get('physical_evidence_communicable_disease', False)
    
    if physical_evidence_hiv or physical_evidence_hepatitis or physical_evidence_communicable_disease:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Physical evidence of conditions or physical characteristics of HIV infection (AIDS), hepatitis or active relevant communicable diseases'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No physical evidence of HIV, hepatitis, or communicable diseases found'
    }


def evaluate_immunizations_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Immunizations criteria."""
    live_virus_vaccine = extracted_data.get('live_virus_vaccine', False)
    four_weeks_since_last_dose = extracted_data.get('four_weeks_since_last_dose', False)
    live_attenuated_virus_vaccine = extracted_data.get('live_attenuated_virus_vaccine', False)
    
    if live_virus_vaccine:
        if four_weeks_since_last_dose:
            return {
                'result': EvaluationResult.ACCEPTABLE,
                'reasoning': 'Donors are acceptable four weeks after the last dose for vaccinations that contain live virus'
            }
        else:
            return {
                'result': EvaluationResult.UNACCEPTABLE,
                'reasoning': 'Live virus vaccine received less than four weeks ago'
            }
    
    if live_attenuated_virus_vaccine:
        return {
            'result': EvaluationResult.ACCEPTABLE,
            'reasoning': 'Receipt of vaccines of live, attenuated virus if they meet all other donor criteria'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No immunization concerns found'
    }


def evaluate_jaundice_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Jaundice criteria."""
    jaundice_areas = extracted_data.get('jaundice_areas', False)
    jaundice_unexplained_undiagnosed = extracted_data.get('jaundice_unexplained_undiagnosed', False)
    not_drugs_mononucleosis_bile_duct = extracted_data.get('not_drugs_mononucleosis_bile_duct', False)
    tissue_type = extracted_data.get('tissue_type', '')
    
    if tissue_type == 'skin' and jaundice_areas:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Skin shall not be recovered from areas with jaundice'
        }
    
    if jaundice_unexplained_undiagnosed and not_drugs_mononucleosis_bile_duct:
        return {
            'result': EvaluationResult.MD_DISCRETION,
            'reasoning': 'History or symptoms of unexplained or undiagnosed jaundice - if cause is related to drugs, infectious mononucleosis, or bile duct obstruction, may be acceptable'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No jaundice concerns found'
    }


def evaluate_leprosy_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Leprosy criteria."""
    leprosy_current = extracted_data.get('leprosy_current', False)
    leprosy_past = extracted_data.get('leprosy_past', False)
    
    if leprosy_current or leprosy_past:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Current or past history of leprosy'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No leprosy history found'
    }


def evaluate_liver_disease_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Liver disease criteria."""
    unexplained_liver_disease_symptoms = extracted_data.get('unexplained_liver_disease_symptoms', False)
    
    if unexplained_liver_disease_symptoms:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Clinical signs and symptoms of unexplained or undiagnosed liver disease, hepatosplenomegaly'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No unexplained liver disease found'
    }


def evaluate_long_term_illness_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Long Term Illness criteria."""
    long_term_illness = extracted_data.get('long_term_illness', False)
    
    if long_term_illness:
        return {
            'result': EvaluationResult.MD_DISCRETION,
            'reasoning': 'Illness involving genetic defects, chronic debilitating disease, as well as diseases of unknown/unclear etiologies - obtain details: history of disease, treatment, general health, activity level, recent/current secondary infections'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No long-term illness found'
    }


def evaluate_long_term_steroid_therapy_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Long Term Steroid therapy criteria."""
    long_term_steroid_therapy = extracted_data.get('long_term_steroid_therapy', False)
    
    if long_term_steroid_therapy:
        return {
            'result': EvaluationResult.MD_DISCRETION,
            'reasoning': 'Possible indication of illnesses or conditions that would exclude tissue donation'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No long-term steroid therapy found'
    }


def evaluate_long_term_infection_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate long-term (more than 3 months) bacterial, fungal, viral infections, or diseases of unknown origin criteria."""
    long_term_infection_current = extracted_data.get('long_term_infection_current', False)
    
    if long_term_infection_current:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Current history of long-term (more than 3 months) bacterial, fungal, viral infections, or diseases of unknown origin'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No long-term infection found'
    }


def evaluate_lou_gehrig_disease_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Lou Gehrig's disease (ALS) criteria."""
    als_current = extracted_data.get('als_current', False)
    als_past = extracted_data.get('als_past', False)
    
    if als_current or als_past:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Current or past history of Lou Gehrig\'s disease (ALS)'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No ALS history found'
    }


def evaluate_malaria_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Malaria criteria."""
    malaria_resident_arrived_us_3_years = extracted_data.get('malaria_resident_arrived_us_3_years', False)
    malaria_treated_within_3_years = extracted_data.get('malaria_treated_within_3_years', False)
    malaria_travel_6_months_no_prophylaxis = extracted_data.get('malaria_travel_6_months_no_prophylaxis', False)
    
    if malaria_resident_arrived_us_3_years:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Residents of malarial areas who arrived in the U.S. within 3 years'
        }
    
    if malaria_treated_within_3_years:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Treated for malaria within past three years'
        }
    
    if malaria_travel_6_months_no_prophylaxis:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Visited endemic malarial areas in past six months and did not take anti-malarial drugs for prophylaxis'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No malaria risk factors found'
    }


def evaluate_measles_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Measles criteria."""
    significant_active_infection = extracted_data.get('significant_active_infection', False)
    measles_active = extracted_data.get('measles_active', False)
    
    if significant_active_infection or measles_active:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Evidence of significant active infections'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No active measles infection found'
    }


def evaluate_meningitis_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Meningitis criteria."""
    significant_active_infection = extracted_data.get('significant_active_infection', False)
    meningitis_active = extracted_data.get('meningitis_active', False)
    
    if significant_active_infection or meningitis_active:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Evidence of significant active infections'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No active meningitis infection found'
    }


def evaluate_multiple_sclerosis_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Multiple Sclerosis (MS) criteria."""
    ms_current = extracted_data.get('ms_current', False)
    ms_past = extracted_data.get('ms_past', False)
    
    if ms_current or ms_past:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Current or past history of Multiple Sclerosis'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No Multiple Sclerosis history found'
    }


def evaluate_mumps_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Mumps criteria."""
    significant_active_infection = extracted_data.get('significant_active_infection', False)
    mumps_active = extracted_data.get('mumps_active', False)
    
    if significant_active_infection or mumps_active:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Evidence of significant active infections'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No active mumps infection found'
    }


def evaluate_muscular_dystrophy_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Muscular dystrophy criteria."""
    muscular_dystrophy = extracted_data.get('muscular_dystrophy', False)
    
    if muscular_dystrophy:
        return {
            'result': EvaluationResult.MD_DISCRETION,
            'reasoning': 'Muscular dystrophy - obtain as many details as possible'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No muscular dystrophy found'
    }


def evaluate_needle_stick_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Needle Stick criteria."""
    exposed_12_months_hiv_hbv_hcv = extracted_data.get('exposed_12_months_hiv_hbv_hcv', False)
    sexual_relations_exposed_person_12_months = extracted_data.get('sexual_relations_exposed_person_12_months', False)
    
    if exposed_12_months_hiv_hbv_hcv:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Exposed in preceding 12 months to known or suspected HIV, HBV, and/or HCV infected blood through percutaneous inoculation or through contact with an open wound, non-intact skin, or mucous membrane'
        }
    
    if sexual_relations_exposed_person_12_months:
        return {
            'result': EvaluationResult.MD_DISCRETION,
            'reasoning': 'Donor had sexual relations with a person who has been exposed in preceding 12 months to known or suspected HIV, HBV, and/or HCV infected blood'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No needle stick exposure found'
    }


def evaluate_non_tumor_related_shunts_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Non-tumor Related Shunts criteria."""
    non_tumor_related_shunts = extracted_data.get('non_tumor_related_shunts', False)
    
    if non_tumor_related_shunts:
        return {
            'result': EvaluationResult.MD_DISCRETION,
            'reasoning': 'Non-tumor related shunts - obtain the following information: length of time patient was shunted, history of recent/current secondary infections and complications'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No non-tumor related shunts found'
    }


def evaluate_osteomyelitis_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Osteomyelitis criteria."""
    osteomyelitis_past_history = extracted_data.get('osteomyelitis_past_history', False)
    prior_age_12_females = extracted_data.get('prior_age_12_females', False)
    prior_age_14_males = extracted_data.get('prior_age_14_males', False)
    no_treatment_10_years = extracted_data.get('no_treatment_10_years', False)
    osteomyelitis_other_history = extracted_data.get('osteomyelitis_other_history', False)
    gender = (donor_info.get('gender') or '').lower()
    
    if osteomyelitis_other_history:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Any other osteomyelitis history is an exclusion for all musculoskeletal tissues'
        }
    
    if osteomyelitis_past_history:
        if (gender == 'female' and prior_age_12_females) or (gender == 'male' and prior_age_14_males):
            if no_treatment_10_years:
                return {
                    'result': EvaluationResult.ACCEPTABLE,
                    'reasoning': f'Adult donors with a past history prior to age 12 years (females) or 14 years (males), without further treatment during the ten years post incident'
                }
    
    if osteomyelitis_past_history:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Osteomyelitis history does not meet acceptable criteria'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No osteomyelitis history found'
    }


def evaluate_perianal_condyloma_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Perianal condyloma criteria."""
    male_donor = (donor_info.get('gender') or '').lower() == 'male'
    anal_intercourse_evidence = extracted_data.get('anal_intercourse_evidence', False)
    
    if male_donor and anal_intercourse_evidence:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Male donors with evidence of anal intercourse'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No perianal condyloma concerns found'
    }


def evaluate_genitalia_piercing_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Genitalia Piercing criteria."""
    genitalia_piercing = extracted_data.get('genitalia_piercing', False)
    
    if genitalia_piercing:
        return {
            'result': EvaluationResult.MD_DISCRETION,
            'reasoning': 'Genitalia piercing(s) will be evaluated case by case'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No genitalia piercing found'
    }


def evaluate_piercing_acupuncture_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Piercing/acupuncture criteria."""
    shared_instruments_12_months = extracted_data.get('shared_instruments_12_months', False)
    piercing_acupuncture_outside_us_canada_12_months = extracted_data.get('piercing_acupuncture_outside_us_canada_12_months', False)
    
    if shared_instruments_12_months:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Acupuncture, ear or body piercing in which shared instruments are known to have been used within 12 months prior to donation'
        }
    
    if piercing_acupuncture_outside_us_canada_12_months:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Piercing(s) and/or acupuncture done outside of the US or Canada within the preceding 12 months'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No piercing/acupuncture concerns found'
    }


def evaluate_prosthetic_implants_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Prosthetic Implants criteria."""
    prosthetic_implants = extracted_data.get('prosthetic_implants', False)
    
    if prosthetic_implants:
        return {
            'result': EvaluationResult.MD_DISCRETION,
            'reasoning': 'Bone with implants may be recovered. Bone and soft tissue may be cut below or above, and prosthetic device left in situ'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No prosthetic implants found'
    }


def evaluate_rabies_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Rabies criteria."""
    bitten_scratched_suspected_rabies_6_months = extracted_data.get('bitten_scratched_suspected_rabies_6_months', False)
    suspected_rabies = extracted_data.get('suspected_rabies', False)
    rabies_vaccine_after_bite = extracted_data.get('rabies_vaccine_after_bite', False)
    one_year_after_last_shot = extracted_data.get('one_year_after_last_shot', False)
    
    if bitten_scratched_suspected_rabies_6_months:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Bitten and/or scratched by an animal suspected to be infected within past six months'
        }
    
    if suspected_rabies:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Suspected rabies'
        }
    
    if rabies_vaccine_after_bite and one_year_after_last_shot:
        return {
            'result': EvaluationResult.ACCEPTABLE,
            'reasoning': 'Receipt of rabies vaccine after bite from rabid animal one year after last shot'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No rabies concerns found'
    }


def evaluate_refused_blood_donor_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Refused as blood donor criteria."""
    deferred_unknown_reasons = extracted_data.get('deferred_unknown_reasons', False)
    deferred_diseases_infections = extracted_data.get('deferred_diseases_infections', False)
    deferred_positive_serologic = extracted_data.get('deferred_positive_serologic', False)
    deferred_other_circumstances = extracted_data.get('deferred_other_circumstances', False)
    
    if deferred_unknown_reasons or deferred_diseases_infections or deferred_positive_serologic:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Deferred for unknown reasons or for history of diseases, infections, or positive serologic testing results'
        }
    
    if deferred_other_circumstances:
        return {
            'result': EvaluationResult.MD_DISCRETION,
            'reasoning': 'Deferred as blood donor due to other circumstances not considered an exclusion for tissue donation'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No blood donor deferral found'
    }


def evaluate_reyes_syndrome_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Reye's Syndrome criteria."""
    reyes_syndrome_past = extracted_data.get('reyes_syndrome_past', False)
    reyes_syndrome_current = extracted_data.get('reyes_syndrome_current', False)
    
    if reyes_syndrome_past or reyes_syndrome_current:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Past or current medical history of Reye\'s Syndrome'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No Reye\'s Syndrome history found'
    }


def evaluate_rheumatic_fever_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Rheumatic Fever criteria."""
    pericardium_tissue_donor = (extracted_data.get('tissue_type') or '').lower() == 'pericardium'
    rheumatic_fever = extracted_data.get('rheumatic_fever', False)
    bacterial_endocarditis = extracted_data.get('bacterial_endocarditis', False)
    semilunar_valvular_heart_disease = extracted_data.get('semilunar_valvular_heart_disease', False)
    heart_disease_unknown_etiology = extracted_data.get('heart_disease_unknown_etiology', False)
    
    if pericardium_tissue_donor and (rheumatic_fever or bacterial_endocarditis or semilunar_valvular_heart_disease or heart_disease_unknown_etiology):
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Pericardium tissue donors with history of rheumatic fever, or history of or presence of bacterial endocarditis, or semilunar valvular heart disease, or heart disease of unknown etiology'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No rheumatic fever concerns found'
    }


def evaluate_rubella_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Rubella criteria."""
    significant_active_infection = extracted_data.get('significant_active_infection', False)
    rubella_active = extracted_data.get('rubella_active', False)
    
    if significant_active_infection or rubella_active:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Evidence of significant active infections'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No active rubella infection found'
    }


def evaluate_std_sti_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Sexually Transmitted Diseases (STDs) or Sexually Transmitted infections (STIs) criteria."""
    std_sti_type = (extracted_data.get('std_sti_type') or '').lower()
    treated_within_12_months = extracted_data.get('treated_within_12_months', False)
    std_sti_other = extracted_data.get('std_sti_other', False)
    std_sti_history_more_than_12_months = extracted_data.get('std_sti_history_more_than_12_months', False)
    sexual_relations_active_std_sti_12_months = extracted_data.get('sexual_relations_active_std_sti_12_months', False)
    
    if (std_sti_type in ['syphilis', 'gonorrhea']) and treated_within_12_months:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Donors diagnosed with or treated for syphilis or gonorrhea within preceding 12 months'
        }
    
    if std_sti_other and treated_within_12_months:
        return {
            'result': EvaluationResult.MD_DISCRETION,
            'reasoning': 'Donors diagnosed with or treated for STDs/STIs other than syphilis or gonorrhea within preceding 12 months'
        }
    
    if std_sti_history_more_than_12_months:
        return {
            'result': EvaluationResult.MD_DISCRETION,
            'reasoning': 'Donors with previous history of symptoms or conditions or a history of STDs/STIs more than 12 months ago'
        }
    
    if sexual_relations_active_std_sti_12_months:
        return {
            'result': EvaluationResult.MD_DISCRETION,
            'reasoning': 'Donors who had sexual relations with an individual who had an active STD/STI within preceding 12 months'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No STD/STI concerns found'
    }


def evaluate_smallpox_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Smallpox criteria."""
    smallpox_vaccine = extracted_data.get('smallpox_vaccine', False)
    
    if smallpox_vaccine:
        return {
            'result': EvaluationResult.MD_DISCRETION,
            'reasoning': 'Smallpox vaccine - obtain the following information: date vaccine obtained, presence or absence of scab, how scab removed, any complications'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No smallpox vaccine found'
    }


def evaluate_sirs_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Systemic Inflammatory Response Syndrome (SIRS) criteria."""
    sirs_due_to_infection = extracted_data.get('sirs_due_to_infection', False)
    sirs_other_causes = extracted_data.get('sirs_other_causes', False)
    
    if sirs_due_to_infection:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'SIRS due to infection'
        }
    
    if sirs_other_causes:
        return {
            'result': EvaluationResult.MD_DISCRETION,
            'reasoning': 'SIRS from other causes may be acceptable and will be reviewed'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No SIRS found'
    }


def evaluate_tattoo_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Tattoo criteria."""
    tattoo_shared_instruments_12_months = extracted_data.get('tattoo_shared_instruments_12_months', False)
    tattoo_outside_us_canada_12_months = extracted_data.get('tattoo_outside_us_canada_12_months', False)
    tattoo_high_risk_lifestyle_12_months = extracted_data.get('tattoo_high_risk_lifestyle_12_months', False)
    tattoo_over_12_months = extracted_data.get('tattoo_over_12_months', False)
    tattoo_areas = extracted_data.get('tattoo_areas', False)
    tissue_type = extracted_data.get('tissue_type', '')
    
    if tissue_type == 'skin' and tattoo_areas:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Skin areas with tattoos'
        }
    
    if tattoo_shared_instruments_12_months or tattoo_outside_us_canada_12_months or tattoo_high_risk_lifestyle_12_months:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Donors who within 12 months prior to donation have undergone tattooing with shared instruments, tattoos done outside of the US or Canada, or tattoos indicative of high-risk lifestyles'
        }
    
    if tattoo_over_12_months:
        return {
            'result': EvaluationResult.MD_DISCRETION,
            'reasoning': 'Tattoos over 12 months old may be acceptable'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No tattoo concerns found'
    }


def evaluate_transplant_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Transplant criteria."""
    transplant_type = extracted_data.get('transplant_type', '')
    xenograft_non_living_cells = extracted_data.get('xenograft_non_living_cells', False)
    xenograft_living_cells = extracted_data.get('xenograft_living_cells', False)
    human_tissue_transplant_screened = extracted_data.get('human_tissue_transplant_screened', False)
    non_synthetic_dura_mater = extracted_data.get('non_synthetic_dura_mater', False)
    epicel_receipt = extracted_data.get('epicel_receipt', False)
    human_dura_allograft_tissue = extracted_data.get('human_dura_allograft_tissue', False)
    
    if non_synthetic_dura_mater:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Receipt of non-synthetic dura-mater'
        }
    
    if epicel_receipt:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Receipt of EpicelTM'
        }
    
    if human_dura_allograft_tissue:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Receipt of human dura allograft tissue'
        }
    
    if xenograft_living_cells:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Xenograft recipient or intimate contact with a recipient – living cells'
        }
    
    if xenograft_non_living_cells:
        return {
            'result': EvaluationResult.ACCEPTABLE,
            'reasoning': 'Xenograft recipient or intimate contact with a recipient – non-living cells'
        }
    
    if human_tissue_transplant_screened:
        return {
            'result': EvaluationResult.ACCEPTABLE,
            'reasoning': 'Receipt of a human tissue transplant is acceptable unless there is evidence suggesting donor received human tissue that was not screened'
        }
    
    if transplant_type:
        return {
            'result': EvaluationResult.MD_DISCRETION,
            'reasoning': 'Transplant history - gather all relevant information: use of steroids, anti-rejection drugs, incidence of infection, blood transfusions, hepatitis test, activity level, date of transplant, overall state of health'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No transplant concerns found'
    }


def evaluate_trauma_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Trauma criteria."""
    extensive_deep_abrasions_lacerations = extracted_data.get('extensive_deep_abrasions_lacerations', False)
    adipose_environmental_contaminants = extracted_data.get('adipose_environmental_contaminants', False)
    tissue_type = extracted_data.get('tissue_type', '')
    
    if extensive_deep_abrasions_lacerations or adipose_environmental_contaminants:
        if tissue_type == 'skin':
            return {
                'result': EvaluationResult.UNACCEPTABLE,
                'reasoning': 'Extensive and/or deep abrasions/lacerations or exposure of adipose to environmental contaminants - unacceptable for skin'
            }
        else:
            return {
                'result': EvaluationResult.MD_DISCRETION,
                'reasoning': 'Extensive and/or deep abrasions/lacerations or exposure of adipose to environmental contaminants - MD discretion for musculoskeletal'
            }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No trauma concerns found'
    }


def evaluate_travel_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Travel criteria."""
    malarial_areas_arrived_us_3_years = extracted_data.get('malarial_areas_arrived_us_3_years', False)
    chagas_areas_arrived_us_3_years = extracted_data.get('chagas_areas_arrived_us_3_years', False)
    tse_areas_arrived_us_3_years = extracted_data.get('tse_areas_arrived_us_3_years', False)
    malarial_areas_6_months_no_prophylaxis = extracted_data.get('malarial_areas_6_months_no_prophylaxis', False)
    uk_3_months_1980_1996 = extracted_data.get('uk_3_months_1980_1996', False)
    blood_transfusion_uk_france_1980_present = extracted_data.get('blood_transfusion_uk_france_1980_present', False)
    europe_5_years_1980_present = extracted_data.get('europe_5_years_1980_present', False)
    
    if malarial_areas_arrived_us_3_years or chagas_areas_arrived_us_3_years or tse_areas_arrived_us_3_years:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Residents of malarial areas who arrived in U.S. within 3 years'
        }
    
    if uk_3_months_1980_1996:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Three or more months cumulatively in United Kingdom from beginning of 1980 through end of 1996'
        }
    
    if blood_transfusion_uk_france_1980_present:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Receipt of transfusion of blood or blood products in the UK or France between 1980 - present'
        }
    
    if europe_5_years_1980_present:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': '5 years or more cumulatively in Europe from 1980 to present'
        }
    
    if malarial_areas_6_months_no_prophylaxis:
        return {
            'result': EvaluationResult.MD_DISCRETION,
            'reasoning': 'Visited any endemic malarial areas in past six months and did not take anti-malarial drugs for prophylaxis'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No travel-related risk factors found'
    }


def evaluate_aatb_new_tb_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate AATB New TB Criteria."""
    tb_disease_history_ever = extracted_data.get('tb_disease_history_ever', False)
    tb_latent_infection_diagnosed_within_2_years = extracted_data.get('tb_latent_infection_diagnosed_within_2_years', False)
    viable_cells_tissue = extracted_data.get('viable_cells_tissue', False)
    age_65_plus = donor_info.get('age', 0) >= 65
    tb_travel_immigration_2_years = extracted_data.get('tb_travel_immigration_2_years', False)
    tb_exposure_2_years = extracted_data.get('tb_exposure_2_years', False)
    tb_latent_2_years_ago = extracted_data.get('tb_latent_2_years_ago', False)
    tb_homelessness_2_years = extracted_data.get('tb_homelessness_2_years', False)
    tb_incarceration_2_years = extracted_data.get('tb_incarceration_2_years', False)
    tb_esrd_transplant = extracted_data.get('tb_esrd_transplant', False)
    exposure_risk_factor = extracted_data.get('exposure_risk_factor', False)
    reactivation_risk_factor = extracted_data.get('reactivation_risk_factor', False)
    
    if tb_disease_history_ever:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Persons with a history (ever) of tuberculosis disease'
        }
    
    if tb_latent_infection_diagnosed_within_2_years:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Persons with a history of (latent) tuberculosis infection initially diagnosed within the past two (2) years'
        }
    
    if viable_cells_tissue:
        if age_65_plus or tb_travel_immigration_2_years or tb_exposure_2_years or tb_latent_2_years_ago or tb_homelessness_2_years or tb_incarceration_2_years or tb_esrd_transplant:
            return {
                'result': EvaluationResult.UNACCEPTABLE,
                'reasoning': 'For tissues intended to ultimately retain viable cells - various risk factors present'
            }
        
        if exposure_risk_factor and reactivation_risk_factor:
            return {
                'result': EvaluationResult.UNACCEPTABLE,
                'reasoning': 'Potential donors with at least one risk factor from each column (exposure and reactivation) are ineligible'
            }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No AATB New TB Criteria risk factors found'
    }


def evaluate_typhus_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate Typhus criteria."""
    significant_active_infection = extracted_data.get('significant_active_infection', False)
    typhus_active = extracted_data.get('typhus_active', False)
    
    if significant_active_infection or typhus_active:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Evidence of significant active infections'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No active typhus infection found'
    }


def evaluate_us_military_criteria(
    extracted_data: Dict[str, Any],
    lab_results: List[LaboratoryResult],
    donor_info: Dict[str, Any],
    criterion_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate US Military criteria."""
    military_northern_europe_6_months_1980_1990 = extracted_data.get('military_northern_europe_6_months_1980_1990', False)
    military_europe_6_months_1980_1996 = extracted_data.get('military_europe_6_months_1980_1996', False)
    uk_3_months_1980_1996 = extracted_data.get('uk_3_months_1980_1996', False)
    
    if military_northern_europe_6_months_1980_1990 or military_europe_6_months_1980_1996:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Current or former U.S. military members who resided at US military bases in Northern Europe for 6 months or more from 1980 through 1990, or elsewhere in Europe for 6 months or more from 1980 through 1996'
        }
    
    if uk_3_months_1980_1996:
        return {
            'result': EvaluationResult.UNACCEPTABLE,
            'reasoning': 'Donors who spent three or more months cumulatively in the United Kingdom from the beginning of 1980 through end of 1996'
        }
    
    return {
        'result': EvaluationResult.ACCEPTABLE,
        'reasoning': 'No US Military risk factors found'
    }

