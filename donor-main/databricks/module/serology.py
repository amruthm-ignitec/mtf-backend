import json
import ast
import time

from module.culture import get_culture_results

def get_llm_response_sero(llm, role, primary_instruction, donor_info, reminder_instructions):
    '''
    Provides assessment with OpenAI API call
    '''
    try:
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
        response = llm.invoke(prompt)
        # print(response)
        return response
    except Exception as e:
        return e


def reranking_serology(llm, retrieved_text_chunks):
    try:
        prompt = """You are provided with donor information that contain information about disease lab tests and its corresponding results from a donor chart. Your task is to carefully read the donor information and check whether the information is relevant to disease lab serology tests (e.g., SARS-CoV-2 Panther, GEL BLOOD TYPE B Rh, ABO/Rh, CMV Antibody, HIV 1&2/HCV/HBV NAT, Hepatitis B Core Total Ab,  etc.,) and its results (e.g., Positive, Negative, Non-Reactive, Reactive, Equivocal, Complete, O Positive etc.) related or not.

        If there are irrelevant donor information, say "NOT RELEVENT" and If there are relevant donor information say "RELEVANT".

        For the provided donor information, please check if both the test names and its corresponding result is present in it. If the only test names are present and its results are not present, then give output as "NOT RELEVANT". You may find some instances having description of tests in the information but not the results, you should give output as "NOT RELEVANT".

        If there are irrelevant information like recovery culture tests, say "NOT RELEVENT". 

        Just give output as "RELEVENT" or "NOT RELEVENT".

        Example-1
        Donor Information: <Left Femur Recovery Culture\nResult\nNegative\nLeft Tib/Fib Recovery Culture\nResult\nNegative\nLeft Achilles Tendon Recovery Culture\nResult\nNegative\nLeft Anterior Tibialis Recovery Culture\nResult\nNegative\nLeft Gracilis Recovery Culture\nResult\nNegative\nLeft Hemipelvis Recovery Culture\nCategory 2>
        AI response: NOT RELEVANT

        Example-2
        Donor Information: <Hepatitis B Core Total Ab 01/29/2021 15:52 Non Reactive Non Reactive\nHepatitis B Surface Ag 01/29/2021 15:51 Non Reactive Non Reactive\nHepatitis C Virus Ab 01/29/2021 15:53 Non Reactive Non Reactive\nHIV-1/HIV-2 Plus O 01/29/2021 15:38 Non Reactive Non Reactive\nSARS-CoV-2 Panther 01/29/2021 17:43 Non Reactive Non Reactive>
        AI response: RELEVANT

        Donor Information: {retrieved_text_chunks}
        AI response: """.format(retrieved_text_chunks=retrieved_text_chunks)
        response = llm.invoke(prompt)
        # print(response)
        return response
    except Exception as e:
        return e


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
    top_k = 8  
    retriever_obj = vectordb.as_retriever(search_type='similarity', search_kwargs={'k': top_k})
    retrieved_docs_dict={}
    disease_level_res = {}

    retrieved_docs = retriever_obj.invoke(disease_context[test_name])
    retrieved_text_chunks = [(doc.page_content, f"page: {doc.metadata['page']+1}") for doc in retrieved_docs]
    retrieved_docs_dict[test_name] = retrieved_text_chunks

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
    
    # LLM assessment
    
    llm_results=[]
    for chunk, page_info in relevant_chunks:
        # Pass individual chunk to LLM
        result = get_llm_response_sero(llm, role[test_name], basic_instruction[test_name], chunk, reminder_instructions[test_name])
        try:
            llm_result = ast.literal_eval(result.content.lower().replace("```", "").replace("json", "").strip())
        except Exception as e:
            llm_result = f"{e}\n------------\n{result}"
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

    # Convert to json
    test_results_dict = {test_name: (result, int(page.split(":")[1].strip())) for test_name, result, page in final_results}
 
    
    return llm_results, test_results_dict # disease_level_res   


def get_qa_results(llm, vectordb, disease_context, role, basic_instruction, reminder_instructions, serology_dictionary, subtissue_map, MS_MO_category_map): #(path_to_blob, blob_name):

    # CULTURE
    culture_llm_result, culture_disease_level_res = get_culture_results(llm, vectordb, disease_context, role, basic_instruction, reminder_instructions, subtissue_map, MS_MO_category_map)

    # SEROLOGY
    serology_llm_result, serology_disease_level_res = get_serology_results(llm, vectordb, disease_context, role, basic_instruction, reminder_instructions, serology_dictionary)
    
    return culture_disease_level_res, serology_disease_level_res

