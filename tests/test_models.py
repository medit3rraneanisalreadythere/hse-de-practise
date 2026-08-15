import pytest
from pydantic import ValidationError

from dagforge.models import Connector, DagSpec, TaskKind, TaskSpec


def make_spec(tasks: list[TaskSpec]) -> DagSpec:
    return DagSpec(
        dag_id="orders_pipeline",
        display_name="Orders pipeline",
        description="A sufficiently detailed pipeline description",
        schedule="0 6 * * *",
        source=Connector.REST_API,
        destination=Connector.POSTGRESQL,
        tasks=tasks,
    )


def test_valid_graph_is_accepted() -> None:
    spec = make_spec(
        [
            TaskSpec(
                task_id="extract",
                title="Extract",
                kind=TaskKind.EXTRACT,
                description="Extract data",
            ),
            TaskSpec(
                task_id="load",
                title="Load",
                kind=TaskKind.LOAD,
                description="Load data",
                upstream_ids=["extract"],
            ),
        ]
    )
    assert spec.tasks[1].upstream_ids == ["extract"]


def test_unknown_dependency_is_rejected() -> None:
    with pytest.raises(ValidationError, match="unknown upstream"):
        make_spec(
            [
                TaskSpec(
                    task_id="extract",
                    title="Extract",
                    kind=TaskKind.EXTRACT,
                    description="Extract data",
                    upstream_ids=["missing"],
                ),
                TaskSpec(task_id="load", title="Load", kind=TaskKind.LOAD, description="Load data"),
            ]
        )


def test_cycle_is_rejected() -> None:
    with pytest.raises(ValidationError, match="cycle"):
        make_spec(
            [
                TaskSpec(
                    task_id="extract",
                    title="Extract",
                    kind=TaskKind.EXTRACT,
                    description="Extract data",
                    upstream_ids=["load"],
                ),
                TaskSpec(
                    task_id="load",
                    title="Load",
                    kind=TaskKind.LOAD,
                    description="Load data",
                    upstream_ids=["extract"],
                ),
            ]
        )


def test_duplicate_task_id_is_rejected() -> None:
    task = TaskSpec(
        task_id="extract", title="Extract", kind=TaskKind.EXTRACT, description="Extract data"
    )
    with pytest.raises(ValidationError, match="unique"):
        make_spec([task, task.model_copy()])
