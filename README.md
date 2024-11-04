# Initial Setup
Install helm, kubectl and minikube

# Database
## Install Postgres
helm install analytics-postgresql bitnami/postgresql --version 16.1.0 -n database -f ./database/values.yaml

## Set up metadata database and user
export POSTGRES_PASSWORD=$(kubectl get secret --namespace database analytics-postgresql -o jsonpath="{.data.postgres-password}" | base64 -d)

kubectl run analytics-postgresql-client --rm --tty -i --restart='Never' --namespace database --image docker.io/bitnami/postgresql:17.0.0-debian-12-r9 --env="PGPASSWORD=$POSTGRES_ADMIN_PASSWORD" \
      --command -- psql --host analytics-postgresql -U postgres -d postgres -p 5432

CREATE DATABASE airflow_db;
CREATE USER airflow_user WITH PASSWORD 'airflow';
GRANT ALL PRIVILEGES ON DATABASE airflow_db TO airflow_user;
\c airflow_db;
GRANT ALL ON SCHEMA public TO airflow_user;

# Airflow
kubectl create namespace airflow

## Create configmap for DAGs
kubectl create configmap airflow-dags --from-file=./airflow/dags/ -n airflow
kubectl delete configmap airflow-dags -n airflow

## Install Airflow
helm install analytics-airflow bitnami/airflow --version 20.0.0 --namespace airflow -f ./airflow/values.yaml

## Upgrade Airflow
helm upgrade analytics-airflow bitnami/airflow -f ./airflow/values.yaml -n airflow

## Forward port
kubectl port-forward --namespace airflow svc/analytics-airflow 8080:8080 &
    echo "Airflow URL: http://127.0.0.1:8080"

export AIRFLOW_PASSWORD=$(kubectl get secret --namespace "airflow" analytics-airflow -o jsonpath="{.data.airflow-password}" | base64 -d)
    echo User:     user
    echo Password: $AIRFLOW_PASSWORD

# Prometheus & Grafana

helm install analytics-prometheus prometheus-community/prometheus --version 25.28.0 -n monitoring -f ./prometheus/values.yaml

helm install analytics-grafana grafana/grafana -n monitoring -f ./grafana/values.yaml

helm install kube-state-metrics prometheus-community/kube-state-metrics -n kube-system


## Forward prometheus port
export POD_NAME=$(kubectl get pods --namespace monitoring -l "app.kubernetes.io/name=prometheus,app.kubernetes.io/instance=analytics-prometheus" -o jsonpath="{.items[0].metadata.name}")
  kubectl --namespace monitoring port-forward $POD_NAME 9090

## Forward grafana port
export POD_NAME=$(kubectl get pods --namespace monitoring -l "app.kubernetes.io/name=grafana,app.kubernetes.io/instance=analytics-grafana" -o jsonpath="{.items[0].metadata.name}")
     kubectl --namespace monitoring port-forward $POD_NAME 3000
