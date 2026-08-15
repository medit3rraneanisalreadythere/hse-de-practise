from dagforge.models import Connector, ExamplePrompt

EXAMPLES = [
    ExamplePrompt(
        title="API заказов → PostgreSQL",
        prompt=(
            "Каждое утро получай новые заказы из REST API, проверяй обязательные поля, "
            "нормализуй даты и валюту, загружай записи в витрину orders и сохраняй метрики запуска."
        ),
        source=Connector.REST_API,
        destination=Connector.POSTGRESQL,
        schedule="0 6 * * *",
    ),
    ExamplePrompt(
        title="S3 события → BigQuery",
        prompt=(
            "Раз в час обрабатывай новые JSON-файлы событий из S3, "
            "отбрасывай дубликаты по event_id, контролируй долю пустых user_id "
            "и загружай партицию в аналитическую таблицу BigQuery."
        ),
        source=Connector.S3,
        destination=Connector.BIGQUERY,
        schedule="15 * * * *",
    ),
    ExamplePrompt(
        title="PostgreSQL → Snowflake",
        prompt=(
            "По будням переносить изменившиеся записи клиентов из PostgreSQL в Snowflake, "
            "маскировать email, выполнять upsert по customer_id и уведомлять владельца "
            "о результате."
        ),
        source=Connector.POSTGRESQL,
        destination=Connector.SNOWFLAKE,
        schedule="0 2 * * 1-5",
    ),
]
