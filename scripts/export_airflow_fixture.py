from __future__ import annotations

import argparse
from pathlib import Path

from dagforge.models import Connector, DagSpec, TaskKind, TaskParameter, TaskSpec
from dagforge.renderer import render_airflow_dag

DAG_ID = "dagforge_airflow_smoke"


def build_smoke_spec() -> DagSpec:
    """Build a stable fixture that exercises rendering and task dependencies in Airflow."""

    return DagSpec(
        dag_id=DAG_ID,
        display_name="DAG Forge Airflow smoke test",
        description="Executable fixture used to verify DAG Forge output in Apache Airflow.",
        schedule="0 6 * * *",
        owner="dagforge-test",
        catchup=False,
        max_active_runs=1,
        tags=["dagforge", "integration-test"],
        source=Connector.REST_API,
        destination=Connector.POSTGRESQL,
        tasks=[
            TaskSpec(
                task_id="extract_orders",
                title="Extract orders",
                kind=TaskKind.EXTRACT,
                description="Read a structured order batch through the source connection.",
                retries=1,
                timeout_minutes=5,
                connection_id="orders_api",
                parameters=[TaskParameter(key="connector", value="rest_api")],
            ),
            TaskSpec(
                task_id="transform_orders",
                title="Transform orders",
                kind=TaskKind.TRANSFORM,
                description="Normalize order dates and monetary values for delivery.",
                upstream_ids=["extract_orders"],
                retries=1,
                timeout_minutes=5,
            ),
            TaskSpec(
                task_id="load_orders",
                title="Load orders",
                kind=TaskKind.LOAD,
                description="Publish the normalized order batch to the destination.",
                upstream_ids=["transform_orders"],
                retries=1,
                timeout_minutes=5,
                connection_id="warehouse_postgres",
                parameters=[TaskParameter(key="write_mode", value="upsert")],
            ),
        ],
        assumptions=["Integration tasks emit contract events and do not access external systems."],
    )


def export_fixture(output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_airflow_dag(build_smoke_spec()), encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a stable DAG Forge Airflow fixture")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = export_fixture(args.output)
    print(f"Exported {DAG_ID} to {output}")


if __name__ == "__main__":
    main()
