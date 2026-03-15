"""
ETL: данные из CRM и телеметрии собираются в витрину report_mart в OLAP.
Расписание: каждый день в 02:00.
"""
from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.providers.postgres.operators.postgres import PostgresOperator

default_args = {
    "owner": "airflow",
    "start_date": datetime(2024, 12, 1),
}


def get_report_period(**context):
    """Период: вчера и 30 дней назад."""
    ds = context.get("logical_date") or context.get("execution_date") or datetime.utcnow()
    if hasattr(ds, "date"):
        period_to = (ds - timedelta(days=1)).date()
    else:
        period_to = ds - timedelta(days=1)
    period_from = period_to - timedelta(days=30)
    return period_from, period_to


def extract_crm(**context):
    """Читаем справочник клиентов из crm_clients."""
    ti = context["ti"]
    hook = PostgresHook(postgres_conn_id="olap")
    conn = hook.get_conn()
    cur = conn.cursor()
    cur.execute("SELECT user_id, full_name, email FROM crm_clients")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    ti.xcom_push(key="crm_data", value=[{"user_id": r[0], "full_name": r[1], "email": r[2]} for r in rows])
    return len(rows)


def extract_telemetry(**context):
    """Суммируем телеметрию по пользователям за выбранный период."""
    period_from, period_to = get_report_period(**context)
    ti = context["ti"]
    hook = PostgresHook(postgres_conn_id="olap")
    conn = hook.get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT user_id,
               SUM(usage_mins) AS total_usage_mins,
               SUM(events) AS total_events
        FROM telemetry_raw
        WHERE ts >= %s AND ts < %s + interval '1 day'
        GROUP BY user_id
    """,
        (period_from, period_to),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    ti.xcom_push(
        key="telemetry_data",
        value=[{"user_id": r[0], "total_usage_mins": r[1], "total_events": r[2]} for r in rows],
    )
    return len(rows)


def generate_load_sql(**context):
    """Склеиваем CRM и телеметрию по user_id, пишем INSERT-ы в sql-файл."""
    ti = context["ti"]
    crm = ti.xcom_pull(task_ids="extract_crm", key="crm_data") or []
    telemetry = ti.xcom_pull(task_ids="extract_telemetry", key="telemetry_data") or []
    period_from, period_to = get_report_period(**context)
    tel_by_user = {t["user_id"]: t for t in telemetry}

    sql_dir = Path("/opt/airflow/dags/sql")
    sql_dir.mkdir(parents=True, exist_ok=True)
    sql_file = sql_dir / "load_report_mart.sql"

    lines = []
    for c in crm:
        uid = c["user_id"]
        tel = tel_by_user.get(uid, {"total_usage_mins": 0, "total_events": 0})
        fn = (c.get("full_name") or "").replace("'", "''")
        em = (c.get("email") or "").replace("'", "''")
        lines.append(
            f"INSERT INTO report_mart (user_id, period_from, period_to, full_name, email, total_usage_mins, total_events, updated_at) "
            f"VALUES ('{uid}', '{period_from}', '{period_to}', '{fn}', '{em}', {tel['total_usage_mins']}, {tel['total_events']}, CURRENT_TIMESTAMP) "
            f"ON CONFLICT (user_id, period_from, period_to) "
            f"DO UPDATE SET full_name = EXCLUDED.full_name, email = EXCLUDED.email, "
            f"total_usage_mins = EXCLUDED.total_usage_mins, total_events = EXCLUDED.total_events, updated_at = CURRENT_TIMESTAMP;"
        )

    sql_file.write_text("\n".join(lines), encoding="utf-8")
    return len(lines)


with DAG(
    dag_id="reports_etl",
    default_args=default_args,
    schedule_interval="0 2 * * *",
    catchup=False,
    tags=["reports", "etl"],
) as dag:
    extract_crm_task = PythonOperator(task_id="extract_crm", python_callable=extract_crm)
    extract_telemetry_task = PythonOperator(task_id="extract_telemetry", python_callable=extract_telemetry)
    generate_load_sql_task = PythonOperator(task_id="generate_load_sql", python_callable=generate_load_sql)
    run_load_sql = PostgresOperator(
        task_id="run_load_sql",
        postgres_conn_id="olap",
        sql="sql/load_report_mart.sql",
    )

    extract_crm_task >> extract_telemetry_task >> generate_load_sql_task >> run_load_sql
