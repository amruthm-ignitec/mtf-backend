import io
import os
import pandas as pd
import json
import shutil
from pathlib import Path
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
import boto3
from utils.llm_config import llm_setup
from utils.blob_connections import blob_connection, mount_blob, get_pdf_files, load_pdf_from_blob_storage, uploadToBlobStorage, renameBlob, move_to_not_processed, check_and_process_file
from utils.helper_functions import get_prompt_components, data_load, get_embeddings, processing_dc, delete_pdf
from utils.postgres import sqlalchemy_connection, update_db_data_prod_sqlalchemy, update_db_meta_prod_sqlalchemy_1, update_db_meta_prod_sqlalchemy
from module.culture import get_llm_response, get_ms_categories, remove_species, reranking_culture, get_collated_donor_info, get_culture_results
from module.serology import get_llm_response_sero, reranking_serology, update_test_names, get_relevant_chunks, convert_to_tuples, standardize_and_deduplicate_results, get_serology_results, get_qa_results
from module.topic_summarization import search_keywords, create_medical_prompt, create_done_or_not_prompt, create_was_or_not_prompt, get_topic_summary_llm_result, parse_conditions, merge_conditions_with_citations_and_sections, create_T3_summary_prompt, ts_llm_call_with_pause, get_T1_results, get_T3_results, get_topic_summary_results

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FileHandler:
    def __init__(self, temp_dir="temp"):
        self.temp_dir = temp_dir
        self._ensure_temp_directory()

    def _ensure_temp_directory(self):
        """Create temp directory if it doesn't exist"""
        Path(self.temp_dir).mkdir(parents=True, exist_ok=True)
        logger.info(f"Temp directory ensured at: {self.temp_dir}")

    def get_temp_path(self, filename):
        """Get full path for temporary file"""
        return os.path.join(self.temp_dir, os.path.basename(filename))

    def cleanup_temp_file(self, filepath):
        """Safely remove temporary file"""
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                logger.info(f"Cleaned up temporary file: {filepath}")
        except Exception as e:
            logger.warning(f"Failed to cleanup temporary file {filepath}: {e}")

    def cleanup_temp_directory(self):
        """Remove all files in temp directory"""
        try:
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
                os.makedirs(self.temp_dir)
                logger.info("Cleaned up temp directory")
        except Exception as e:
            logger.warning(f"Failed to cleanup temp directory: {e}")

class DOSpacesManager:
    def __init__(self):
        self.spaces_key = "DO00GV37Z343WU7ZTRVU"
        self.spaces_secret = "+hg3EtXTORJSoH9IduE9QEWU0fxGPhF0ncLWBgjuH5s"
        self.region = "nyc3"
        self.bucket_name = "donoriq-storage"
        self.endpoint_url = f"https://{self.region}.digitaloceanspaces.com"
        
        self.s3_client = boto3.client(
            's3',
            region_name=self.region,
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.spaces_key,
            aws_secret_access_key=self.spaces_secret
        )

    def list_files(self, prefix: str) -> List[str]:
        """List all files in the specified prefix (directory)"""
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix
            )
            if 'Contents' in response:
                return [obj['Key'] for obj in response['Contents'] if obj['Key'].endswith('.pdf')]
            return []
        except Exception as e:
            logger.error(f"Error listing files: {e}")
            raise

    def download_file(self, space_path: str, local_path: str) -> bool:
        """Download a file from DO Spaces"""
        try:
            self.s3_client.download_file(self.bucket_name, space_path, local_path)
            return True
        except Exception as e:
            logger.error(f"Error downloading file {space_path}: {e}")
            return False

    def move_file(self, old_path: str, new_path: str) -> bool:
        """Move/rename a file within DO Spaces"""
        try:
            # Copy the object to the new location
            self.s3_client.copy_object(
                Bucket=self.bucket_name,
                CopySource={'Bucket': self.bucket_name, 'Key': old_path},
                Key=new_path
            )
            # Delete the old object
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=old_path
            )
            return True
        except Exception as e:
            logger.error(f"Error moving file {old_path} to {new_path}: {e}")
            return False

def check_file_size(file_path: str, max_size_mb: int = 450) -> bool:
    """Check if file size is within limits"""
    file_size = os.path.getsize(file_path) / (1024 * 1024)  # Convert to MB
    return file_size <= max_size_mb

