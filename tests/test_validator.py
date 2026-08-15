from dagforge.models import Severity
from dagforge.validator import DagCodeValidator

GOOD_DAG = """
from datetime import timedelta
from airflow.sdk import DAG, task
with DAG(dag_id="safe", catchup=False) as dag:
    @task(retries=2, execution_timeout=timedelta(minutes=5))
    def work():
        return 1
    work()
"""


def test_good_dag_passes_with_full_score() -> None:
    result = DagCodeValidator().validate(GOOD_DAG)
    assert result.passed
    assert result.score == 100
    assert result.findings == []


def test_syntax_error_fails_validation() -> None:
    result = DagCodeValidator().validate("def broken(:\n")
    assert not result.passed
    assert any(item.rule_id == "python.syntax" for item in result.findings)


def test_hardcoded_secret_is_rejected() -> None:
    result = DagCodeValidator().validate(GOOD_DAG + '\napi_key = "this-is-a-real-looking-secret"')
    assert not result.passed
    assert any(item.severity == Severity.ERROR for item in result.findings)


def test_dangerous_eval_is_rejected() -> None:
    result = DagCodeValidator().validate(GOOD_DAG + '\neval("2 + 2")')
    assert not result.passed
    assert any(item.rule_id == "security.dangerous_call" for item in result.findings)


def test_dynamic_start_date_is_reported() -> None:
    result = DagCodeValidator().validate(GOOD_DAG + "\nvalue = datetime.now()")
    assert any(item.rule_id == "airflow.dynamic_start_date" for item in result.findings)
