import re
import os
from typing import Dict, List, Tuple
from langchain.schema import Document
from langchain_openai import AzureOpenAI
import logging
import pandas as pd
from azure.core.exceptions import HttpResponseError
from openai import BadRequestError
import json
import ast
import time


def search_keywords(documents: List[Document], keyword: str) -> List[Tuple[str, int]]:
    """
    Searches for keywords in the loaded documents and collects unique page content 
    containing the keywords along with the page number.

    Args:
        documents (List[Document]): List of documents to search within.
        keywords (List[str]): List of keywords to search for.

    Returns:
        List[Tuple[str, int]]: 
            A list of tuples containing unique page content and page number where the keywords were found.
    """
    page_info = []          # To store unique page content with page number
    unique_contents = set() # To keep track of unique page contents

    for doc in documents:
        page_content = doc.page_content
        page_number = doc.metadata['page']  

        # Check if any keyword exists in the page content
        if keyword.lower() in page_content.lower():
            if page_content not in unique_contents:
                unique_contents.add(page_content)  # Add to set to ensure uniqueness
                page_info.append((page_content, page_number + 1))  # Append content with page number (1-indexed)

    return page_info


def create_medical_prompt(condition: str, sections_context_dict: Dict[str, str], context: List[Tuple[str, int]], key_tips: Dict[str, str], fewshot_examples: Dict[str, str]) -> str:
    """
    Creates a prompt based on the given condition, its sections, extracted context, key tips, and condition-specific few-shot examples.

    Args:
        condition (str): The condition to evaluate.
        sections (Dict[str, str]): Sections and their context from the JSON for the given condition.
        context (List[Tuple[str, int]]): Extracted context from the document, with page numbers.
        key_tips (Dict[str, str]): A dictionary containing key tips to include in the prompt.
        fewshot_examples (Dict[str, str]): Dictionary of condition-specific few-shot examples.

    Returns:
        str: The constructed prompt for the LLM.
    """

    # Join sections and context into formatted strings
    sections_text = "\n\n".join(
        f"Section: {section_name}\nContext: {section_context}" for section_name, section_context in sections_context_dict.items()
    )

    section_summary_template = ",\n        ".join([f'"{section_name}": "Summary of {section_name}"' for section_name in sections_context_dict.keys()])

    # Format extracted context with page numbers
    extracted_context = "\n".join([f"Page {page}: {text}" for text, page in context])

    # Add the default key tips to the string
    default_key_tips = """- If relevant information is found outside of the mentioned sections, you should summarize that information in the 'Miscellaneous Summary' section.
- If not, just return 'NA' in the 'Miscellaneous Summary' section. The 'Miscellaneous Summary' will always be part of the overall Summary.
- The Donor Risk Assessment Interview (DRAI) has a series of questions that are aimed at assessing the donor's medical and social history. These are then followed by the answer to the question. Do not assume the question to be statements and return your answers based on the question alone.""" 
    
    key_tips_str = f"Key Tips:\n{default_key_tips}"

    # Include specific key tips for the condition if present
    if condition in key_tips:
        key_tips_str += key_tips[condition]

    examples = fewshot_examples.get(condition, "")

    # Construct the prompt
    prompt = """You are an expert medical director working for LifeNet Health, which is a leading organization in regenerative medicine and life sciences. At LifeNet Health, donors who acknowledge donating their tissues/organs are evaluated based on their medical history, their cause of death, and various tests performed on various tissues/organs. All this information is collated in one document. Your task is to extract relevant information around {condition} from the given donor information and summarize it. Based on the extracted information on {condition}, you also need to provide a final decision on the result/presence of the condition in the donor's body ("CONDITION RESULT": "Positive/Negative/UNKNOWN"). 

CRITICAL: Extract information ONLY from the provided donor document below. Do not use information from other donors, documents, or your training data. Only extract data that is explicitly present in the provided donor document.

Instructions:
1. Extract and summarize relevant information (if present) for the following sections:
{sections}\n
2. You must always return the output in the following JSON format with proper formatting. There should be no backticks (```) in the output. Only the JSON output:
{{
    "Summary" : {{
        {section_summary_template}
    }},
    "CONDITION RESULT" : "Positive/Negative/UNKNOWN"
}}

DONOR DOCUMENT:
{extracted_context}

Key Tips to be followed when returning your answer:
{key_tips_str}

Here are some examples for your reference:
Example:
{{
  'Summary': {{
    'Serology': 'The results for HIV-1/HIV-2 Plus O Antibody and HIV-1 NAT tests are both Non-Reactive',
    'Referral Worksheet': 'No history of HIV found.',
    'DRAI': 'The patient has never had a positive or reactive test for the HIV/AIDS virus.',
    'Miscellaneous Summary': 'The patient did not have any history of HIV in the past 12 months.'
  }},
  'CONDITION RESULT': 'Negative'
}}

Example:
{{
  'Summary': {{
    'Serology': 'Hepatitis B Surface Antigen, Hepatitis C Antibody and Hepatitis B Total Core Antibody tests returned Non-Reactive',
    'DRAI': 'In the past 12 months she/he did not live with a person who had hepatitis.',
    'Miscellaneous Summary': 'NA'
  }},
  'CONDITION RESULT': 'Negative'
}}

{examples}
""".format(
        condition = condition,
        sections = sections_text,
        extracted_context = extracted_context,
        section_summary_template = section_summary_template,
        key_tips_str = key_tips_str,
        examples = examples
    )

    return prompt



