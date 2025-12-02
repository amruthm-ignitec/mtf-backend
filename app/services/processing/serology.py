import json
import ast
import time
import logging

from .culture import get_culture_results
from .utils.json_parser import safe_parse_llm_json, LLMResponseParseError
from .utils.llm_wrapper import call_llm_with_retry, LLMCallError

logger = logging.getLogger(__name__)

def get_llm_response_sero(llm, role, primary_instruction, donor_info, reminder_instructions):
    '''
    Provides assessment with OpenAI API call using retry logic and error handling.
    '''
    prompt = """{role}
        Instruction: {primary_instruction}

        Key Tips:
        - ABO/Rh or ABO-Rh is one single test also, if ABO and Rh seem to be present in different lines, you should combine and their corresponding results as well.
        - Exclude all non-relevant details such as administrative information and collection procedures.
        - Extract test result information only from the donor information which is a valid serology report from an external laboratory.
        - Avoid generating output for test if its result is incomprehensible or meaningless.
        - Do not generate output if the test name does not seem to be specific disease test names.
        - Do not alter the test names and results provided in the donor information. Maintain the original test names and results as they appear in the donor information.
        - Provide the output only when both the test name and its corresponding result are present together in the given donor information.


        Relevant donor information: 
        {donor_info}

        Here are some output examples for your reference in the desired JSON format:

        Example-1
        AI Response: {{'sars-cov-2 panther': 'Negative', 'Hepatitis B Surface Antigen (HBsAg)': 'Non Reactive','Hepatitis B Surface Antigen (HBsAg)': 'Non Reactive', 'Hepatitis B - NAT': 'Positive', 'ABO/Rh': 'A Positive'}}

        Example-2
        AI Response: {{'Syphilis': 'Cancelled', 'HTLV I/II Antibody (anti-HTLV I/II)': 'Positive', 'CMV Antibody': 'Equivocal', 'ABO/Rh': 'O Positive'}}

        {reminder_instructions} DO NOT return any other character or word (like ``` or 'json') but the required result JSON.
        AI Response: """.format(role=role, primary_instruction=primary_instruction, donor_info=donor_info, reminder_instructions=reminder_instructions)
    
    try:
        response = call_llm_with_retry(
            llm=llm,
            prompt=prompt,
            max_retries=3,
            base_delay=1.0,
            timeout=60,
            context="serology extraction"
        )
        return response
    except LLMCallError as e:
        logger.error(f"LLM call failed for serology extraction: {e}")
        raise


def reranking_serology(llm, retrieved_text_chunks):
    """
    Rerank serology chunks for relevance using LLM with retry logic.
    """
    prompt = """You are provided with donor information that contain information about disease lab tests and its corresponding results from a donor chart. Your task is to carefully read the donor information and check whether the information is relevant to disease lab serology tests (e.g., SARS-CoV-2 Panther, GEL BLOOD TYPE B Rh, ABO/Rh, CMV Antibody, HIV 1&2/HCV/HBV NAT, Hepatitis B Core Total Ab,  etc.,) and its results (e.g., Positive, Negative, Non-Reactive, Reactive, Equivocal, Complete, O Positive etc.) related or not.

        If there are irrelevant donor information, say "NOT RELEVANT" and If there are relevant donor information say "RELEVANT".

        IMPORTANT: Be lenient in determining relevance. If the chunk contains ANY mention of serology tests (HIV, HBV, HCV, CMV, EBV, Syphilis, ABO/Rh, etc.) even if the result is on a nearby line or in the same table, mark it as "RELEVANT". The extraction step will handle finding the exact test-result pairs.

        For the provided donor information, check if it contains serology test information. If test names are present (even without immediately visible results in the same chunk), say "RELEVANT" as results may be in adjacent rows/columns. Only say "NOT RELEVANT" if the chunk clearly contains NO serology test information at all (e.g., only recovery culture tests, administrative text, etc.).

        If there are irrelevant information like recovery culture tests with no serology content, say "NOT RELEVANT". 

        Just give output as "RELEVENT" or "NOT RELEVENT".

        Example-1
        Donor Information: <Left Femur Recovery Culture\nResult\nNegative\nLeft Tib/Fib Recovery Culture\nResult\nNegative\nLeft Achilles Tendon Recovery Culture\nResult\nNegative\nLeft Anterior Tibialis Recovery Culture\nResult\nNegative\nLeft Gracilis Recovery Culture\nResult\nNegative\nLeft Hemipelvis Recovery Culture\nCategory 2>
        AI response: NOT RELEVANT

        Example-2
        Donor Information: <Hepatitis B Core Total Ab 01/29/2021 15:52 Non Reactive Non Reactive\nHepatitis B Surface Ag 01/29/2021 15:51 Non Reactive Non Reactive\nHepatitis C Virus Ab 01/29/2021 15:53 Non Reactive Non Reactive\nHIV-1/HIV-2 Plus O 01/29/2021 15:38 Non Reactive Non Reactive\nSARS-CoV-2 Panther 01/29/2021 17:43 Non Reactive Non Reactive>
        AI response: RELEVANT

        Donor Information: {retrieved_text_chunks}
        AI response: """.format(retrieved_text_chunks=retrieved_text_chunks)
    
    try:
        response = call_llm_with_retry(
            llm=llm,
            prompt=prompt,
            max_retries=3,
            base_delay=1.0,
            timeout=30,  # Shorter timeout for reranking
            context="serology reranking"
        )
        return response
    except LLMCallError as e:
        logger.error(f"LLM call failed for serology reranking: {e}")
        raise


