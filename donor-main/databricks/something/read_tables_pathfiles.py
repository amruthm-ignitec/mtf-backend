# Databricks notebook source
# MAGIC %pip install -r requirements.txt

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

from imports import *

# COMMAND ----------

connection_string, container_name = blob_connection()
(blob_service_client, container_client) = mount_blob(connection_string, container_name)
pdf_files = get_pdf_files(container_client, "QUEUE")
pdf_files

# COMMAND ----------

# MAGIC %md
# MAGIC ### Read tables

# COMMAND ----------

engine = create_engine("postgresql://donoraiadmin:qCg!zHz7MX%vN4RM@postgresdev-donorai-eus.postgres.database.azure.com:5432/postgres")

sql_query = "SELECT * FROM dc_data_prod;"
with engine.connect() as connection:
    df = pd.read_sql_query(text(sql_query), connection).round(1)

df.tail(14)

# COMMAND ----------

df['culture_results'][99]

# COMMAND ----------

sql_query = "SELECT * FROM dc_meta_prod;"
with engine.connect() as connection:
    df1 = pd.read_sql_query(text(sql_query), connection).round(1)

df1.tail(50)

# COMMAND ----------

sql_query = "SELECT * FROM dc_meta_prod where uid = '2414613_335611211206570';"
with engine.connect() as connection:
    df2 = pd.read_sql_query(text(sql_query), connection).round(1)

df2.tail(15)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Delete rows

# COMMAND ----------

# sql_query = "DELETE FROM dc_meta_prod where uid = '2323789_613';"
# with engine.connect() as connection:
#     with connection.begin():
#         result = connection.execute(text(sql_query))

#     rows_affected = result.rowcount
#     print(f"Rows affected: {rows_affected}")
