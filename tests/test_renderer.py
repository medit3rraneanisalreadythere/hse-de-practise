import ast

from dagforge.models import Connector, DagSpec, GenerationRequest, TaskKind, TaskSpec
from dagforge.planner import DemoPlanner
from dagforge.renderer import render_airflow_dag


def generated_code() -> str:
    request = GenerationRequest(
        prompt="Забирать новые заказы из API и сохранять в PostgreSQL каждый день"
    )
    return render_airflow_dag(DemoPlanner().plan(request))


def test_rendered_code_is_valid_python() -> None:
    tree = ast.parse(generated_code())
    assert isinstance(tree, ast.Module)


def test_rendered_code_uses_airflow_3_public_sdk() -> None:
    code = generated_code()
    assert "from airflow.sdk import DAG" in code
    assert "is_paused_upon_creation=False" in code
    assert "catchup=False" in code
    assert 'context.get("logical_date")' in code


def test_rendered_code_contains_all_dependencies() -> None:
    code = generated_code()
    assert "extract_source_data_result >> validate_source_data_result" in code
    assert "transform_data_result >> load_destination_result" in code


def test_user_prompt_is_encoded_as_literal() -> None:
    request = GenerationRequest(
        prompt="Обработать данные с текстом: __import__('os').system('bad')"
    )
    code = render_airflow_dag(DemoPlanner().plan(request))
    tree = ast.parse(code)
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    assert not any(
        isinstance(node.func, ast.Name) and node.func.id == "__import__" for node in calls
    )


def test_task_description_cannot_escape_generated_function() -> None:
    spec = DagSpec(
        dag_id="safe_pipeline",
        display_name="Safe pipeline",
        description="A sufficiently detailed safe pipeline description",
        schedule="@daily",
        source=Connector.REST_API,
        destination=Connector.POSTGRESQL,
        tasks=[
            TaskSpec(
                task_id="extract",
                title="Extract",
                kind=TaskKind.EXTRACT,
                description='"""; __import__("os").system("bad")',
            ),
            TaskSpec(
                task_id="load",
                title="Load",
                kind=TaskKind.LOAD,
                description="Load data safely",
                upstream_ids=["extract"],
            ),
        ],
    )
    tree = ast.parse(render_airflow_dag(spec))
    import_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "__import__"
    ]
    assert import_calls == []