def create_done_or_not_prompt(condition: str, sections_context_dict: Dict[str, str], context: List[Tuple[str, int]], key_tips: Dict[str, str], fewshot_examples: Dict[str, str]) -> str:
    """
    Creates a prompt based on the given condition, its sections, extracted context, and the provided key tips.

    Args:
        condition (str): The condition to evaluate.
        sections (Dict[str, str]): Sections and their context from the JSON for the given condition. (section_context.json)
        context (List[Tuple[str, int]]): Extracted context from the document, with page numbers. 
        key_tips (Dict[str, str]): A dictionary containing key tips to include in the prompt. (tips.json)

    Returns:
        str: The constructed prompt for the LLM.
    """

    # Join sections and context into formatted strings
    sections_text = "\n\n".join(
        f"Section: {section_name}\nContext: {section_context}" for section_name, section_context in sections_context_dict.items()
    )

    section_summary_template = ",\n        ".join([f'"{section_name}": "Summary of {section_name}"' for section_name in sections_context_dict.keys()])

    # Format extracted context with page numbers
    extracted_context = "\n".join([f"Page {page}: {text}" for text, page in context])

    # Add the default key tips to the string
    default_key_tips = """- If relevant information is found outside of the mentioned sections, you should summarize that information in the 'Miscellaneous Summary' section.
- If not, just return 'NA' in the 'Miscellaneous Summary' section. The 'Miscellaneous Summary' will always be part of the overall Summary.
- The Donor Risk Assessment Interview (DRAI) has a series of questions that are aimed at assessing the donor's medical and social history. These are then followed by the answer to the question. Do not assume the question to be statements and return your answers based on the question alone.""" 
    
    key_tips_str = f"Key Tips:\n{default_key_tips}"

    # Include specific key tips for the condition if present
    if condition in key_tips:
        key_tips_str += key_tips[condition]
    
    examples = fewshot_examples.get(condition, "")

    # Construct the prompt
    prompt = """You are an expert medical director working for LifeNet Health which is a leading organisation in regenerative medicine and life scienes. At LifeNet Health, donors who acknowledge donating their tissues/organs are evaluated based on their medical history, their cause of death, various tests are performed on various tissues/organs. All these information is collated in one document. Your task is to extract relevant information around {condition} from the given donor information and summarize it. Based on the extracted information on {condition}, you also need to provide a final decision on whether or not the {condition} was done ("RESULT": "Yes/No/UNKNOWN").

CRITICAL: Extract information ONLY from the provided donor document below. Do not use information from other donors, documents, or your training data. Only extract data that is explicitly present in the provided donor document.

Instructions:
1. Extract and summarize relevant information (if present) for the following sections:
{sections}\n
2. You must always return the output in the following JSON format with proper formatting. There should be no backticks (```) in the output. Only the JSON output:
{{
    "Summary" : {{
        {section_summary_template}
    }},
    "CONDITION RESULT" : "Yes/No/UNKNOWN"
}}

Key Tips to be followed when returning your answer:
{key_tips_str}


DONOR DOCUMENT:
{extracted_context}

Here are some examples for your reference:

Example:
{{
  'Summary': {{
    'Donor Refrigeration': 'The donor's body was cooled for 18:05 hours and it was not cooled for 3:05 hours',
    'Miscellaneous Summary': 'NA.'
  }},
  CONDITION RESULT': 'Yes'
}}

Example:
{{
  'Summary': {{
    'DRAI': 'The patient received a COVID Vaccine shot in the past 12 months',
    'Miscellaneous Summary': 'The patient received Pfizer immunizations in January 2021 and February 2021.'
  }},
  'CONDITION RESULT': 'Yes'
}}

{examples}

""".format(
        condition = condition,
        sections = sections_text,
        extracted_context = extracted_context,
        section_summary_template = section_summary_template,
        key_tips_str = key_tips_str,
        examples = examples
    )

    return prompt



