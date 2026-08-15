from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any

from dagforge.config import Settings
from dagforge.models import (
    DagSpec,
    GenerationRequest,
    PolicyPack,
    TaskKind,
    TaskParameter,
    TaskSpec,
)
from dagforge.prompts import PLANNER_SYSTEM_PROMPT, build_planner_input


def _slug(text: str) -> str:
    ascii_words = re.findall(r"[a-z0-9]+", text.lower())
    if ascii_words:
        value = "_".join(ascii_words[:6])
    else:
        value = "generated_pipeline"
    if value[0].isdigit():
        value = f"dag_{value}"
    suffix = hashlib.sha1(text.encode("utf-8")).hexdigest()[:6]
    return f"{value[:82]}_{suffix}"


class Planner(ABC):
    mode: str
    model_name: str | None

    @abstractmethod
    def plan(self, request: GenerationRequest) -> DagSpec:
        raise NotImplementedError


class DemoPlanner(Planner):
    """Deterministic planner used for local demos and tests without paid API calls."""

    mode = "demo"
    model_name = None

    def plan(self, request: GenerationRequest) -> DagSpec:
        retries = 1 if request.policy_pack == PolicyPack.BASIC else 2
        timeout = 45 if request.policy_pack == PolicyPack.STRICT else 30
        tasks: list[TaskSpec] = [
            TaskSpec(
                task_id="extract_source_data",
                title="Извлечение данных",
                kind=TaskKind.EXTRACT,
                description=(
                    f"Получить входные данные из {request.source.value} через Airflow Connection."
                ),
                retries=retries,
                timeout_minutes=timeout,
                connection_id=request.source_connection_id,
                parameters=[TaskParameter(key="connector", value=request.source.value)],
            )
        ]

        previous = "extract_source_data"
        if request.include_quality_checks:
            tasks.append(
                TaskSpec(
                    task_id="validate_source_data",
                    title="Контроль входных данных",
                    kind=TaskKind.QUALITY_CHECK,
                    description=(
                        "Проверить непустой результат, структуру и базовые ограничения качества."
                    ),
                    upstream_ids=[previous],
                    retries=retries,
                    timeout_minutes=15,
                    parameters=[TaskParameter(key="check_level", value=request.policy_pack.value)],
                )
            )
            previous = "validate_source_data"

        tasks.extend(
            [
                TaskSpec(
                    task_id="transform_data",
                    title="Преобразование",
                    kind=TaskKind.TRANSFORM,
                    description=(
                        "Применить описанные пользователем преобразования и нормализацию схемы."
                    ),
                    upstream_ids=[previous],
                    retries=retries,
                    timeout_minutes=timeout,
                ),
                TaskSpec(
                    task_id="load_destination",
                    title="Загрузка результата",
                    kind=TaskKind.LOAD,
                    description=f"Идемпотентно загрузить результат в {request.destination.value}.",
                    upstream_ids=["transform_data"],
                    retries=retries,
                    timeout_minutes=timeout,
                    connection_id=request.destination_connection_id,
                    parameters=[TaskParameter(key="write_mode", value="upsert")],
                ),
                TaskSpec(
                    task_id="audit_delivery",
                    title="Аудит доставки",
                    kind=TaskKind.AUDIT,
                    description="Зафиксировать количество записей и итоговый статус запуска.",
                    upstream_ids=["load_destination"],
                    retries=retries,
                    timeout_minutes=10,
                ),
            ]
        )

        if request.include_notifications:
            tasks.append(
                TaskSpec(
                    task_id="notify_owner",
                    title="Уведомление владельца",
                    kind=TaskKind.NOTIFICATION,
                    description=(
                        "Отправить итог выполнения владельцу конвейера через настроенный канал."
                    ),
                    upstream_ids=["audit_delivery"],
                    retries=1,
                    timeout_minutes=5,
                    parameters=[TaskParameter(key="channel", value="airflow_notifier")],
                )
            )

        return DagSpec(
            dag_id=_slug(request.prompt),
            display_name="AI-generated data pipeline",
            description=request.prompt[:900],
            schedule=request.schedule,
            owner=request.owner,
            catchup=False,
            max_active_runs=1,
            tags=["dagforge", request.source.value, request.destination.value],
            source=request.source,
            destination=request.destination,
            tasks=tasks,
            assumptions=[
                "Имена Airflow Connections существуют в целевом окружении.",
                "Конкретные операции адаптеров уточняются перед production-развёртыванием.",
            ],
        )


class OpenAIPlanner(Planner):
    mode = "openai"

    def __init__(self, settings: Settings):
        from openai import OpenAI

        self.model_name = settings.openai_model
        self._client = OpenAI(api_key=settings.openai_api_key)

    def plan(self, request: GenerationRequest) -> DagSpec:
        response = self._client.responses.parse(
            model=self.model_name,
            input=[
                {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": build_planner_input(request.model_dump(mode="json")),
                },
            ],
            text_format=DagSpec,
        )
        if response.output_parsed is None:
            raise RuntimeError("The model did not return a DAG specification")
        return _bind_request_configuration(response.output_parsed, request)


class OllamaPlanner(Planner):
    """Local planner using Ollama's JSON-schema structured output API."""

    mode = "ollama"

    def __init__(self, settings: Settings):
        if not settings.ollama_model or not settings.ollama_model.strip():
            raise ValueError("OLLAMA_MODEL must be set when AI_PROVIDER=ollama")
        self.model_name = settings.ollama_model.strip()
        self._base_url = settings.ollama_base_url.rstrip("/")
        self._timeout = settings.ollama_timeout_seconds

    def plan(self, request: GenerationRequest) -> DagSpec:
        schema = DagSpec.model_json_schema()
        prompt = build_planner_input(request.model_dump(mode="json"))
        prompt += "\n\nReturn only JSON matching this schema:\n" + json.dumps(schema)
        payload = {
            "model": self.model_name,
            "stream": False,
            "think": False,
            "messages": [
                {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "format": schema,
            "options": {"temperature": 0},
        }
        http_request = urllib.request.Request(
            f"{self._base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(http_request, timeout=self._timeout) as response:
                body: dict[str, Any] = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Ollama returned HTTP {exc.code}: {detail[:500]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Cannot connect to Ollama at {self._base_url}. Is `ollama serve` running?"
            ) from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Ollama returned an invalid JSON response") from exc

        content = body.get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("Ollama did not return a DAG specification")
        try:
            spec = DagSpec.model_validate_json(content)
        except ValueError as exc:
            raise RuntimeError(f"Ollama returned an invalid DAG specification: {exc}") from exc
        return _bind_request_configuration(spec, request)


def _bind_request_configuration(spec: DagSpec, request: GenerationRequest) -> DagSpec:
    """Override model-controlled values that belong to the trusted user configuration."""

    spec.schedule = request.schedule
    spec.source = request.source
    spec.destination = request.destination
    spec.owner = request.owner
    spec.catchup = False
    for task in spec.tasks:
        if task.kind == TaskKind.EXTRACT:
            task.connection_id = request.source_connection_id
        elif task.kind == TaskKind.LOAD:
            task.connection_id = request.destination_connection_id
        else:
            task.connection_id = ""
    return DagSpec.model_validate(spec.model_dump())


def create_planner(settings: Settings) -> Planner:
    provider = settings.resolved_provider
    if provider == "openai":
        if not settings.openai_api_key or not settings.openai_api_key.strip():
            raise ValueError("OPENAI_API_KEY must be set when AI_PROVIDER=openai")
        return OpenAIPlanner(settings)
    if provider == "ollama":
        return OllamaPlanner(settings)
    return DemoPlanner()
