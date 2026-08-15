import json

import pytest

from dagforge.config import Settings
from dagforge.models import Connector, GenerationRequest, PolicyPack, TaskKind
from dagforge.planner import DemoPlanner, OllamaPlanner, create_planner


def request(**updates: object) -> GenerationRequest:
    values = {
        "prompt": "Каждое утро получать заказы из API и сохранять их в базу данных",
        "source": Connector.REST_API,
        "destination": Connector.POSTGRESQL,
        "schedule": "0 6 * * *",
    }
    values.update(updates)
    return GenerationRequest(**values)


def test_demo_planner_builds_bound_configuration() -> None:
    spec = DemoPlanner().plan(request())
    assert spec.schedule == "0 6 * * *"
    assert spec.source == Connector.REST_API
    assert spec.destination == Connector.POSTGRESQL
    assert spec.catchup is False


def test_demo_planner_prefixes_dag_id_when_prompt_starts_with_digits() -> None:
    spec = DemoPlanner().plan(
        request(prompt="06:00 fetch REST API orders and load them into PostgreSQL every day")
    )

    assert spec.dag_id.startswith("dag_06_00_")


def test_demo_planner_adds_quality_and_notification_tasks() -> None:
    spec = DemoPlanner().plan(request())
    kinds = {task.kind for task in spec.tasks}
    assert TaskKind.QUALITY_CHECK in kinds
    assert TaskKind.NOTIFICATION in kinds


def test_demo_planner_respects_feature_toggles() -> None:
    spec = DemoPlanner().plan(request(include_quality_checks=False, include_notifications=False))
    kinds = {task.kind for task in spec.tasks}
    assert TaskKind.QUALITY_CHECK not in kinds
    assert TaskKind.NOTIFICATION not in kinds


def test_strict_policy_uses_retries_and_timeouts() -> None:
    spec = DemoPlanner().plan(request(policy_pack=PolicyPack.STRICT))
    assert all(task.timeout_minutes > 0 for task in spec.tasks)
    assert all(task.retries > 0 for task in spec.tasks)


def test_create_planner_selects_demo_and_ollama() -> None:
    demo = create_planner(Settings(_env_file=None, ai_provider="demo"))
    ollama = create_planner(Settings(_env_file=None, ai_provider="ollama", ollama_model="qwen3:4b"))

    assert isinstance(demo, DemoPlanner)
    assert isinstance(ollama, OllamaPlanner)
    assert ollama.model_name == "qwen3:4b"


def test_ollama_requires_a_model() -> None:
    with pytest.raises(ValueError, match="OLLAMA_MODEL"):
        create_planner(Settings(_env_file=None, ai_provider="ollama", ollama_model=None))


def test_ollama_uses_json_schema_and_binds_trusted_configuration(monkeypatch) -> None:
    user_request = request(
        owner="trusted-owner",
        source_connection_id="trusted_source",
        destination_connection_id="trusted_destination",
    )
    model_spec = DemoPlanner().plan(user_request)
    model_spec.schedule = "@once"
    model_spec.source = Connector.MYSQL
    model_spec.destination = Connector.S3
    model_spec.owner = "model-owner"
    for task in model_spec.tasks:
        task.connection_id = "model_supplied_secret"

    response_body = json.dumps(
        {"message": {"role": "assistant", "content": model_spec.model_dump_json()}}
    ).encode()
    captured: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self) -> bytes:
            return response_body

    def fake_urlopen(http_request, timeout):
        captured["url"] = http_request.full_url
        captured["payload"] = json.loads(http_request.data)
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("dagforge.planner.urllib.request.urlopen", fake_urlopen)
    planner = OllamaPlanner(
        Settings(
            _env_file=None,
            ai_provider="ollama",
            ollama_model="qwen3:4b",
            ollama_base_url="http://127.0.0.1:11434/",
        )
    )

    spec = planner.plan(user_request)

    assert captured["url"] == "http://127.0.0.1:11434/api/chat"
    assert captured["payload"]["format"]["title"] == "DagSpec"
    assert captured["payload"]["stream"] is False
    assert spec.schedule == user_request.schedule
    assert spec.source == user_request.source
    assert spec.destination == user_request.destination
    assert spec.owner == user_request.owner
    for task in spec.tasks:
        if task.kind == TaskKind.EXTRACT:
            assert task.connection_id == "trusted_source"
        elif task.kind == TaskKind.LOAD:
            assert task.connection_id == "trusted_destination"
        else:
            assert task.connection_id == ""
