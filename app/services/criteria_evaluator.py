"""
Criteria evaluation engine.
Evaluates extracted data against acceptance criteria rules and generates eligibility decisions.
"""
import json
import os
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.criteria_evaluation import CriteriaEvaluation, EvaluationResult, TissueType as CriteriaTissueType
from app.models.donor_eligibility import DonorEligibility, EligibilityStatus, TissueType
from app.models.laboratory_result import LaboratoryResult, TestType
from app.models.donor import Donor
from app.services.criteria_evaluator.rules import (
    evaluate_age_criteria, evaluate_cancer_criteria, evaluate_hiv_criteria,
    evaluate_hiv_aids_criteria, evaluate_hepatitis_criteria, evaluate_sepsis_criteria,
    evaluate_septicemia_criteria, evaluate_tuberculosis_criteria,
    evaluate_high_risk_behavior_criteria, evaluate_iv_drug_use_criteria,
    evaluate_incarceration_criteria, evaluate_syphilis_criteria, evaluate_htlv_criteria,
    evaluate_west_nile_virus_criteria, evaluate_infection_criteria,
    evaluate_cooling_criteria, evaluate_autopsy_criteria, evaluate_toxicology_criteria,
    evaluate_autoimmune_criteria, evaluate_dementia_criteria,
    evaluate_bleeding_disorder_criteria, evaluate_bone_disease_criteria,
    evaluate_bowel_perforation_criteria, evaluate_chagas_disease_criteria,
    evaluate_chicken_pox_criteria, evaluate_contamination_criteria,
    evaluate_covid_criteria, evaluate_creutzfeldt_jakob_disease_criteria,
    evaluate_delirium_criteria, evaluate_diabetes_criteria, evaluate_drowning_criteria,
    evaluate_encephalitis_criteria, evaluate_fracture_criteria, evaluate_gout_criteria,
    evaluate_growth_hormone_criteria, evaluate_guillain_barre_criteria,
    evaluate_hemodialysis_criteria, evaluate_herpes_ii_criteria,
    evaluate_high_risk_non_iv_drug_use_criteria, evaluate_hiv_group_o_criteria,
    evaluate_hiv_hepatitis_criteria, evaluate_hiv_hepatitis_communicable_disease_criteria,
    evaluate_immunizations_criteria, evaluate_jaundice_criteria, evaluate_leprosy_criteria,
    evaluate_liver_disease_criteria, evaluate_long_term_illness_criteria,
    evaluate_long_term_steroid_therapy_criteria, evaluate_long_term_infection_criteria,
    evaluate_lou_gehrig_disease_criteria, evaluate_malaria_criteria,
    evaluate_measles_criteria, evaluate_meningitis_criteria, evaluate_multiple_sclerosis_criteria,
    evaluate_mumps_criteria, evaluate_muscular_dystrophy_criteria, evaluate_needle_stick_criteria,
    evaluate_non_tumor_related_shunts_criteria, evaluate_osteomyelitis_criteria,
    evaluate_perianal_condyloma_criteria, evaluate_genitalia_piercing_criteria,
    evaluate_piercing_acupuncture_criteria, evaluate_prosthetic_implants_criteria,
    evaluate_rabies_criteria, evaluate_refused_blood_donor_criteria,
    evaluate_reyes_syndrome_criteria, evaluate_rheumatic_fever_criteria,
    evaluate_rubella_criteria, evaluate_std_sti_criteria, evaluate_smallpox_criteria,
    evaluate_sirs_criteria, evaluate_tattoo_criteria, evaluate_transplant_criteria,
    evaluate_trauma_criteria, evaluate_travel_criteria, evaluate_aatb_new_tb_criteria,
    evaluate_typhus_criteria, evaluate_us_military_criteria
)

logger = logging.getLogger(__name__)

# Get config directory
_CONFIG_DIR = os.path.join(os.path.dirname(__file__), 'processing', 'config')


def load_acceptance_criteria_config() -> Dict[str, Any]:
    """Load acceptance criteria configuration."""
    criteria_path = os.path.join(_CONFIG_DIR, 'acceptance_criteria.json')
    with open(criteria_path, 'r') as f:
        return json.load(f)


