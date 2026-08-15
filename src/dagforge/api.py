from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from dagforge import __version__
from dagforge.config import Settings, get_settings
from dagforge.examples import EXAMPLES
from dagforge.models import (
    AirflowPublishRequest,
    AirflowPublishResult,
    CodeValidationRequest,
    GenerationRequest,
    GenerationResult,
    ValidationReport,
)
from dagforge.service import DagGenerationService
from dagforge.validator import DagCodeValidator

STATIC_DIR = Path(__file__).parent / "static"


@lru_cache
def get_service() -> DagGenerationService:
    return DagGenerationService()


router = APIRouter(prefix="/api")


@router.get("/health")
def health(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, object]:
    return {
        "status": "ok",
        "version": __version__,
        "mode": settings.resolved_provider,
        "model": settings.active_model,
    }


@router.get("/examples")
def examples() -> list[dict[str, object]]:
    return [example.model_dump(mode="json") for example in EXAMPLES]


@router.post("/generate", response_model=GenerationResult)
def generate(
    request: GenerationRequest,
    service: Annotated[DagGenerationService, Depends(get_service)],
) -> GenerationResult:
    try:
        return service.generate(request)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Generation failed: {exc}") from exc


@router.post("/airflow/publish", response_model=AirflowPublishResult)
def publish_to_airflow(
    request: AirflowPublishRequest,
    service: Annotated[DagGenerationService, Depends(get_service)],
) -> AirflowPublishResult:
    try:
        return service.publish_to_airflow(request.spec)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Airflow publish failed: {exc}") from exc


@router.post("/validate", response_model=ValidationReport)
def validate_code(request: CodeValidationRequest) -> ValidationReport:
    return DagCodeValidator().validate(request.code)


def create_app() -> FastAPI:
    app = FastAPI(
        title="DAG Forge API",
        description="Safe AI-assisted Apache Airflow DAG generator",
        version=__version__,
    )
    app.include_router(router)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    return app


app = create_app()
