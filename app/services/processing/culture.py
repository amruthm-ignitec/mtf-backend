import json
import ast
import time
import logging
from .utils.json_parser import safe_parse_llm_json, LLMResponseParseError
from .utils.llm_wrapper import call_llm_with_retry, LLMCallError

logger = logging.getLogger(__name__)


def get_llm_response(llm, role, primary_instruction, donor_info, reminder_instruction):
    '''
    Provides assessment with OpenAI API call using retry logic and error handling.
    '''
    prompt = """{role}
    Instruction: {primary_instruction}

    Do not extract: Culture results for blood, sputum, urine, stool, bronch

    Relevant donor information: {donor_info}

    Here are some output examples for your reference in the desired JSON format:

    Example-1
    AI Response: {{"Left Hemipelvis Pre-Processing Culture": ["Listeria monocytogenes", "Aspergillus fumigatus"], "Right Femur Recovery Culture": [], "Right Semitendinosus Recovery Culture": ["Burkholderia mallei"]}}

    Example-2
    AI Response: {{"Cardiac Processing Representative Sample": ["Cladosporium", "Mold", "Salmonella"], "Right Peroneus Longus Recovery Culture": []}}

    {reminder_instruction} DO NOT return any other character or word (like ``` or 'json') but the required result JSON.
    AI Response: """.format(role=role, primary_instruction=primary_instruction, donor_info=donor_info, reminder_instruction=reminder_instruction)
    
    try:
        response = call_llm_with_retry(
            llm=llm,
            prompt=prompt,
            max_retries=3,
            base_delay=1.0,
            timeout=60,
            context="culture extraction"
        )
        return response
    except LLMCallError as e:
        logger.error(f"LLM call failed for culture extraction: {e}")
        raise
    

def get_ms_categories(dc_info, subtissue_map, MS_MO_category_map):
    '''
    Given LLM extraction from DCs, provides subtissue-MS (MS subtissue or not) and microorganism-category mapping. These are to be kept and appended in excel files and exported as JSON.
    Output format:
    {
        "subtissue-1": {'Type': 'MS', 'MO_CAT': [('MO1', 'C3'), ('MO2', 'C1'), ('MO7", 'C2')]},

    }
    '''

    output_dc_info = {}

    for subtissue, mo_list in dc_info.items():
        if any( x in subtissue for x in ["tib/fib", "fib/tib", "radius/ulna", "ulna/radius"]):
            subtissue = subtissue.replace("-", "").replace("  ", " ").strip()
        else:
            subtissue = subtissue.replace("-", "").replace("/", "").replace("  ", " ").strip()

        if subtissue in subtissue_map["MS"]:
            cat_list = []

            for mo in mo_list:
                mo = mo.lower().strip()
                if mo in MS_MO_category_map["C3"]:
                    cat_list.append("C3")
                elif mo in MS_MO_category_map["C2"]:
                    cat_list.append("C2")
                elif mo in MS_MO_category_map["C1"]:
                    cat_list.append("C1")
                elif mo in MS_MO_category_map["C3A"]:
                    cat_list.append("C3A")
                else:
                    cat_list.append("unknown")

            output_dc_info[subtissue] = {'Type': 'MS', 'MO_CAT': list(zip(mo_list, cat_list))}

        elif subtissue in subtissue_map.get("CARDIAC", []):
            cat_list = ["NA"] * len(mo_list)
            output_dc_info[subtissue] = {'Type': 'CARDIAC', 'MO_CAT': list(zip(mo_list, cat_list))}
        
        elif subtissue in subtissue_map.get("OCULAR", []):
            cat_list = ["NA"] * len(mo_list)
            output_dc_info[subtissue] = {'Type': 'OCULAR', 'MO_CAT': list(zip(mo_list, cat_list))}
        
        elif subtissue in subtissue_map.get("SKIN", []):
            cat_list = ["NA"] * len(mo_list)
            output_dc_info[subtissue] = {'Type': 'SKIN', 'MO_CAT': list(zip(mo_list, cat_list))}
        
        elif subtissue in subtissue_map.get("COMPOSITE", []):
            cat_list = ["NA"] * len(mo_list)
            output_dc_info[subtissue] = {'Type': 'COMPOSITE', 'MO_CAT': list(zip(mo_list, cat_list))}

        else:
            cat_list = ["NA"] * len(mo_list)
            output_dc_info[subtissue] = {'Type': 'UNKNOWN', 'MO_CAT': list(zip(mo_list, cat_list))}

    return output_dc_info