class CriteriaEvaluator:
    """Service for evaluating criteria against extracted data."""
    
    def __init__(self):
        self.criteria_config = load_acceptance_criteria_config()
    
    async def evaluate_donor_criteria(self, donor_id: int, db: Session) -> bool:
        """
        Evaluate all criteria for a donor after all documents are processed.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Get donor info
            donor = db.query(Donor).filter(Donor.id == donor_id).first()
            if not donor:
                logger.error(f"Donor {donor_id} not found")
                return False
            
            # Get all extracted criteria data for this donor
            criteria_evaluations = db.query(CriteriaEvaluation).filter(
                CriteriaEvaluation.donor_id == donor_id
            ).all()
            
            if not criteria_evaluations:
                logger.warning(f"No criteria evaluations found for donor {donor_id}")
                return False
            
            # Get lab test results for this donor
            from app.models.document import Document
            documents = db.query(Document).filter(Document.donor_id == donor_id).all()
            document_ids = [doc.id for doc in documents]
            
            lab_results = db.query(LaboratoryResult).filter(
                LaboratoryResult.document_id.in_(document_ids)
            ).all()
            
            # Group criteria evaluations by criterion name
            criteria_by_name = {}
            for eval_obj in criteria_evaluations:
                criterion_name = eval_obj.criterion_name
                if criterion_name not in criteria_by_name:
                    criteria_by_name[criterion_name] = []
                criteria_by_name[criterion_name].append(eval_obj)
            
            # Evaluate each criterion
            for criterion_name, eval_objects in criteria_by_name.items():
                if criterion_name not in self.criteria_config:
                    logger.warning(f"Criterion {criterion_name} not found in config, skipping")
                    continue
                
                criterion_info = self.criteria_config[criterion_name]
                
                # Merge extracted data from all documents for this criterion
                merged_extracted_data = {}
                for eval_obj in eval_objects:
                    if eval_obj.extracted_data:
                        # Merge extracted data (simple merge, later values override)
                        merged_extracted_data.update(eval_obj.extracted_data)
                
                # Evaluate the criterion
                evaluation_result = self.evaluate_single_criterion(
                    criterion_name=criterion_name,
                    criterion_info=criterion_info,
                    extracted_data=merged_extracted_data,
                    lab_results=lab_results,
                    donor_info={'age': donor.age, 'gender': donor.gender}
                )
                
                # Update evaluation results in database
                for eval_obj in eval_objects:
                    eval_obj.evaluation_result = evaluation_result['result']
                    eval_obj.evaluation_reasoning = evaluation_result.get('reasoning', '')
                    eval_obj.extracted_data = merged_extracted_data  # Update with merged data
            
            db.commit()
            
            # Generate final eligibility decisions
            await self.generate_eligibility_decision(donor_id, db)
            
            logger.info(f"Successfully evaluated criteria for donor {donor_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error evaluating criteria for donor {donor_id}: {e}", exc_info=True)
            db.rollback()
            return False
    
    def evaluate_single_criterion(
        self,
        criterion_name: str,
        criterion_info: Dict[str, Any],
        extracted_data: Dict[str, Any],
        lab_results: List[LaboratoryResult],
        donor_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Evaluate a single criterion against extracted data and lab results.
        
        Returns:
            Dictionary with 'result' (EvaluationResult) and 'reasoning' (str)
        """
        try:
            evaluation_logic = criterion_info.get('evaluation_logic', '')
            
            # Get evaluation function from rules module
            eval_function_name = f"evaluate_{evaluation_logic}"
            eval_function_map = {
                'age_criteria': evaluate_age_criteria,
                'cancer_criteria': evaluate_cancer_criteria,
                'hiv_criteria': evaluate_hiv_criteria,
                'hiv_aids_criteria': evaluate_hiv_aids_criteria,
                'hepatitis_criteria': evaluate_hepatitis_criteria,
                'sepsis_criteria': evaluate_sepsis_criteria,
                'septicemia_criteria': evaluate_septicemia_criteria,
                'tuberculosis_criteria': evaluate_tuberculosis_criteria,
                'high_risk_behavior_criteria': evaluate_high_risk_behavior_criteria,
                'iv_drug_use_criteria': evaluate_iv_drug_use_criteria,
                'incarceration_criteria': evaluate_incarceration_criteria,
                'syphilis_criteria': evaluate_syphilis_criteria,
                'htlv_criteria': evaluate_htlv_criteria,
                'west_nile_virus_criteria': evaluate_west_nile_virus_criteria,
                'infection_criteria': evaluate_infection_criteria,
                'cooling_criteria': evaluate_cooling_criteria,
                'autopsy_criteria': evaluate_autopsy_criteria,
                'toxicology_criteria': evaluate_toxicology_criteria,
                'autoimmune_criteria': evaluate_autoimmune_criteria,
                'dementia_criteria': evaluate_dementia_criteria,
                'bleeding_disorder_criteria': evaluate_bleeding_disorder_criteria,
                'bone_disease_criteria': evaluate_bone_disease_criteria,
                'bowel_perforation_criteria': evaluate_bowel_perforation_criteria,
                'chagas_disease_criteria': evaluate_chagas_disease_criteria,
                'chicken_pox_criteria': evaluate_chicken_pox_criteria,
                'contamination_criteria': evaluate_contamination_criteria,
                'covid_criteria': evaluate_covid_criteria,
                'creutzfeldt_jakob_disease_criteria': evaluate_creutzfeldt_jakob_disease_criteria,
                'delirium_criteria': evaluate_delirium_criteria,
                'diabetes_criteria': evaluate_diabetes_criteria,
                'drowning_criteria': evaluate_drowning_criteria,
                'encephalitis_criteria': evaluate_encephalitis_criteria,
                'fracture_criteria': evaluate_fracture_criteria,
                'gout_criteria': evaluate_gout_criteria,
                'growth_hormone_criteria': evaluate_growth_hormone_criteria,
                'guillain_barre_criteria': evaluate_guillain_barre_criteria,
                'hemodialysis_criteria': evaluate_hemodialysis_criteria,
                'herpes_ii_criteria': evaluate_herpes_ii_criteria,
                'high_risk_non_iv_drug_use_criteria': evaluate_high_risk_non_iv_drug_use_criteria,
                'hiv_group_o_criteria': evaluate_hiv_group_o_criteria,
                'hiv_hepatitis_criteria': evaluate_hiv_hepatitis_criteria,
                'hiv_hepatitis_communicable_disease_criteria': evaluate_hiv_hepatitis_communicable_disease_criteria,
                'immunizations_criteria': evaluate_immunizations_criteria,
                'jaundice_criteria': evaluate_jaundice_criteria,
                'leprosy_criteria': evaluate_leprosy_criteria,
                'liver_disease_criteria': evaluate_liver_disease_criteria,
                'long_term_illness_criteria': evaluate_long_term_illness_criteria,
                'long_term_steroid_therapy_criteria': evaluate_long_term_steroid_therapy_criteria,
                'long_term_infection_criteria': evaluate_long_term_infection_criteria,
                'lou_gehrig_disease_criteria': evaluate_lou_gehrig_disease_criteria,
                'malaria_criteria': evaluate_malaria_criteria,
                'measles_criteria': evaluate_measles_criteria,
                'meningitis_criteria': evaluate_meningitis_criteria,
                'multiple_sclerosis_criteria': evaluate_multiple_sclerosis_criteria,
                'mumps_criteria': evaluate_mumps_criteria,
                'muscular_dystrophy_criteria': evaluate_muscular_dystrophy_criteria,
                'needle_stick_criteria': evaluate_needle_stick_criteria,
                'non_tumor_related_shunts_criteria': evaluate_non_tumor_related_shunts_criteria,
                'osteomyelitis_criteria': evaluate_osteomyelitis_criteria,
                'perianal_condyloma_criteria': evaluate_perianal_condyloma_criteria,
                'genitalia_piercing_criteria': evaluate_genitalia_piercing_criteria,
                'piercing_acupuncture_criteria': evaluate_piercing_acupuncture_criteria,
                'prosthetic_implants_criteria': evaluate_prosthetic_implants_criteria,
                'rabies_criteria': evaluate_rabies_criteria,
                'refused_blood_donor_criteria': evaluate_refused_blood_donor_criteria,
                'reyes_syndrome_criteria': evaluate_reyes_syndrome_criteria,
                'rheumatic_fever_criteria': evaluate_rheumatic_fever_criteria,
                'rubella_criteria': evaluate_rubella_criteria,
                'std_sti_criteria': evaluate_std_sti_criteria,
                'smallpox_criteria': evaluate_smallpox_criteria,
                'sirs_criteria': evaluate_sirs_criteria,
                'tattoo_criteria': evaluate_tattoo_criteria,
                'transplant_criteria': evaluate_transplant_criteria,
                'trauma_criteria': evaluate_trauma_criteria,
                'travel_criteria': evaluate_travel_criteria,
                'aatb_new_tb_criteria': evaluate_aatb_new_tb_criteria,
                'typhus_criteria': evaluate_typhus_criteria,
                'us_military_criteria': evaluate_us_military_criteria
            }
            
            if evaluation_logic in eval_function_map:
                eval_function = eval_function_map[evaluation_logic]
                return eval_function(extracted_data, lab_results, donor_info, criterion_info)
            else:
                logger.warning(f"Evaluation function for {evaluation_logic} not found, using default")
                return {
                    'result': EvaluationResult.MD_DISCRETION,
                    'reasoning': f"Evaluation logic {evaluation_logic} not implemented"
                }
                
        except Exception as e:
            logger.error(f"Error evaluating criterion {criterion_name}: {e}", exc_info=True)
            return {
                'result': EvaluationResult.MD_DISCRETION,
                'reasoning': f"Error during evaluation: {str(e)}"
            }
    
    async def generate_eligibility_decision(self, donor_id: int, db: Session) -> bool:
        """
        Generate final eligibility decision per tissue type based on all criteria evaluations.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Get all evaluated criteria for this donor
            criteria_evaluations = db.query(CriteriaEvaluation).filter(
                CriteriaEvaluation.donor_id == donor_id
            ).all()
            
            # Group by tissue type
            evaluations_by_tissue = {
                TissueType.MUSCULOSKELETAL: [],
                TissueType.SKIN: []
            }
            
            for eval_obj in criteria_evaluations:
                tissue_type = eval_obj.tissue_type
                if tissue_type == CriteriaTissueType.MUSCULOSKELETAL:
                    evaluations_by_tissue[TissueType.MUSCULOSKELETAL].append(eval_obj)
                elif tissue_type == CriteriaTissueType.SKIN:
                    evaluations_by_tissue[TissueType.SKIN].append(eval_obj)
                elif tissue_type == CriteriaTissueType.BOTH:
                    evaluations_by_tissue[TissueType.MUSCULOSKELETAL].append(eval_obj)
                    evaluations_by_tissue[TissueType.SKIN].append(eval_obj)
            
            # Generate eligibility for each tissue type
            for tissue_type, evaluations in evaluations_by_tissue.items():
                if not evaluations:
                    continue
                
                # Find blocking criteria (unacceptable)
                blocking_criteria = []
                md_discretion_criteria = []
                
                for eval_obj in evaluations:
                    if eval_obj.evaluation_result == EvaluationResult.UNACCEPTABLE:
                        blocking_criteria.append({
                            'criterion_name': eval_obj.criterion_name,
                            'reasoning': eval_obj.evaluation_reasoning
                        })
                    elif eval_obj.evaluation_result == EvaluationResult.MD_DISCRETION:
                        md_discretion_criteria.append({
                            'criterion_name': eval_obj.criterion_name,
                            'reasoning': eval_obj.evaluation_reasoning
                        })
                
                # Determine overall status
                if blocking_criteria:
                    overall_status = EligibilityStatus.INELIGIBLE
                elif md_discretion_criteria:
                    overall_status = EligibilityStatus.REQUIRES_REVIEW
                else:
                    overall_status = EligibilityStatus.ELIGIBLE
                
                # Check if eligibility record exists
                existing_eligibility = db.query(DonorEligibility).filter(
                    DonorEligibility.donor_id == donor_id,
                    DonorEligibility.tissue_type == tissue_type
                ).first()
                
                if existing_eligibility:
                    # Update existing
                    existing_eligibility.overall_status = overall_status
                    existing_eligibility.blocking_criteria = blocking_criteria
                    existing_eligibility.md_discretion_criteria = md_discretion_criteria
                    existing_eligibility.evaluated_at = datetime.now()
                else:
                    # Create new
                    eligibility = DonorEligibility(
                        donor_id=donor_id,
                        tissue_type=tissue_type,
                        overall_status=overall_status,
                        blocking_criteria=blocking_criteria,
                        md_discretion_criteria=md_discretion_criteria
                    )
                    db.add(eligibility)
            
            db.commit()
            logger.info(f"Generated eligibility decisions for donor {donor_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error generating eligibility decision for donor {donor_id}: {e}", exc_info=True)
            db.rollback()
            return False


# Global instance
criteria_evaluator = CriteriaEvaluator()

