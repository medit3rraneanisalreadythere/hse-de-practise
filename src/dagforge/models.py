from __future__ import annotations

import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class Connector(StrEnum):
    REST_API = "rest_api"
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    S3 = "s3"
    LOCAL_FILE = "local_file"
    BIGQUERY = "bigquery"
    SNOWFLAKE = "snowflake"


class TaskKind(StrEnum):
    EXTRACT = "extract"
    QUALITY_CHECK = "quality_check"
    TRANSFORM = "transform"
    LOAD = "load"
    AUDIT = "audit"
    NOTIFICATION = "notification"


class PolicyPack(StrEnum):
    BASIC = "basic"
    PRODUCTION = "production"
    STRICT = "strict"


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class TaskParameter(BaseModel):
    key: str = Field(min_length=1, max_length=60, pattern=r"^[a-z][a-z0-9_]*$")
    value: str = Field(max_length=500)


class TaskSpec(BaseModel):
    task_id: str = Field(min_length=2, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    title: str = Field(min_length=2, max_length=100)
    kind: TaskKind
    description: str = Field(min_length=5, max_length=500)
    upstream_ids: list[str] = Field(default_factory=list, max_length=12)
    retries: int = Field(default=2, ge=0, le=10)
    timeout_minutes: int = Field(default=30, ge=1, le=720)
    connection_id: str = Field(default="", max_length=100)
    parameters: list[TaskParameter] = Field(default_factory=list, max_length=12)


class DagSpec(BaseModel):
    dag_id: str = Field(min_length=3, max_length=100, pattern=r"^[a-z][a-z0-9_]*$")
    display_name: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=10, max_length=1000)
    schedule: str = Field(min_length=1, max_length=100)
    owner: str = Field(default="data-platform", min_length=2, max_length=80)
    catchup: bool = False
    max_active_runs: int = Field(default=1, ge=1, le=20)
    tags: list[str] = Field(default_factory=list, max_length=10)
    source: Connector
    destination: Connector
    tasks: list[TaskSpec] = Field(min_length=2, max_length=24)
    assumptions: list[str] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def validate_graph(self) -> DagSpec:
        task_ids = [task.task_id for task in self.tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("task_id values must be unique")

        known = set(task_ids)
        for task in self.tasks:
            unknown = set(task.upstream_ids) - known
            if unknown:
                raise ValueError(f"unknown upstream task(s) for {task.task_id}: {sorted(unknown)}")
            if task.task_id in task.upstream_ids:
                raise ValueError(f"task {task.task_id} cannot depend on itself")

        graph = {task.task_id: task.upstream_ids for task in self.tasks}
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> None:
            if node in visiting:
                raise ValueError("task graph contains a cycle")
            if node in visited:
                return
            visiting.add(node)
            for parent in graph[node]:
                visit(parent)
            visiting.remove(node)
            visited.add(node)

        for task_id in task_ids:
            visit(task_id)
        return self


class GenerationRequest(BaseModel):
    prompt: str = Field(min_length=15, max_length=5000)
    source: Connector = Connector.REST_API
    destination: Connector = Connector.POSTGRESQL
    schedule: str = Field(default="0 6 * * *", min_length=1, max_length=100)
    source_connection_id: str = Field(default="source_default", max_length=100)
    destination_connection_id: str = Field(default="destination_default", max_length=100)
    owner: str = Field(default="data-platform", min_length=2, max_length=80)
    policy_pack: PolicyPack = PolicyPack.PRODUCTION
    include_quality_checks: bool = True
    include_notifications: bool = True

    @model_validator(mode="after")
    def normalize(self) -> GenerationRequest:
        self.prompt = self.prompt.strip()
        self.owner = self.owner.strip()
        for value, name in (
            (self.source_connection_id, "source_connection_id"),
            (self.destination_connection_id, "destination_connection_id"),
        ):
            if value and not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]*", value):
                raise ValueError(f"{name} contains unsupported characters")
        return self


class ValidationFinding(BaseModel):
    rule_id: str
    severity: Severity
    title: str
    message: str
    line: int | None = None


class ValidationReport(BaseModel):
    passed: bool
    score: int = Field(ge=0, le=100)
    findings: list[ValidationFinding]
    checks_run: int = Field(ge=0)


class GenerationResult(BaseModel):
    mode: str
    model: str | None
    spec: DagSpec
    code: str
    validation: ValidationReport
    generation_notes: list[str]


class AirflowPublishRequest(BaseModel):
    spec: DagSpec


class AirflowPublishResult(BaseModel):
    dag_id: str
    filename: str
    airflow_url: str


class CodeValidationRequest(BaseModel):
    code: str = Field(min_length=1, max_length=200_000)


class ExamplePrompt(BaseModel):
    title: str
    prompt: str
    source: Connector
    destination: Connector
    schedule: str


JsonDict = dict[str, Any]
