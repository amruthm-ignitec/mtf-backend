import os
import pandas as pd
import json
from langchain.text_splitter import CharacterTextSplitter, RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_community.vectorstores import FAISS
# from langchain_core.documents import Document
from langchain_community.document_loaders import PDFMinerLoader
from langchain_community.document_loaders import PDFPlumberLoader
from langchain.schema import Document

# Get the base directory for config files (relative to this file)
_CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config')

def get_prompt_components(): 
    # This is the role for chunk extraction task
    with open(os.path.join(_CONFIG_DIR, "role.json"), 'r') as f:
        role = json.load(f)

    # This is the context for chunk extraction task
    with open(os.path.join(_CONFIG_DIR, "context.json"), 'r') as f:
        disease_context = json.load(f)

    # This is the instruction that goes into the prompt (LLM) using LLM API call
    with open(os.path.join(_CONFIG_DIR, "instruction.json"), 'r') as f:
        basic_instruction = json.load(f)

    # This is the reminder that goes into the prompt (LLM) using LLM API call
    with open(os.path.join(_CONFIG_DIR, "reminder_instruction.json"), 'r') as f:
        reminder_instructions = json.load(f)

    # This is the serology test name synonym dictionary
    with open(os.path.join(_CONFIG_DIR, "new_serology_dictionary.json"), 'r') as f:
        serology_dictionary = json.load(f)

    with open(os.path.join(_CONFIG_DIR, "cat.json"), 'r') as f:
        MS_MO_category_map = json.load(f)

    with open(os.path.join(_CONFIG_DIR, "newMS.json"), 'r') as f:
        subtissue_map = json.load(f)

    with open(os.path.join(_CONFIG_DIR, "Summary_topics.csv"), 'r') as f:
        topic_df = pd.read_csv(f)

    with open(os.path.join(_CONFIG_DIR, "t1_section_context.json"), 'r') as file:
        t1_context = json.load(file)
    with open(os.path.join(_CONFIG_DIR, "t1_tips.json"), 'r') as file:
        t1_tips = json.load(file)
    with open(os.path.join(_CONFIG_DIR, "t1_fewshot.json"), 'r') as file:
        t1_fewshot = json.load(file)

    # T3 topics prompt components
    with open(os.path.join(_CONFIG_DIR, "t3_context.json"), 'r') as file:
        t3_context = json.load(file)
    with open(os.path.join(_CONFIG_DIR, "t3_instruction.json"), 'r') as file:
        t3_instruction = json.load(file)
    with open(os.path.join(_CONFIG_DIR, "t3_fewshot.json"), 'r') as file:
        t3_fewshot = json.load(file)

    return role, disease_context, basic_instruction, reminder_instructions, serology_dictionary, t1_context, t1_tips, t1_fewshot, topic_df, t3_context, t3_instruction, t3_fewshot, subtissue_map, MS_MO_category_map




def data_load(filename, parser_name):
    '''
    Loads data from PDF file and chunks it
    '''
    try:
        # Check if file exists first
        if not os.path.exists(filename):
            raise FileNotFoundError(f"PDF file not found: {filename}")
        
        if parser_name == "pymupdf":
            loader = PyMuPDFLoader(filename)
            page_docs = loader.load()
        elif parser_name == "pdfminer":
            loader = PDFMinerLoader(filename, concatenate_pages=False)
            temp_page_docs = loader.load()
            page_docs=[]
            for num, doc in enumerate(temp_page_docs):
                new_doc = Document(page_content=doc.page_content, metadata={'source': doc.metadata['source'], 'page': num+1})
                page_docs.append(new_doc)
        elif parser_name == "pdfplumber":
            loader = PDFPlumberLoader(filename)
            page_docs = loader.load()
        else:
            raise ValueError(f"Unknown parser name: {parser_name}")
        
        if not page_docs or len(page_docs) == 0:
            raise ValueError(f"PDF file appears to be empty or could not be parsed: {filename}")
        
        text_splitter = CharacterTextSplitter(
                separator = " ",
                chunk_size = 3000,
                chunk_overlap  = 250 
            )
        chunk_docs =  text_splitter.split_documents(page_docs)
        
        # Filter out empty chunks (can cause embedding issues)
        chunk_docs = [doc for doc in chunk_docs if doc.page_content and doc.page_content.strip()]
        
        if not chunk_docs or len(chunk_docs) == 0:
            raise ValueError(f"PDF file produced no valid text chunks after splitting: {filename}")
        
        return page_docs, chunk_docs
    except Exception as e:
        # Re-raise with more context
        raise Exception(f"Failed to load PDF file '{filename}' using {parser_name}: {str(e)}") from e
    

