.PHONY: install run test lint airflow-check airflow-demo airflow-demo-logs airflow-demo-stop docker

install:
	python -m pip install -e ".[dev]"

run:
	dagforge serve --reload

test:
	pytest

lint:
	ruff check .

airflow-check:
	docker compose --profile airflow-test run --rm airflow-check

airflow-demo:
	docker compose --profile airflow-demo up -d airflow-demo
	@echo "Airflow UI: http://localhost:8080"

airflow-demo-logs:
	docker compose --profile airflow-demo logs -f airflow-demo

airflow-demo-stop:
	docker compose --profile airflow-demo stop airflow-demo
	docker compose --profile airflow-demo rm -f airflow-demo

docker:
	docker compose up --build