def process_file(file_path: str, spaces_manager: DOSpacesManager, engine, llm, embeddings) -> Dict:
    """Process a single PDF file"""

    file_handler = FileHandler()
    local_path = None

    try:
        # Extract donor ID from filename
        blob_name = os.path.basename(file_path)
        donor_id = blob_name.split(' ')[0].split('.')[0]
        print("Donor ID-"+donor_id)
        
        # Generate a unique job ID (you might want to implement your own logic)
        job_id = datetime.now().strftime('%Y%m%d%H%M%S')
        uid = f"{donor_id}_{job_id}"

        # Create temp directory if it doesn't exist
        local_path = file_handler.get_temp_path(blob_name)
        logger.info(f"Processing file {blob_name} to temporary location: {local_path}")


        # Download file
        if not spaces_manager.download_file(file_path, local_path):
            return {
                "status": "error",
                "message": "Failed to download file",
                "uid": uid,
                "donor_id": donor_id
            }

        # Verify file exists after download
        if not os.path.exists(local_path):
            return {
                "status": "error",
                "message": f"File not found after download: {local_path}",
                "uid": uid,
                "donor_id": donor_id
            }

        # Check file size
        if not check_file_size(local_path):
            os.remove(local_path)
            return {
                "status": "error",
                "message": "File size exceeded",
                "uid": uid,
                "donor_id": donor_id
            }

        # Process the file (original logic from your code)
        page_doc_list, doc_list, vectordb = processing_dc(local_path, embeddings)
        
        # Get prompt components
        role, disease_context, basic_instruction, reminder_instructions, serology_dictionary, \
        t1_context, t1_tips, t1_fewshot, topic_df, t3_context, t3_instruction, t3_fewshot, \
        subtissue_map, MS_MO_category_map = get_prompt_components()

        # Run pipelines
        culture_res, serology_res = get_qa_results(
            llm, vectordb, disease_context, role, basic_instruction, 
            reminder_instructions, serology_dictionary, subtissue_map, 
            MS_MO_category_map
        )

        topic_summary_res = get_topic_summary_results(
            vectordb, topic_df, t1_context, t1_tips, t1_fewshot,
            t3_context, t3_instruction, t3_fewshot, llm, page_doc_list
        )

        # Update database
        donor_details = {
            k.lower(): v for k, v in topic_summary_res['Donor Information'].items() 
            if k not in ['decision', 'citation', 'classifier']
        }
        
        update_db_result = update_db_data_prod_sqlalchemy(
            engine, uid, serology_res, culture_res, topic_summary_res
        )

        if update_db_result == "Success":
            update_db_meta_prod_sqlalchemy(
                engine, uid, donor_id, job_id, donor_details, update_db_result
            )
            
            # Move file to processed folder
            new_path = f"PROCESSED/{blob_name}"
            spaces_manager.move_file(file_path, new_path)
            
        # Cleanup
        os.remove(local_path)
        
        return {
            "status": "success",
            "message": "File processed successfully",
            "uid": uid,
            "donor_id": donor_id
        }

    except Exception as e:
        logger.error(f"Error processing file {file_path}: {e}")
        return {
            "status": "error",
            "message": str(e),
            "uid": uid,
            "donor_id": donor_id
        }

    finally:
        # Cleanup temporary file
        if local_path and os.path.exists(local_path):
            file_handler.cleanup_temp_file(local_path)

def main():

    file_handler = FileHandler()
    try:
        # Initialize DO Spaces manager
        spaces_manager = DOSpacesManager()
        
        # Initialize database connection
        engine = sqlalchemy_connection()
        
        # Initialize LLM and embeddings
        llm, embeddings = llm_setup()

        # Get list of files to process
        files = spaces_manager.list_files("QUEUE/")
        
        for file_path in files:
            logger.info(f"Processing file: {file_path}")
            result = process_file(file_path, spaces_manager, engine, llm, embeddings)
            logger.info(f"Result: {result}")

            # Delay between files to prevent rate limiting
            time.sleep(30)
    
    except Exception as e:
        logger.error(f"Error in main process: {e}")
        
    finally:
        # Final cleanup
        file_handler.cleanup_temp_directory()


if __name__ == "__main__":
    main()