def create_was_or_not_prompt(condition: str, sections_context_dict: Dict[str, str], context: List[Tuple[str, int]], key_tips: Dict[str, str], fewshot_examples: Dict[str, str]) -> str:
    """
    Creates a prompt based on the given condition, its sections, extracted context, and the provided key tips.

    Args:
        condition (str): The condition to evaluate.
        sections (Dict[str, str]): Sections and their context from the JSON for the given condition.
        context (List[Tuple[str, int]]): Extracted context from the document, with page numbers.
        key_tips (Dict[str, str]): A dictionary containing key tips to include in the prompt.

    Returns:
        str: The constructed prompt for the LLM.
    """

    # Join sections and context into formatted strings
    sections_text = "\n\n".join(
        f"Section: {section_name}\nContext: {section_context}" for section_name, section_context in sections_context_dict.items()
    )

    section_summary_template = ",\n        ".join([f'"{section_name}": "Summary of {section_name}"' for section_name in sections_context_dict.keys()])

    # Format extracted context with page numbers
    extracted_context = "\n".join([f"Page {page}: {text}" for text, page in context])

    # Add the default key tips to the string
    default_key_tips = """- If relevant information is found outside of the mentioned sections, you should summarize that information in the 'Miscellaneous Summary' section.
- If not, just return 'NA' in the 'Miscellaneous Summary' section. The 'Miscellaneous Summary' will always be part of the overall Summary.
- The Donor Risk Assessment Interview (DRAI) has a series of questions that are aimed at assessing the donor's medical and social history. These are then followed by the answer to the question. Do not assume the question to be statements and return your answers based on the question alone."""

    key_tips_str = f"Key Tips:\n{default_key_tips}"

    # Include specific key tips for the condition if present
    if condition in key_tips:
        key_tips_str += key_tips[condition]

    examples = fewshot_examples.get(condition, "")

    # Construct the prompt
    prompt = """You are an expert medical director working for LifeNet Health which is a leading organisation in regenerative medicine and life scienes. At LifeNet Health, donors who acknowledge donating their tissues/organs are evaluated based on their medical history, their cause of death, various tests are performed on various tissues/organs. All these information is collated in one document. Your task is to extract relevant information around {condition} from the given donor information and summarize it. Based on the extracted information on {condition}, you also need to provide a final decision on whether the donor was or had history of {condition} or not ("CONDITION RESULT": "Yes/No/UNKNOWN").

CRITICAL: Extract information ONLY from the provided donor document below. Do not use information from other donors, documents, or your training data. Only extract data that is explicitly present in the provided donor document.

Instructions:
1. Extract and summarize relevant information (if present) for the following sections:
{sections}\n
2. You must always return the output in the following JSON format with proper formatting. There should be no backticks (```) in the output. Only the JSON output:
{{ 
    "Summary" : {{
        {section_summary_template}
    }},
    "CONDITION RESULT" : "Yes/No/UNKNOWN"
}}

Key Tips to be followed when returning your answer:
{key_tips_str}

DONOR DOCUMENT:
{extracted_context}

Here are some examples for your reference:

Example:
{{
  'Summary': {{
    'DRAI': 'The patient was not in Jail or a correctional facility in the past 12 months',
    'Miscellaneous Summary': 'The donor has no history of jailtime throughout his/her life'
  }},
  'CONDITION RESULT': 'No'
}}

{examples}
""".format(
        condition = condition,
        sections = sections_text,
        extracted_context = extracted_context,
        section_summary_template = section_summary_template,
        key_tips_str = key_tips_str,
        examples = examples
    )
    return prompt


