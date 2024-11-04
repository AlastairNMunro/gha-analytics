import requests
import gzip
import json
from datetime import datetime

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook

def _download_data(url: str, output_path: str, **kwargs):
    response = requests.get(url, stream=True)
    response.raise_for_status()  # Raise an error for bad status codes

    # Write the compressed data to a file
    with open(output_path, 'wb') as f:
        f.write(response.content)
    
    # Unzip the file and return the file path of uncompressed data
    uncompressed_path = output_path.replace('.gz', '')
    with gzip.open(output_path, 'rb') as gz_in, open(uncompressed_path, 'wb') as f_out:
        f_out.write(gz_in.read())
    return uncompressed_path

def _load(file_path: str, table_name: str, postgres_conn_id: str, batch_size: int = 1000, **kwargs):   
    postgres_hook = PostgresHook(postgres_conn_id=postgres_conn_id)

    with open(file_path, 'r', encoding='utf-8') as f:
        records = [json.loads(line) for line in f]  # Assuming JSON lines format for large files

    # Prepare SQL insert statement
    keys = records[0].keys()
    insert_query = f"INSERT INTO {table_name} ({', '.join(keys)}) VALUES ({', '.join(['%s'] * len(keys))})"

    # Insert in batches to optimize memory and performance
    with postgres_hook.get_conn() as conn:
        with conn.cursor() as cursor:
            for i in range(0, len(records), batch_size):
                batch = records[i:i+batch_size]
                cursor.executemany(insert_query, [tuple(record.values()) for record in batch])
            conn.commit()
            
    return


with DAG(
    dag_id="download-gh-archive",
    start_date=datetime(2025, 11, 1),
    schedule="@daily",
) as dag:
    download_task = PythonOperator(
        task_id='download_task',
        python_callable=_download_data,
        op_kwargs={
            'url': 'https://data.gharchive.org/2015-01-01-15.json.gz',  # URL of the compressed JSON file
            'output_path': '/tmp/downloaded_file.json.gz',         # Temporary storage for the downloaded file
        },
    )
    
    load_task = PythonOperator(task_id="load_task",
                               python_callable=_load,
                               op_kwargs={
            'file_path': "{{ ti.xcom_pull(task_ids='download_task') }}",
            'table_name': 'raw_json',                             # Target table name in PostgreSQL
            'postgres_conn_id': 'riverty_db',                     # Connection ID for PostgreSQL
            'batch_size': 1000,                                   # Number of records to insert per batch
        })
    
download_task >> load_task