import io
import os
import pandas as pd
import json
from datetime import datetime
import ast
import time
from azure.storage.blob import BlobServiceClient, ContentSettings
import langchain 
from langchain_openai import AzureChatOpenAI
from langchain_openai import AzureOpenAIEmbeddings
from langchain.text_splitter import CharacterTextSplitter, RecursiveCharacterTextSplitter
from langchain.document_loaders import PyMuPDFLoader
from langchain_community.vectorstores import FAISS
# from langchain_core.documents import Document
from langchain_community.document_loaders import PDFMinerLoader
from langchain_community.document_loaders import PDFPlumberLoader
from PyPDF2 import PdfReader
from langchain.schema import Document
import logging
from typing import List, Tuple, Dict
from azure.core.exceptions import HttpResponseError
from openai import BadRequestError
import psycopg2
from sqlalchemy import create_engine
from sqlalchemy import text
import pandas as pd
from sqlalchemy import Table, Column, String, JSON, DateTime, MetaData, insert
import re

from utils.llm_config import llm_setup
from utils.blob_connections import blob_connection, mount_blob, get_pdf_files, load_pdf_from_blob_storage, uploadToBlobStorage, renameBlob, move_to_not_processed, check_and_process_file
from utils.helper_functions import get_prompt_components, data_load, get_embeddings, processing_dc, delete_pdf
from utils.postgres import sqlalchemy_connection, update_db_data_prod_sqlalchemy, update_db_meta_prod_sqlalchemy_1, update_db_meta_prod_sqlalchemy
from module.culture import get_llm_response, get_ms_categories, remove_species, reranking_culture, get_collated_donor_info, get_culture_results
from module.serology import get_llm_response_sero, reranking_serology, update_test_names, get_relevant_chunks, convert_to_tuples, standardize_and_deduplicate_results, get_serology_results, get_qa_results
from module.topic_summarization import search_keywords, create_medical_prompt, create_done_or_not_prompt, create_was_or_not_prompt, get_topic_summary_llm_result, parse_conditions, merge_conditions_with_citations_and_sections, create_T3_summary_prompt, ts_llm_call_with_pause, get_T1_results, get_T3_results, get_topic_summary_results

def main():
    llm, embeddings = llm_setup()

    path_to_blob = "QUEUE"
    (connection_string, container_name) = blob_connection()
    (blob_service_client, container_client) = mount_blob(connection_string, container_name)
    pdf_files = get_pdf_files(container_client, path_to_blob)
    engine = sqlalchemy_connection()
    role, disease_context, basic_instruction, reminder_instructions, serology_dictionary, t1_context, t1_tips, t1_fewshot, topic_df, t3_context, t3_instruction, t3_fewshot, subtissue_map, MS_MO_category_map = get_prompt_components()


    for full_blob_name in pdf_files:
        print('Full Blob Name: ', full_blob_name)
        blob_name = full_blob_name.split('/')[-1]
        donor_id = blob_name.split(' ')[0]
        dbfs_path = f"DC_TEMP/{blob_name}"
        job_id = dbutils.widgets.get('job_id')
        # job_id = '000'
        uid = donor_id + '_' + job_id
        
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=full_blob_name)

        check_result = check_and_process_file(blob_client, container_name, blob_service_client, full_blob_name, dbfs_path)
    
        if check_result["status"] == "error":
            error_status = check_result["message"] 
            update_db_meta_prod_sqlalchemy(
                engine, uid, donor_id, job_id, 
                donor_details={'name': 'Na', 'age': 'Na', 'gender': 'Na'}, 
                status=error_status  
            )
            continue

        # Chunk and create embeddings for the PDF
        page_doc_list, doc_list, vectordb = processing_dc(dbfs_path, embeddings)

        # QA Culture & QA Serology pipeline run
        culture_res, serology_res = get_qa_results(llm, vectordb, disease_context, role, basic_instruction, reminder_instructions, serology_dictionary, subtissue_map, MS_MO_category_map)

        # Topic Summary pipeline run
        topic_summary_res = get_topic_summary_results(vectordb, topic_df, t1_context, t1_tips, t1_fewshot, t3_context, t3_instruction, t3_fewshot, llm, page_doc_list)


        donor_details = {k.lower(): v for k, v in topic_summary_res['Donor Information'].items() if k not in ['decision', 'citation', 'classifier']}
        
        update_db_result_data = update_db_data_prod_sqlalchemy(engine, uid, serology_res, culture_res, topic_summary_res)
        print(update_db_result_data)
        update_db_result_meta = update_db_meta_prod_sqlalchemy(engine, uid, donor_id, job_id, donor_details, update_db_result_data)

        if update_db_result_meta:
            new_blob_name = 'PROCESSED/' + blob_name
            new_blob_client = blob_service_client.get_blob_client(container=container_name, blob=new_blob_name)
            renameBlob(blob_client, new_blob_client)
    

if __name__ == "__main__":
    main()