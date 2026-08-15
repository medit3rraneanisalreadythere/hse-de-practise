import ast

from dagforge.renderer import render_airflow_dag
from scripts.export_airflow_fixture import DAG_ID, build_smoke_spec


def test_airflow_smoke_fixture_is_stable_and_renderable() -> None:
    spec = build_smoke_spec()
    code = render_airflow_dag(spec)

    assert spec.dag_id == DAG_ID
    assert [task.task_id for task in spec.tasks] == [
        "extract_orders",
        "transform_orders",
        "load_orders",
    ]
    assert spec.tasks[1].upstream_ids == ["extract_orders"]
    assert spec.tasks[2].upstream_ids == ["transform_orders"]
    assert isinstance(ast.parse(code), ast.Module)
