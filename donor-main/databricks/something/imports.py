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