def get_topic_summary_llm_result(llm: AzureOpenAI, condition: str, prompt: str) -> str:
    """
    Uses LLM to determine whether the patient has the given condition based on the prompt.

    Args:
        llm (AzureOpenAI): The AzureOpenAI instance for classification.
        condition (str): The condition to check
        prompt (str): The constructed prompt with context.

    Returns:
        str: The LLM's response indicating the presence of the condition.
    """
    response = llm.invoke(prompt)
    
    return response



def parse_conditions(output):
    """
    This function takes a dictionary where keys are condition names, 
    and values are JSON-like strings. It parses each string into a dictionary 
    using ast.literal_eval and returns a new dictionary with the parsed results. 
    If an error occurs, it stores the error message as part of the dictionary.

    Args:
    - output (dict): A dictionary where keys are condition names, 
                     and values are JSON-like strings.
    
    Returns:
    - parsed_conditions (dict): A dictionary with condition names as keys 
                                and parsed dictionaries as values.
                                If parsing fails, stores the error as a string.
    """
    # Set up logging
    logging.basicConfig(level=logging.ERROR)
    logger = logging.getLogger(__name__)

    parsed_conditions = {}

    # Loop through each condition and parse its corresponding string
    from .utils.json_parser import safe_parse_llm_json, LLMResponseParseError
    
    for condition, json_string in output.items():
        try:
            # Convert the JSON-like string to a dictionary using robust JSON parser
            parsed_conditions[condition] = safe_parse_llm_json(
                json_string,
                context=f"topic summarization for {condition}"
            )
            parsed_conditions[condition] = lowercase_keys(parsed_conditions[condition])
        except LLMResponseParseError as e:
            # Log the error and add it to the dictionary
            error_message = f"Error parsing {condition.upper()}: {e}"
            logger.error(error_message)
            parsed_conditions[condition] = {
                "Error": error_message,
                "error_type": "parse_error",
                "LLM Response": json_string[:500]  # Limit response preview
            }
        except Exception as e:
            # Log unexpected errors
            error_message = f"Unexpected error parsing {condition.upper()}: {e}"
            logger.error(error_message, exc_info=True)
            parsed_conditions[condition] = {
                "Error": error_message,
                "error_type": "unexpected_error",
                "LLM Response": json_string[:500]
            }

    return parsed_conditions