def get_relevant_chunks(retrieved_text_chunks, extracted_results):
    relevant_chunks = []

    # Loop through the extracted results and filter out relevant pages
    for page_info, relevance, _ in extracted_results:
        if relevance == "RELEVANT":
            # Find the corresponding chunk with the same page number
            for chunk, chunk_page_info in retrieved_text_chunks:
                if chunk_page_info == page_info:  # Matching the page numbers
                    relevant_chunks.append((chunk, chunk_page_info))
                    break

    return relevant_chunks

def update_test_names(output, test_name_mapping):
    '''Output is a list of tuples:
    [(page number 1, test name 1, test result 1),
    (page number 2, test name 2, test result 2),
    ...
    ]
    '''

    test_name_mapping = {key.lower(): value for key, value in test_name_mapping.items()}

    # Replace test names in the final output using the mapping
    updated_output = []
    for page_info, test_name, test_value in output:
        # Convert test name to lowercase for case-insensitive matching
        updated_test_name = test_name_mapping.get(test_name.lower(), test_name)
        # Append updated page info, test name, and test value
        updated_output.append((page_info, updated_test_name, test_value))
    
    return updated_output


# Function to convert the updated output to a list of tuples
def convert_to_tuples(updated_output):
    converted_list = []
    for page_info, results in updated_output:
        for test_name, result_value in results.items():
            converted_list.append((page_info, test_name, result_value))
    return converted_list


def standardize_and_deduplicate_results(converted_list):
    # Standardize test results
    results_mapping = {

    "non reactive": "Non Reactive",
    "nonreactive": "Non Reactive",
    "non-reactive": "Non Reactive",
    "negative": "Non Reactive",
    "neg": "Non Reactive",
    "no reaction": "Non Reactive",
    "not detected": "Non Reactive",
    "not reactive": "Non Reactive",
    "negative (not detected)": "Non Reactive",

    "reactive": "Reactive",
    "detected": "Reactive",
    "reactive (detected)": "Reactive",

    "a negative": "A Negative",
    "a positive": "A Positive",
    "a positive ( + )": "A Positive",
    "b rh positive": "B Rh Positive",
    "o pos": "O Positive",
    "o positive": "O Positive",
    "a pos": "A Positive",
    "positive": "Positive",

    "not done": "Not Done",
    "complete": "Complete",
    "cancelled": "Cancelled"
}
    standardized_results = [
        (page, test_name, results_mapping.get(result.lower().strip(), result))
        for page, test_name, result in converted_list
    ]

    # Remove duplicates based on test name and standardized result only
    unique_results = []
    seen = set()

    for page, test_name, result in standardized_results:
        # Use only test name and standardized result for uniqueness check
        key = (test_name, result)
        if key not in seen:
            unique_results.append((test_name, result, page))  # Retain page if needed
            seen.add(key)
    
    return unique_results


