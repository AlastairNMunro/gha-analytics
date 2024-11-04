import requests
import gzip
import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook

def _get_hwm(postgres_conn_id: str, **kwargs):
    postgres_hook = PostgresHook(postgres_conn_id=postgres_conn_id)
    
    select_query = f"SELECT max(hwm_value) FROM gh_analysis.raw_json_hwm"
    conn = postgres_hook.get_conn()
    cursor = conn.cursor()
    cursor.execute(select_query)
    result = cursor.fetchone()
    if result and result[0]:
        return result[0]
    else:
        return datetime(2024, 8, 1, 0, 0)
        
def _download_data(ti, url: str, **kwargs):
    
    hwm = ti.xcom_pull(task_ids='hwm_task')
    
    # Determine which file to download:
    next_timestamp = hwm + timedelta(hours=1)
    file_name = f'{next_timestamp.strftime('%Y-%m-%d-%-H')}.json.gz'
    full_url = f'{url}{file_name}'
    
    response = requests.get(full_url, stream=True)
    response.raise_for_status()  # Raise an error for bad status codes
    
    output_path = f'/tmp/{file_name}'

    # Write the compressed data to a file
    with open(output_path, 'wb') as f:
        f.write(response.content)
    
    # Unzip the file and return the file path of uncompressed data
    uncompressed_path = output_path.replace('.gz', '')
    with gzip.open(output_path, 'rb') as gz_in, open(uncompressed_path, 'wb') as f_out:
        f_out.write(gz_in.read())
    return uncompressed_path

def _load(file_path: str, postgres_conn_id: str, **kwargs):   
    postgres_hook = PostgresHook(postgres_conn_id=postgres_conn_id)

    with postgres_hook.get_conn() as conn:
        with conn.cursor() as cursor:
            with open(file_path, 'r+') as file:
                cursor.copy_expert(
                """
                COPY gh_analysis.raw_json (json_data) 
                FROM STDIN
                csv quote e'\x01' delimiter e'\x02'
                """,
                file
                )
                conn.commit()
    
    # Remove file to save disk space
    os.remove(file_path)
    os.remove(f'{file_path}.gz')
            
    return

def _update_high_watermark(ti):
        next_timestamp = ti.xcom_pull(task_ids='hwm_task') + timedelta(hours=1)
        
        postgres_hook = PostgresHook(postgres_conn_id='analytics_db')
        conn = postgres_hook.get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO gh_analysis.raw_json_hwm (hwm_value) VALUES (%s)",
            (next_timestamp,)
        )
        conn.commit()
    

with DAG(
    dag_id="load-gh-archive",
    start_date=datetime(2024, 8, 1),
    schedule=timedelta(seconds=120),
    catchup=False
) as dag:
    get_hwm_task = PythonOperator(
        task_id='hwm_task',
        python_callable=_get_hwm,
        op_kwargs={
            'table_name': 'raw_json',                             # Target table name in PostgreSQL
            'postgres_conn_id': 'analytics_db',                     # Connection ID for PostgreSQL
        }
    )
    
    download_task = PythonOperator(
        task_id='download_task',
        python_callable=_download_data,
        op_kwargs={
            'url': 'https://data.gharchive.org/'
        },
    )
    
    load_task = PythonOperator(task_id="load_task",
                               python_callable=_load,
                               op_kwargs={
            'file_path': "{{ ti.xcom_pull(task_ids='download_task') }}",
            'postgres_conn_id': 'analytics_db',                     # Connection ID for PostgreSQL
        })
    
    update_high_watermark_task = PythonOperator(
        task_id='update_high_watermark',
        python_callable=_update_high_watermark,
    )
    
get_hwm_task >> download_task >> load_task >> update_high_watermark_task