def merge_conditions_with_citations_and_sections(summary_dict, pages_dict):
    """
    Merges the summary and pages dictionaries on the condition key.
    Retains original summary section names, adds 'Decision' as the first key, 
    and merges all citations into a single list under 'Citation'. Handles cases 
    where there is an error in the summary by printing out a predefined error structure.

    Args:
    - summary_dict (dict): Dictionary with condition summaries and results.
    - pages_dict (dict): Dictionary with pages where each condition is found.

    Returns:
    - merged_dict (dict): A new dictionary with unwrapped summaries, 
                          'Decision' as the first key, and citations under 'Citation'.
    """
    final_merged_dict = {}

    # Loop through all conditions in the summary dictionary
    for condition, summary_data in summary_dict.items():
        merged_condition = {}

        # Check if the summary data contains an error or if it's missing
        if isinstance(summary_data, dict) and "Error" in summary_data:
            # Predefined error structure from parse_conditions() function
            merged_condition['decision'] = summary_data['Error']
            merged_condition['summary'] = summary_data['LLM Response']
            merged_condition['citation'] = pages_dict[condition]
            
        else:
            # Add the CONDITION RESULT as the 'Decision' first
            merged_condition['decision'] = summary_data.get('condition result', 'UNKNOWN')

            # Unwrap the Summary section by retaining original keys
            summary_sections = summary_data.get('summary', {})
            # print(summary_sections)

            for section_name, summary in summary_sections.items():
                merged_condition[section_name] = summary

            merged_condition['citation'] = pages_dict[condition] # all_pages if all_pages else None

        # Add the merged condition to the final dictionary
        final_merged_dict[condition] = merged_condition

    return final_merged_dict

def create_T3_summary_prompt(topic: str, text_chunks: List[Document], instructions, fewshot_examples: str) -> str:
    """
    Creates a prompt for summarizing information related to a specific condition based on text chunks and provides 
    the page numbers where the condition is found. The summary will include the Donor ID extracted from the filename.

    Args:
        topic (str): The condition to evaluate.
        text_chunks (List[Document]): List of Document objects containing text chunks and page numbers.

    Returns:
        str: The constructed prompt for the LLM.
    """
    # Combine the text chunks into a single context block, including page numbers
    context = "\n".join([f"Page {doc.metadata['page']+1}: {doc.page_content}" for doc in text_chunks])

    # Construct the combined prompt for summary and page search
    prompt = f"""Role: You are an MD at LifeNet Health tasked with extracting and summarizing information related to specific topics based on provided context. These topics are related to donors who have agreed to donate their organs/tissues. These topics aim to summarize the medical history of the donor and assess if their tissues/organs are fit to be donated to others.

CRITICAL: Extract information ONLY from the provided donor document below. Do not use information from other donors, documents, or your training data. Only extract data that is explicitly present in the provided context.

Instructions: 
- Give a detailed summary of the findings related to the topic '{topic}' based on the provided context. Summarize all relevant information together.
{instructions}

Topic: {topic}

Context:
{context}

Provide a concise summary of the findings related to the topic '{topic}'.
Also, return the page numbers where the condition is found in the document.

The output should only be in a JSON format. Do not print anything else other than the output, including backticks:
{fewshot_examples}
"""
    return prompt


def ts_llm_call_with_pause(llm, condition, prompt, max_retries=3, delay=3):
    """
    This function will attempt to call the LLM up to `max_retries` times with a delay of `delay` seconds
    between retries in case of a rate limit error.
    """
    attempt = 0
    while attempt < max_retries:
        try:
            result = get_topic_summary_llm_result(llm, condition, prompt)
            return result  # Return result if successful
        except Exception as e:
            
            if "rate limit" in str(e).lower():
                print(f"Rate limit error encountered. Retrying in {delay} seconds... (Attempt {attempt+1}/{max_retries})")
                time.sleep(delay)  # Pause for `delay` seconds
                attempt += 1  # Increment the retry count
            else:
                # If it's another error, raise it
                raise e

    # If we reach here, all retries failed
    raise Exception(f"Max retries reached for condition '{condition}'")

def lowercase_keys(data):
    
    new_dict = {}

    for key in data:
        
        lower_key = key.lower()
        new_dict[lower_key] = data[key]

    return new_dict