def remove_species(dc_info):
    output_dc_info = {}

    for subtissue, mo_list in dc_info.items():
        new_mo_list = [mo.replace("species", "").strip() for mo in mo_list]
        output_dc_info[subtissue] = new_mo_list

    return output_dc_info


def reranking_culture(llm, retrieved_text_chunk):

    prompt = """You are provided with donor information that may contain results for Culture tests for various tissues (like Recovery cultures, pre-processing cultures, postprocessing vivigen, cardiac processing filters, etc.) and microorganisms that may be present within these tissues. Your task is to carefully read the donor information and check whether the information is relevant to such Culture tests.

    - If there are culture test results for subtissues like recovery culture, preprocessing culture, vivigen preprocessing, postprocessing vivigen, postprocessing skin, cardiac disinfect filter, cardiac processing represntative samples, etc say "RELEVANT".
    - DO NOT OVERSEE test results for cardiac processing filters, postprocessing vivigen, aortoiliac processing filter, aortoiliac processing representative sample, cardiac disinfect filter, cardiac endpoint representative sample, cardiac representative sample, cardiac represntative filter, postprocessing skin, etc. These are also culture tests. If results for such sub-tissues are present, say "RELEVANT".
    - Say "RELEVANT" only if culture test RESULTS for tissues are explicity present.
    - If there is no culture test results, say "NOT RELEVANT".
    - If there are instances of tests like blood, sputum, stool, urine, bronch, pad floor absorbent, bone, etc, say "NOT RELEVANT". 
    - Just give output as "RELEVANT" or "NOT RELEVANT".

    Example-1
    Donor information: blood culture\\ bacteria\\ urine culture\\ negative\\ bronch\\ negative\\ sputum\\ bacteria\\ heart\\ no growth observed 
    AI response: NOT RELEVANT

    Example-2
    Donor information: left femur recovery culture\\ result negative\\cardiac disinfect filter\\Bacteroides species\\ postprocessing vivigen\\ result negative\\ right femur preprocessing recovery culture\\ result negative\\ left tib fib recovery culture\\ result negative\\ right achilles tendon recovery culture\\ mold 
    AI response: RELEVANT

    Example-3
    Donor information: Indicate Tissue Submitted for Processing to be Performed by LifeNet Health\\JAMS Recovery Cultures Skin Prep* Date. Skin was prepped to initiate any tissue recovery.Skin Recovery Cultures. MS and Skin Recovery cultures submitted to LNH QC Lab are received and processed.
    AI response: NOT RELEVANT

    Example-4
    Donor information: postprocessing skin rs13\\ bacteria\\ cardiac disinfect filter\\ result negative\\ cardiac processing representative sample\\ clostridum perfringens
    AI response: RELEVANT

    Donor information: {retrieved_text_chunk}
    AI response: """.format(retrieved_text_chunk=retrieved_text_chunk)
    response = llm.invoke(prompt)

    return response


def get_collated_donor_info(info_list):
    page_content_list = [val[0] for val in info_list]
    collated_donor_info = '\n'.join(page_content_list)
    return collated_donor_info


