from __future__ import annotations

import ast
import re
from dataclasses import dataclass

from dagforge.models import Severity, ValidationFinding, ValidationReport


@dataclass(frozen=True)
class RuleContext:
    code: str
    tree: ast.AST | None


class DagCodeValidator:
    """Static, side-effect-free validation of generated or pasted DAG source code."""

    secret_patterns = (
        ("secret.openai", re.compile(r"sk-[A-Za-z0-9_-]{20,}"), "OpenAI API key"),
        ("secret.aws", re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key"),
        (
            "secret.assignment",
            re.compile(r"(?i)(password|api_key|secret|token)\s*=\s*['\"][^'\"]{8,}['\"]"),
            "hard-coded credential",
        ),
    )
    dangerous_calls = {"eval", "exec", "compile", "os.system", "subprocess.run", "subprocess.Popen"}

    def validate(self, code: str) -> ValidationReport:
        findings: list[ValidationFinding] = []
        tree: ast.AST | None = None
        checks = 0

        checks += 1
        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            findings.append(
                ValidationFinding(
                    rule_id="python.syntax",
                    severity=Severity.ERROR,
                    title="Синтаксическая ошибка Python",
                    message=exc.msg,
                    line=exc.lineno,
                )
            )

        checks += 1
        if "from airflow.sdk import" not in code:
            findings.append(
                ValidationFinding(
                    rule_id="airflow.public_api",
                    severity=Severity.WARNING,
                    title="Используйте публичный Airflow SDK",
                    message="Для Airflow 3 ожидается импорт из airflow.sdk.",
                )
            )

        checks += 1
        if not re.search(r"\bcatchup\s*=\s*False\b", code):
            findings.append(
                ValidationFinding(
                    rule_id="airflow.catchup",
                    severity=Severity.WARNING,
                    title="Catchup не отключён",
                    message="Явно укажите catchup=False, если исторический backfill не нужен.",
                )
            )

        checks += 1
        if "retries=" not in code and '"retries"' not in code:
            findings.append(
                ValidationFinding(
                    rule_id="reliability.retries",
                    severity=Severity.WARNING,
                    title="Не заданы повторные попытки",
                    message="Production DAG должен иметь ограниченную retry-политику.",
                )
            )

        checks += 1
        if "execution_timeout=" not in code:
            findings.append(
                ValidationFinding(
                    rule_id="reliability.timeout",
                    severity=Severity.INFO,
                    title="Нет таймаута задач",
                    message="Ограничьте время выполнения задач через execution_timeout.",
                )
            )

        for rule_id, pattern, label in self.secret_patterns:
            checks += 1
            match = pattern.search(code)
            if match:
                findings.append(
                    ValidationFinding(
                        rule_id=rule_id,
                        severity=Severity.ERROR,
                        title="Обнаружен возможный секрет",
                        message=(
                            f"Удалите {label} из исходного кода и используйте Airflow Connection."
                        ),
                        line=code[: match.start()].count("\n") + 1,
                    )
                )

        checks += 1
        if tree is not None:
            findings.extend(self._find_dangerous_calls(tree))

        checks += 1
        if re.search(r"datetime\.now\s*\(", code):
            findings.append(
                ValidationFinding(
                    rule_id="airflow.dynamic_start_date",
                    severity=Severity.WARNING,
                    title="Динамическая start_date",
                    message=(
                        "datetime.now() делает расписание непредсказуемым; "
                        "используйте фиксированную дату."
                    ),
                )
            )

        errors = sum(item.severity == Severity.ERROR for item in findings)
        warnings = sum(item.severity == Severity.WARNING for item in findings)
        infos = sum(item.severity == Severity.INFO for item in findings)
        score = max(0, 100 - errors * 30 - warnings * 10 - infos * 3)
        return ValidationReport(
            passed=errors == 0,
            score=score,
            findings=findings,
            checks_run=checks,
        )

    def _find_dangerous_calls(self, tree: ast.AST) -> list[ValidationFinding]:
        findings: list[ValidationFinding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = self._call_name(node.func)
            if name in self.dangerous_calls:
                findings.append(
                    ValidationFinding(
                        rule_id="security.dangerous_call",
                        severity=Severity.ERROR,
                        title="Опасный вызов",
                        message=f"Вызов {name} запрещён политикой безопасной генерации.",
                        line=getattr(node, "lineno", None),
                    )
                )
        return findings

    @staticmethod
    def _call_name(node: ast.expr) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parts = [node.attr]
            current: ast.expr = node.value
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            return ".".join(reversed(parts))
        return ""