def get_T1_results(t1_conditions, t1_context, t1_tips, t1_fewshot, llm, page_doc_list):

    medical_prompt_conditions = set()
    was_or_not_prompt_conditions = set()
    done_or_not_prompt_conditions = set()
    # t3_prompt_conditions = set()

    for _, row in t1_conditions.iterrows():
        topic = row['Topic']
        prompt_condition = row['T1_Type']
        if prompt_condition == 'medical_prompt_conditions':
            medical_prompt_conditions.add(topic)
        elif prompt_condition == 'was_or_not_prompt_conditions':
            was_or_not_prompt_conditions.add(topic)
        elif prompt_condition == 'done_or_not_prompt_conditions':
            done_or_not_prompt_conditions.add(topic)
        else:
            print(f'{prompt_condition} is not a valid T1 prompt condition!')
        # else:
        #     t3_prompt_conditions.add(topic)

    conditions = list(medical_prompt_conditions | was_or_not_prompt_conditions | done_or_not_prompt_conditions)

    results = {}  # To store Summary and Yes/No result for each condition
    final_page_results = {}  # To store the list of pages for each condition
    
    for condition in conditions: 
        page_info = search_keywords(page_doc_list, condition)
        page_numbers = [page_num for _, page_num in page_info]
        sections = t1_context.get(condition, {})
        try:
            if not page_numbers:  # If no page numbers found
                default_output = '''{
                    "summary" : {
                        "Miscellaneous Summary": "No instances found in this DC."
                    },
                    "condition result" : "NA"
                }'''
                results[condition] = default_output
                final_page_results[condition] = []
            else:
                # Determine which prompt to use based on the condition
                if condition in medical_prompt_conditions:
                    prompt = create_medical_prompt(condition, sections, page_info, t1_tips, t1_fewshot)
                elif condition in was_or_not_prompt_conditions:
                    prompt = create_was_or_not_prompt(condition, sections, page_info, t1_tips, t1_fewshot)
                elif condition in done_or_not_prompt_conditions:
                    prompt = create_done_or_not_prompt(condition, sections, page_info, t1_tips, t1_fewshot)
                else:
                    continue  # Skip any conditions that don't match the predefined lists

                # Classify the condition as present ("Yes") or absent ("No")
                result = ts_llm_call_with_pause(llm, condition, prompt)
                results[condition] = result.content.replace("`", "").replace("json", "").strip()
                final_page_results[condition] = page_numbers

        except Exception as e:
            error_msg = f"{{'Error': '{e}'}}"
            results[condition] = f"{{'summary': {error_msg}, 'condition result': 'NA'}}"
            final_page_results[condition] = page_numbers
    all_summaries_dict = parse_conditions(results)
    return all_summaries_dict, final_page_results


