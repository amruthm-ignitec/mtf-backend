import os
import pandas as pd
import json
from langchain.text_splitter import CharacterTextSplitter, RecursiveCharacterTextSplitter
from langchain.document_loaders import PyMuPDFLoader
from langchain_community.vectorstores import FAISS
# from langchain_core.documents import Document
from langchain_community.document_loaders import PDFMinerLoader
from langchain_community.document_loaders import PDFPlumberLoader
from langchain.schema import Document

def get_prompt_components(): 
    # This is the role for chunk extraction task
    with open("/root/script/Input_files/040924/role.json", 'r') as f:
        role = json.load(f)

    # This is the context for chunk extraction task
    with open("/root/script/Input_files/040924/context.json", 'r') as f:
        disease_context = json.load(f)

    # This is the instruction that goes into the prompt (LLM) using LLM API call
    with open("/root/script/Input_files/040924/instruction.json", 'r') as f:
        basic_instruction = json.load(f)

    # This is the reminder that goes into the prompt (LLM) using LLM API call
    with open("/root/script/Input_files/040924/reminder_instruction.json", 'r') as f:
        reminder_instructions = json.load(f)

    # This is the serology test name synonym dictionary
    with open("/root/script/Input_files/040924/new_serology_dictionary.json", 'r') as f:
        serology_dictionary = json.load(f)

    with open("/root/script/Input_files/040924/cat.json", 'r') as f:
        MS_MO_category_map = json.load(f)

    with open("/root/script/Input_files/040924/newMS.json", 'r') as f:
        subtissue_map = json.load(f)

    with open("/root/script/Input_files/Summary_topics.csv", 'r') as f:
        topic_df = pd.read_csv(f)

    with open("/root/script/Input_files/040924/t1_section_context.json", 'r') as file:
        t1_context = json.load(file)
    with open("/root/script/Input_files/040924/t1_tips.json", 'r') as file:
        t1_tips = json.load(file)
    with open("/root/script/Input_files/040924/t1_fewshot.json", 'r') as file:
        t1_fewshot = json.load(file)

    # T3 topics prompt components
    with open("/root/script/Input_files/040924/t3_context.json", 'r') as file:
        t3_context = json.load(file)
    with open("/root/script/Input_files/040924/t3_instruction.json", 'r') as file:
        t3_instruction = json.load(file)
    with open("/root/script/Input_files/040924/t3_fewshot.json", 'r') as file:
        t3_fewshot = json.load(file)

    return role, disease_context, basic_instruction, reminder_instructions, serology_dictionary, t1_context, t1_tips, t1_fewshot, topic_df, t3_context, t3_instruction, t3_fewshot, subtissue_map, MS_MO_category_map




def data_load(filename, parser_name):
    '''
    Loads data from PDF file and chunks it
    '''
    try:
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
        
        text_splitter = CharacterTextSplitter(
                separator = " ",
                chunk_size = 3000,
                chunk_overlap  = 250 
            )
        chunk_docs =  text_splitter.split_documents(page_docs)
        return page_docs, chunk_docs
    except Exception as e:
        print(f"An error occurred while loading your PDF: {e}")
        return None, None
    

def get_embeddings(filename, chunk_docs, embeddings):
    '''
    Creates embeddings and saves in DBFS
    '''
    try:
        vectordb = FAISS.from_documents(documents = chunk_docs, embedding = embeddings)
        em_dir_name = filename.split('/')[-1].replace('.pdf','').replace(' ','_')
        vectordb.save_local(f'Embeddings/{em_dir_name}')
        return vectordb, em_dir_name
    except Exception as e:
        print(f"An error occurred while embedding your PDF: {e}")
        return None, None
    


def delete_pdf(file_path):
    
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
        else:
            print(f"File not found: {file_path}")
    except Exception as e:
        print(f"Error deleting {file_path}: {str(e)}")


def processing_dc(dbfs_path, embeddings):

    # Chunk & Create Embeddings
    page_doc_list, doc_list = data_load(dbfs_path, 'pdfplumber')
    vectordb, em_dir_name = get_embeddings(dbfs_path, doc_list, embeddings)
    # Delete PDF from DBFS
    delete_pdf(dbfs_path)

    return page_doc_list, doc_list, vectordb