def get_embeddings(filename, chunk_docs, embeddings, save_embeddings=False, embeddings_dir='Embeddings'):
    '''
    Creates embeddings and optionally saves them locally
    '''
    import logging
    logger = logging.getLogger(__name__)
    
    # Validate inputs
    if embeddings is None:
        raise ValueError(f"Embeddings object is None. Check embedding deployment configuration.")
    
    if not chunk_docs or len(chunk_docs) == 0:
        raise ValueError(f"No document chunks to embed for file: {filename}")
    
    # Filter out empty or very short chunks (can cause embedding API issues)
    valid_chunks = []
    for doc in chunk_docs:
        content = doc.page_content.strip() if doc.page_content else ""
        # Skip chunks that are too short (less than 10 characters)
        # These often cause issues with embedding APIs
        if len(content) >= 10:
            valid_chunks.append(doc)
    
    if not valid_chunks:
        raise ValueError(f"PDF '{filename}' has no valid chunks to embed (all chunks are empty or too short)")
    
    if len(valid_chunks) != len(chunk_docs):
        logger.warning(f"Filtered out {len(chunk_docs) - len(valid_chunks)} empty/short chunks from {filename}")
    
    # Log chunk statistics for debugging
    total_chars = sum(len(doc.page_content) for doc in valid_chunks)
    avg_chunk_size = total_chars / len(valid_chunks) if valid_chunks else 0
    logger.info(f"Creating embeddings for {filename}: {len(valid_chunks)} chunks, avg size: {avg_chunk_size:.0f} chars")
    
    try:
        # FAISS.from_documents will call the embedding API for each chunk
        # This can fail for large PDFs or if there are API rate limits
        vectordb = FAISS.from_documents(documents = valid_chunks, embedding = embeddings)
        
        if save_embeddings:
            em_dir_name = os.path.basename(filename).replace('.pdf','').replace(' ','_')
            embeddings_path = os.path.join(embeddings_dir, em_dir_name)
            os.makedirs(embeddings_path, exist_ok=True)
            vectordb.save_local(embeddings_path)
            return vectordb, em_dir_name
        return vectordb, None
    except Exception as e:
        # Re-raise with more context about what failed
        error_msg = f"Failed to create embeddings for PDF '{filename}' ({len(valid_chunks)} chunks): {str(e)}"
        
        # Add specific error context
        error_str = str(e).lower()
        if "deploymentnotfound" in error_str or "deployment" in error_str:
            error_msg += " (Embedding deployment not found. Check AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME in .env)"
        elif "api" in error_str or "401" in error_str or "403" in error_str:
            error_msg += " (API authentication error. Check OPENAI_API_KEY and API permissions)"
        elif "429" in error_str or "rate limit" in error_str or "quota" in error_str:
            error_msg += " (Rate limit/quota exceeded. PDF may be too large or too many requests. Try processing fewer PDFs at once or wait before retrying)"
        elif "timeout" in error_str:
            error_msg += " (Request timeout. PDF may be too large. Check network connection or try again)"
        elif "too many" in error_str or "limit" in error_str:
            error_msg += " (PDF may be too large with too many chunks. Consider splitting the PDF or reducing chunk_size)"
        
        raise Exception(error_msg) from e
    


def delete_pdf(file_path):
    
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
        else:
            print(f"File not found: {file_path}")
    except Exception as e:
        print(f"Error deleting {file_path}: {str(e)}")


def processing_dc(file_path, embeddings, save_embeddings=False, delete_after=False):
    """
    Process PDF: load, chunk, and create embeddings.
    
    Args:
        file_path: Path to PDF file
        embeddings: Embeddings instance (must not be None)
        save_embeddings: Whether to save embeddings to disk
        delete_after: Whether to delete PDF after processing
        
    Returns:
        Tuple of (page_doc_list, doc_list, vectordb)
        
    Raises:
        Exception: If PDF loading, chunking, or embedding creation fails
    """
    # Validate embeddings before processing
    if embeddings is None:
        raise ValueError("Embeddings object is None. Check embedding deployment configuration in .env file.")
    
    # Chunk & Create Embeddings
    # data_load will raise an exception if it fails, which will be caught by the caller
    page_doc_list, doc_list = data_load(file_path, 'pdfplumber')
    
    # get_embeddings will raise an exception if it fails, which will be caught by the caller
    vectordb, em_dir_name = get_embeddings(file_path, doc_list, embeddings, save_embeddings=save_embeddings)
    
    # Optionally delete PDF (for Databricks/DBFS workflows)
    if delete_after:
        delete_pdf(file_path)

    return page_doc_list, doc_list, vectordb