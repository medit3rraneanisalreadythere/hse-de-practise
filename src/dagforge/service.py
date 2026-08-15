from __future__ import annotations

from dagforge.config import Settings, get_settings
from dagforge.models import AirflowPublishResult, DagSpec, GenerationRequest, GenerationResult
from dagforge.planner import Planner, create_planner
from dagforge.renderer import render_airflow_dag
from dagforge.validator import DagCodeValidator


class DagGenerationService:
    def __init__(
        self,
        settings: Settings | None = None,
        planner: Planner | None = None,
        validator: DagCodeValidator | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.planner = planner or create_planner(self.settings)
        self.validator = validator or DagCodeValidator()

    def generate(self, request: GenerationRequest) -> GenerationResult:
        spec = self.planner.plan(request)
        code = render_airflow_dag(spec)
        validation = self.validator.validate(code)
        notes = [
            "LLM формирует только типизированный план; Python создаётся доверенным renderer-ом.",
            "Секреты не включаются в файл: используются идентификаторы Airflow Connections.",
            (
                "Задачи реализуют исполняемый contract scaffold; подключите корпоративные "
                "адаптеры перед production."
            ),
        ]
        if self.planner.mode == "demo":
            notes.insert(
                0,
                "Использован детерминированный demo-планировщик: AI-провайдер не настроен.",
            )
        elif self.planner.mode == "ollama":
            notes.insert(
                0,
                f"План построен локальной моделью Ollama: {self.planner.model_name}.",
            )
        return GenerationResult(
            mode=self.planner.mode,
            model=self.planner.model_name,
            spec=spec,
            code=code,
            validation=validation,
            generation_notes=notes,
        )

    def publish_to_airflow(self, spec: DagSpec) -> AirflowPublishResult:
        code = render_airflow_dag(spec)
        validation = self.validator.validate(code)
        if not validation.passed:
            raise ValueError("rendered DAG did not pass validation")

        dags_dir = self.settings.airflow_dags_dir
        dags_dir.mkdir(parents=True, exist_ok=True)
        target = dags_dir / f"{spec.dag_id}.py"
        temporary = dags_dir / f".{spec.dag_id}.py.tmp"
        temporary.write_text(code, encoding="utf-8")
        temporary.replace(target)

        return AirflowPublishResult(
            dag_id=spec.dag_id,
            filename=target.name,
            airflow_url=self.settings.airflow_ui_url,
        )
