from __future__ import annotations

import argparse
import sys
from pathlib import Path

from airflow.dag_processing.dagbag import DagBag


def fail(message: str) -> None:
    print(f"AIRFLOW_CHECK_FAILED: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a generated DAG through Airflow DagBag")
    parser.add_argument("dag_file", type=Path)
    parser.add_argument("dag_id")
    args = parser.parse_args()

    dag_bag = DagBag(
        dag_folder=str(args.dag_file),
        safe_mode=False,
    )
    if dag_bag.import_errors:
        errors = "\n".join(f"{path}: {error}" for path, error in dag_bag.import_errors.items())
        fail(f"Airflow could not import the generated file:\n{errors}")

    dag = dag_bag.dags.get(args.dag_id)
    if dag is None:
        fail(f"DAG {args.dag_id!r} was not discovered; found {sorted(dag_bag.dags)}")

    expected_upstreams = {
        "extract_orders": set(),
        "transform_orders": {"extract_orders"},
        "load_orders": {"transform_orders"},
    }
    actual_task_ids = set(dag.task_ids)
    if actual_task_ids != set(expected_upstreams):
        fail(f"unexpected tasks: {sorted(actual_task_ids)}")

    for task_id, expected in expected_upstreams.items():
        actual = dag.get_task(task_id).upstream_task_ids
        if actual != expected:
            fail(f"{task_id} upstream IDs are {sorted(actual)}, expected {sorted(expected)}")

    dag.validate()
    print(
        f"DAGBAG_OK dag_id={dag.dag_id} tasks={len(dag.tasks)} "
        f"edges={sum(len(task.upstream_task_ids) for task in dag.tasks)}"
    )


if __name__ == "__main__":
    main()
