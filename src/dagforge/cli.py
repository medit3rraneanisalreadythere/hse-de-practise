from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from dagforge.config import get_settings
from dagforge.models import Connector, GenerationRequest, PolicyPack
from dagforge.service import DagGenerationService


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dagforge", description="AI-assisted Airflow DAG generator"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="start the web UI and API")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)
    serve.add_argument("--reload", action="store_true")

    generate = subparsers.add_parser("generate", help="generate a DAG file from the command line")
    generate.add_argument("--prompt", required=True)
    generate.add_argument(
        "--source", choices=[item.value for item in Connector], default="rest_api"
    )
    generate.add_argument(
        "--destination", choices=[item.value for item in Connector], default="postgresql"
    )
    generate.add_argument("--schedule", default="0 6 * * *")
    generate.add_argument("--output", type=Path, required=True)
    generate.add_argument(
        "--policy", choices=[item.value for item in PolicyPack], default="production"
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    settings = get_settings()
    if args.command == "serve":
        uvicorn.run(
            "dagforge.api:app",
            host=args.host or settings.dagforge_host,
            port=args.port or settings.dagforge_port,
            reload=args.reload,
        )
        return

    request = GenerationRequest(
        prompt=args.prompt,
        source=args.source,
        destination=args.destination,
        schedule=args.schedule,
        policy_pack=args.policy,
    )
    result = DagGenerationService(settings=settings).generate(request)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(result.code, encoding="utf-8")
    print(f"DAG: {result.spec.dag_id}")
    print(f"Mode: {result.mode}; validation score: {result.validation.score}/100")
    print(f"Saved: {args.output.resolve()}")


if __name__ == "__main__":
    main()
