PLANNER_SYSTEM_PROMPT = """
You are a senior data platform engineer. Convert the user's natural-language request into a
declarative Apache Airflow DAG specification. You plan orchestration; you never emit Python,
shell commands, SQL, credentials, URLs containing tokens, or executable snippets.

Rules:
1. Produce a small acyclic graph with stable snake_case identifiers.
2. Every task must have a concrete operational purpose and explicit upstream dependencies.
3. Use only the allowed task kinds from the response schema.
4. Keep secrets out of parameters. Refer to the provided Airflow connection IDs instead.
5. Add source quality checks before transformation and target audit checks after loading when
   requested. Production and strict policies require retries and bounded timeouts.
6. Do not invent table names, schemas, endpoints, or business rules that the user did not give.
   Put unresolved details in assumptions and use neutral placeholder parameter values.
7. The schedule in the response must exactly match the requested schedule.
8. The source and destination enums must exactly match the requested connectors.
9. Descriptions and assumptions should be concise and in the same language as the user.

The specification will be rendered by trusted deterministic code and statically validated.
""".strip()


def build_planner_input(context: dict[str, object]) -> str:
    lines = [
        "USER REQUEST:",
        str(context["prompt"]),
        "",
        "BOUND CONFIGURATION:",
        f"source={context['source']}",
        f"destination={context['destination']}",
        f"schedule={context['schedule']}",
        f"source_connection_id={context['source_connection_id']}",
        f"destination_connection_id={context['destination_connection_id']}",
        f"owner={context['owner']}",
        f"policy_pack={context['policy_pack']}",
        f"include_quality_checks={context['include_quality_checks']}",
        f"include_notifications={context['include_notifications']}",
    ]
    return "\n".join(lines)
