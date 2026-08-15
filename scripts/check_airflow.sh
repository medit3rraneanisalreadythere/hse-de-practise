#!/usr/bin/env bash
set -Eeuo pipefail

readonly DAG_ID="dagforge_airflow_smoke"
readonly DAG_FILE="${AIRFLOW_HOME}/dags/${DAG_ID}.py"

mkdir -p "${AIRFLOW_HOME}/dags" "${AIRFLOW_HOME}/logs"

python /opt/dagforge/scripts/export_airflow_fixture.py "${DAG_FILE}"
airflow db migrate
python /opt/dagforge/scripts/airflow_dagbag_check.py "${DAG_FILE}" "${DAG_ID}"
airflow dags test "${DAG_ID}" "2026-01-02T00:00:00+00:00" --dagfile-path "${DAG_FILE}"

echo "AIRFLOW_SMOKE_OK dag_id=${DAG_ID}"