def get_culture_results(llm, vectordb, disease_context, role, basic_instruction, reminder_instructions, subtissue_map, MS_MO_category_map):
    test_name = "Culture test"
    # Retrieve docs similar to each of the disease/condition descriptions and save as json
    top_k = 10  
    retriever_obj = vectordb.as_retriever(search_type='similarity', search_kwargs={'k': top_k})
    retrieved_docs_dict={}
    disease_level_res = {}

    retrieved_docs = retriever_obj.invoke(disease_context[test_name])
    retrieved_text_chunks = [(doc.page_content, f"page: {doc.metadata['page']+1}") for doc in retrieved_docs]
    retrieved_text_chunks = sorted(retrieved_text_chunks, key=lambda x: int(x[1].split(":")[1]))
    retrieved_docs_dict[test_name] = retrieved_text_chunks

    output = []
    extracted_results=[]
    relevant_chunks=[]
    citations =[]
    keyword_pages = []
    for chunk, page_info in retrieved_text_chunks:
        result = reranking_culture(llm, chunk)
        extracted_results.append((page_info, result.content))
        if result.content=='RELEVANT':
            relevant_chunks.append((chunk, page_info))

    keywords = ([keyword for sublist in subtissue_map.values() for keyword in sublist] +
        [keyword for sublist in MS_MO_category_map.values() for keyword in sublist])
 
    if relevant_chunks:
        citations = sorted([int(item[1].split(":")[1]) for item in relevant_chunks if "page:" in item[1]])
 
    elif not relevant_chunks:
   

        for chunk, page_info in retrieved_text_chunks:
            if any(keyword.lower() in chunk.lower() for keyword in keywords):
                keyword_pages.append((chunk, page_info))
                citations = sorted([int(item[1].split(":")[1]) for item in keyword_pages if "page:" in item[1]])
    else:
        citations = sorted([int(item[1].split(":")[1]) for item in retrieved_text_chunks if "page:" in item[1]])
        

    collated_donor_info = get_collated_donor_info(retrieved_docs_dict[test_name])
    result = get_llm_response(llm, role[test_name], basic_instruction[test_name], collated_donor_info, reminder_instructions[test_name])
    
    try:
        # Use robust JSON parsing
        final_result = safe_parse_llm_json(
            result.content,
            context=f"culture extraction for {test_name}"
        )
        
        # Validate structure (should be dict with tissue locations as keys)
        if not isinstance(final_result, dict):
            raise LLMResponseParseError(
                f"Expected dictionary but got {type(final_result)}. "
                f"Context: culture extraction"
            )
        
        final_result = remove_species(final_result)
        final_mapped_result = get_ms_categories(final_result, subtissue_map, MS_MO_category_map)
        
    except LLMResponseParseError as e:
        logger.error(f"Failed to parse culture extraction result: {e}")
        # Store error in structured format instead of string
        final_mapped_result = {
            "error": True,
            "error_type": "parse_error",
            "error_message": str(e),
            "raw_response_preview": result.content[:500] if hasattr(result, 'content') else str(result)[:500]
        }
    except Exception as e:
        logger.error(f"Unexpected error in culture extraction: {e}", exc_info=True)
        final_mapped_result = {
            "error": True,
            "error_type": "unexpected_error",
            "error_message": str(e),
            "raw_response_preview": result.content[:500] if hasattr(result, 'content') else str(result)[:500]
        }
 
    # Convert final_mapped_result to the format expected by store_culture_results
    # Format: {"result": [{tissue_location: [microorganisms]}, ...], "citations": [{"page": page_num}, ...]}
    result_list = []
    
    # Convert citations from list of integers to list of dicts (consistent with serology format)
    formatted_citations = []
    if citations:
        seen_pages = set()
        for page_num in citations:
            if isinstance(page_num, int) and page_num not in seen_pages:
                seen_pages.add(page_num)
                formatted_citations.append({"page": page_num})
    
    # Skip if there's an error
    if not isinstance(final_mapped_result, dict) or final_mapped_result.get("error"):
        # Return empty structure with citations if error
        culture_data = {
            "result": [],
            "citations": formatted_citations
        }
        logger.warning(f"Culture extraction error: {final_mapped_result.get('error_message', 'Unknown error')}")
    else:
        # Convert dict format {tissue_location: [microorganisms]} to list format [{tissue_location: [microorganisms]}, ...]
        for tissue_location, microorganisms in final_mapped_result.items():
            # Skip Citations key if present
            if tissue_location != 'Citations' and tissue_location != 'citations':
                result_list.append({tissue_location: microorganisms})
        
        culture_data = {
            "result": result_list,
            "citations": formatted_citations
        }
    
    logger.info(f"Extracted {len(result_list)} culture tissue locations with microorganisms from {len(formatted_citations)} pages")
    
    return result.content, culture_data
  