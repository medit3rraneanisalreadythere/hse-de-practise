from dagforge.api import examples, generate, health, publish_to_airflow, router, validate_code
from dagforge.config import Settings
from dagforge.models import AirflowPublishRequest, CodeValidationRequest, GenerationRequest
from dagforge.service import DagGenerationService

demo_settings = Settings(_env_file=None, ai_provider="demo")
demo_service = DagGenerationService(settings=demo_settings)


def test_health_endpoint() -> None:
    response = health(demo_settings)
    assert response["status"] == "ok"
    assert response["mode"] == "demo"
    assert response["model"] is None


def test_examples_endpoint() -> None:
    assert len(examples()) >= 3


def test_generate_endpoint_in_demo_mode() -> None:
    response = generate(
        GenerationRequest(
            prompt="Каждый день получать заказы из REST API и загружать их в PostgreSQL"
        ),
        demo_service,
    )
    assert response.mode == "demo"
    assert response.validation.passed is True
    assert "from airflow.sdk import DAG" in response.code


def test_publish_endpoint_writes_rendered_dag(tmp_path) -> None:
    settings = Settings(_env_file=None, ai_provider="demo", airflow_dags_dir=tmp_path)
    service = DagGenerationService(settings=settings)
    generated = service.generate(
        GenerationRequest(
            prompt="Каждый день получать заказы из REST API и загружать их в PostgreSQL"
        )
    )

    published = publish_to_airflow(AirflowPublishRequest(spec=generated.spec), service)

    dag_file = tmp_path / published.filename
    assert published.dag_id == generated.spec.dag_id
    assert dag_file.is_file()
    assert dag_file.read_text(encoding="utf-8") == generated.code


def test_validate_endpoint() -> None:
    response = validate_code(CodeValidationRequest(code="eval('bad')"))
    assert response.passed is False


def test_expected_api_routes_are_registered() -> None:
    paths = {route.path for route in router.routes}
    assert {
        "/api/health",
        "/api/examples",
        "/api/generate",
        "/api/airflow/publish",
        "/api/validate",
    } <= paths