def get_T3_results(t3_conditions, vectordb, t3_context, t3_instruction, t3_fewshot, llm):
    final_results = {}
    final_page_results = {}

    for _, row in t3_conditions.iterrows():
        topic = row['Topic']
        if topic.lower() in ['medical history'] :
            top_k = 15
        else :
            top_k = 10
        if topic.lower() in ['donor information']: # , 'organ transplant recipient'
            search_type = 'mmr'
        else:
            search_type = 'similarity'
        retriever = vectordb.as_retriever(search_type=search_type, search_kwargs={'k': top_k})
        try:
            ret_docs = retriever.invoke(t3_context[topic])
        except Exception as e:
            print('Error retrieving documents for {topic}: {e}')
        try:
            # Check if any documents were found for the condition
            if len(ret_docs)>0: 
                
                # Create a prompt specifically for this condition with page numbers
                prompt = create_T3_summary_prompt(topic, ret_docs, t3_instruction[topic].replace("'", '"'), t3_fewshot[topic].replace("'", '"'))
                
                # Get the summary from the LLM
                response = ts_llm_call_with_pause(llm, topic, prompt)
                
                # Store the result in the dictionary
                llm_result = response.content.replace("`", "").replace("json", "").strip()
                all_ret_docs = [(doc.metadata['page'], doc.page_content) for doc in ret_docs]
            else:
                # If no documents were found, handle the case
                empty_res = '''{
                    "presence": "NA",
                    "summary": "NA",
                    "pages": []
                }'''
                llm_result = empty_res
                all_ret_docs = []

        except Exception as e:
            # logger.error(f"Error processing condition '{condition}': {str(e)}")
            error_res = f'''{{
                "presence": "CM Error in LLM response: {str(e)}",
                "summary": "CM Error in LLM response: {str(e)}",
                "pages": []
            }}'''
            llm_result = error_res
            all_ret_docs = [(doc.metadata['page'], doc.page_content) for doc in ret_docs]

        try:
            from .utils.json_parser import safe_parse_llm_json, LLMResponseParseError
            
            llm_result_dict = safe_parse_llm_json(
                llm_result,
                context=f"topic summarization for {topic}"
            )
            llm_result_dict = lowercase_keys(llm_result_dict)
            
            # Validate required keys
            if 'presence' not in llm_result_dict or 'pages' not in llm_result_dict:
                raise LLMResponseParseError(
                    f"Missing required keys 'presence' or 'pages' in response. "
                    f"Context: topic summarization for {topic}"
                )
            
            decision_string = llm_result_dict['presence']
            pages_string = llm_result_dict['pages']
            # In future we need to create separate bucket for topics like DIF, COD etc. where very specific information is to be extracted as opposed to summarize. We'll call them T2.
            if topic.lower() == 'donor information': 
                if isinstance(llm_result_dict['summary'], dict):
                    summary_dict = llm_result_dict['summary']
                else:
                    summary_dict = {'name': llm_result_dict['summary'], 'age': 'NA', 'gender': 'NA'}
            else:
                summary_dict = {topic: llm_result_dict['summary']}
            final_results[topic] = {'summary': summary_dict, 'condition result': decision_string}
            final_page_results[topic] = pages_string
        except Exception as e:
            print(e)
            if topic.lower() == 'donor information':
                try:
                    name_pattern = r'"name":\s*"([^"]*)"'
                    age_pattern = r'"age":\s*("[^"]*"|\bnull\b)'
                    gender_pattern = r'"gender":\s*("[^"]*"|\bnull\b)'

                    # Search for Name, Age, and Gender in the llm_result using regex
                    name_match = re.search(name_pattern, llm_result)
                    age_match = re.search(age_pattern, llm_result)
                    gender_match = re.search(gender_pattern, llm_result)

                    # Extract matched groups or return 'N/A' if not found
                    name = name_match.group(1) if name_match else 'N/A'
                    age = age_match.group(1) if age_match else 'N/A'
                    gender = gender_match.group(1) if gender_match else 'N/A'

                    # Create the summary dictionary
                    summary_dict = {
                        'name': name,
                        'age': age,
                        'gender': gender
                    }
            
                except:
                    summary_dict = {'name': 'NA', 'age': 'NA', 'gender': 'NA'}
            else:
                summary_dict = {topic: llm_result}
            final_results[topic] = {'summary': summary_dict, 'condition result': 'NA'}
            final_page_results[topic] = 'NA'

    return final_results, final_page_results

