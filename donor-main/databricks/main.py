# Databricks notebook source
# MAGIC %pip install -r requirements.txt

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

from imports import *

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