def get_serology_results(llm, vectordb, disease_context, role, basic_instruction, reminder_instructions, serology_dictionary):
    test_name="Serology test"
    # Retrieve docs similar to each of the disease/condition descriptions and save as json
    # Increased top_k to capture more chunks from large serology reports
    top_k = 15  # Increased from 8 to capture more serology test data
    retriever_obj = vectordb.as_retriever(search_type='similarity', search_kwargs={'k': top_k})
    retrieved_docs_dict={}
    disease_level_res = {}

    retrieved_docs = retriever_obj.invoke(disease_context[test_name])
    retrieved_text_chunks = [(doc.page_content, f"page: {doc.metadata['page']+1}") for doc in retrieved_docs]
    retrieved_docs_dict[test_name] = retrieved_text_chunks
    
    logger.info(f"Retrieved {len(retrieved_text_chunks)} text chunks for serology extraction")

    extracted_results = []
    relevant_chunks = []
    for chunk, page_info in retrieved_text_chunks:
        start_time = time.time()
        result = reranking_serology(llm, chunk)
        end_time = time.time()
        latency = round(end_time - start_time, 2)
        extracted_results.append((page_info, result.content, latency))
        if result.content=='RELEVANT':
            relevant_chunks.append((chunk, page_info))
    
    logger.info(f"After reranking: {len(relevant_chunks)} relevant chunks out of {len(retrieved_text_chunks)} total chunks")
    
    if not relevant_chunks:
        logger.warning(f"No relevant chunks found for serology extraction. Reranking results: {[r[1] for r in extracted_results]}")
        # Return empty structure but in correct format
        return [], {"result": {}, "citations": []}
    
    # LLM assessment
    
    llm_results=[]
    for chunk, page_info in relevant_chunks:
        # Pass individual chunk to LLM
        try:
            result = get_llm_response_sero(llm, role[test_name], basic_instruction[test_name], chunk, reminder_instructions[test_name])
            try:
                # Use robust JSON parsing
                llm_result = safe_parse_llm_json(
                    result.content,
                    context=f"serology extraction for {test_name} (page {page_info})"
                )
                
                # Validate structure (should be dict with test names as keys)
                if not isinstance(llm_result, dict):
                    raise LLMResponseParseError(
                        f"Expected dictionary but got {type(llm_result)}. "
                        f"Context: serology extraction"
                    )
                
                logger.debug(f"Successfully extracted serology data from page {page_info}: {list(llm_result.keys())}")
                
            except LLMResponseParseError as e:
                logger.error(f"Failed to parse serology extraction result from page {page_info}: {e}")
                # Store error in structured format
                llm_result = {
                    "error": True,
                    "error_type": "parse_error",
                    "error_message": str(e),
                    "raw_response_preview": result.content[:500] if hasattr(result, 'content') else str(result)[:500]
                }
            except Exception as e:
                logger.error(f"Unexpected error in serology extraction from page {page_info}: {e}", exc_info=True)
                llm_result = {
                    "error": True,
                    "error_type": "unexpected_error",
                    "error_message": str(e),
                    "raw_response_preview": result.content[:500] if hasattr(result, 'content') else str(result)[:500]
                }
        except Exception as e:
            logger.error(f"Error calling LLM for serology extraction from page {page_info}: {e}", exc_info=True)
            llm_result = {
                "error": True,
                "error_type": "llm_call_error",
                "error_message": str(e)
            }
        
        llm_results.append((page_info, llm_result))

    sorted_results = sorted(llm_results, key=lambda x: int(x[0].replace('page:', '').strip()))

    converted_list = convert_to_tuples(sorted_results)
    updated_output = update_test_names(converted_list, serology_dictionary)
    unique_results = standardize_and_deduplicate_results(updated_output)

    count_dict = {}
    final_results = []

    for test_name, result, page in unique_results:
        if test_name in count_dict:
            count_dict[test_name] += 1
            new_test_name = f"{test_name} (Duplicate {count_dict[test_name] - 1})"
        else:
            count_dict[test_name] = 1
            new_test_name = test_name
            
        final_results.append((new_test_name, result, page))

    # Convert to proper format for storage: {"result": {test_name: result}, "citations": [...]}
    result_dict = {}
    citations = []
    
    for test_name, result, page in final_results:
        # Extract page number from page string (format: "page: X")
        try:
            page_num = int(page.split(":")[1].strip()) if ":" in page else int(page.replace("page:", "").strip())
        except (ValueError, IndexError):
            page_num = None
        
        # Store result (just the result string, not the tuple)
        result_dict[test_name] = result
        
        # Build citations
        if page_num is not None:
            citations.append({
                "page": page_num
            })
    
    # Deduplicate citations
    unique_citations = []
    seen_pages = set()
    for citation in citations:
        page = citation.get("page")
        if page and page not in seen_pages:
            seen_pages.add(page)
            unique_citations.append(citation)
    
    # Sort citations by page
    unique_citations.sort(key=lambda x: x.get("page", 0))
    
    # Return in format expected by store_serology_results
    serology_data = {
        "result": result_dict,
        "citations": unique_citations
    }
    
    logger.info(f"Extracted {len(result_dict)} serology test results: {list(result_dict.keys())}")
    
    return llm_results, serology_data   


def get_qa_results(llm, vectordb, disease_context, role, basic_instruction, reminder_instructions, serology_dictionary, subtissue_map, MS_MO_category_map): #(path_to_blob, blob_name):

    # CULTURE
    culture_llm_result, culture_disease_level_res = get_culture_results(llm, vectordb, disease_context, role, basic_instruction, reminder_instructions, subtissue_map, MS_MO_category_map)

    # SEROLOGY
    serology_llm_result, serology_disease_level_res = get_serology_results(llm, vectordb, disease_context, role, basic_instruction, reminder_instructions, serology_dictionary)
    
    return culture_disease_level_res, serology_disease_level_res