def classify_all_conditions(output):
    transformation_map = {
        'Track Mark': {'yes': 'Positive', 'no': 'Negative', 'unknown': 'Ambiguous'},
        'Homeless': {'yes': 'Positive', 'no': 'Negative', 'unknown': 'Ambiguous'},
        'Jail': {'yes': 'Positive', 'no': 'Negative', 'unknown': 'Ambiguous'},
        'Cooled': {'yes': 'Negative', 'no': 'Positive', 'unknown': 'Ambiguous'},
        'Dialysis': {'yes': 'Positive', 'no': 'Negative', 'unknown': 'Ambiguous'},
        'Illicit': {'yes': 'Positive', 'no': 'Negative', 'unknown': 'Ambiguous'},
        'Immunization': {'yes': 'Negative', 'no': 'Positive', 'unknown': 'Ambiguous'},
        'Prep': {'yes': 'Negative', 'no': 'Positive', 'unknown': 'Ambiguous'},
        'Steroid': {'yes': 'Positive', 'no': 'Negative', 'unknown': 'Ambiguous'},
        'Travel': {'yes': 'Positive', 'no': 'Negative', 'unknown': 'Ambiguous'},
        'Toxicology': {'yes': 'Positive', 'no': 'Negative', 'unknown': 'Ambiguous'},
        'Autopsy': {'yes': 'Positive', 'no': 'Negative', 'unknown': 'Ambiguous'}
    }

    positive_negative_conditions = ['Autoimmune', 'Cancer', 'Dementia', 'Granuloma', 'Hepatitis',
                                    'HIV', 'Infection', 'Jaundice', 'Tuberculosis', 'Lymph', 
                                    'Blood Culture', 'Urine Culture', 'SARS', 'Sepsis', 'Mass', 
                                    'Organ Transplant Recipient']

    neutral_conditions = ['Donor Risk Assessment Interview', 'Donor Information', 'Medical History', 'Organ Donation', 'Cause of Death']

    for condition_name, condition_output in output.items():
        decision = condition_output.get('decision', 'NA').lower()  # Normalize decision
        citation_len = len(condition_output.get('citation', []))  # Correctly get citation length
        classifier = {}

        # Case 1: Handle 'NA' decision with citation check
        if decision == 'na':
            if citation_len == 0:
                classifier['presence'] = 'No'
            else:
                classifier['presence'] = 'Yes'
                classifier['category'] = 'Ambiguous'

        # Case 2: Handle Positive/negative/unknown conditions
        elif condition_name in positive_negative_conditions:
            classifier['presence'] = 'Yes'
            if decision == 'positive':
                classifier['category'] = 'Positive'
            elif decision == 'negative':
                classifier['category'] = 'Negative'
            elif decision == 'unknown':
                classifier['category'] = 'Ambiguous'

        # Case 3: Handle neutral conditions
        elif condition_name in neutral_conditions:
            classifier['presence'] = 'Yes'
            classifier['category'] = 'Neutral'

        # Case 4: Handle conditions with transformation
        elif condition_name in transformation_map:
            if decision in transformation_map[condition_name]:
                classifier['presence'] = 'Yes'
                classifier['category'] = transformation_map[condition_name][decision]
                
        condition_output['classifier'] = classifier

    return output


def get_topic_summary_results(vectordb, topic_df, t1_context, t1_tips, t1_fewshot, t3_context, t3_instruction, t3_fewshot, llm, page_doc_list):
    
    # top_k = 10
    # retriever = vectordb.as_retriever(search_type='similarity', search_kwargs={'k': top_k})
    
    # # Retrieve relevant document chunks based on the query
    # ret_docs = retriever.invoke(context)

    # context = "\n".join([f"Page {doc.metadata['page']}: {doc.page_content}" for doc in ret_docs])
    t1_conditions = topic_df[topic_df['Level'] == 'T1']
    t3_conditions = topic_df[topic_df['Level'] == 'T2']

    t1_all_summaries, t1_all_citations = get_T1_results(t1_conditions, t1_context, t1_tips, t1_fewshot, llm, page_doc_list)
    t3_all_summaries, t3_all_citations = get_T3_results(t3_conditions, vectordb, t3_context, t3_instruction, t3_fewshot, llm)    
    
    t1_t3_all_summaries = {**t1_all_summaries, **t3_all_summaries}
    t1_t3_all_citations = {**t1_all_citations, **t3_all_citations}

    # Change the formatting to what's expected in the DB
    final_topic_summary_results1 = merge_conditions_with_citations_and_sections(t1_t3_all_summaries, t1_t3_all_citations)

    final_topic_summary_results = classify_all_conditions(final_topic_summary_results1)

    return final_topic_summary_results
