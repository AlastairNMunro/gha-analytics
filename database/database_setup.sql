CREATE DATABASE airflow_db;
CREATE USER airflow_user WITH PASSWORD 'airflow';
GRANT ALL PRIVILEGES ON DATABASE airflow_db TO airflow_user;
\c airflow_db;
GRANT ALL ON SCHEMA public TO airflow_user;
SET ROLE airflow_user;
CREATE SCHEMA gh_analysis;
create table gh_analysis.raw_json (
    load_dtm timestamp default current_timestamp,
    json_data json
);
create table gh_analysis.raw_json_hwm (
    load_dtm timestamp default current_timestamp,
    hwm_value timestamp
);
