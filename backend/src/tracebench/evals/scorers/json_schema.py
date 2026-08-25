import json
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from tracebench.errors import ValidationFailedError
from tracebench.evals.models import JsonSchemaSpec, ScoreResult
from tracebench.evals.scorers.base import ScoringInput


class JsonSchemaScorer:
    name = "json_schema"

    def __init__(self, spec: JsonSchemaSpec) -> None:
        try:
            Draft202012Validator.check_schema(spec.json_schema)
        except SchemaError as exc:
            raise ValidationFailedError(f"invalid JSON schema: {exc.message}") from exc
        self._validator = Draft202012Validator(spec.json_schema)

    async def score(self, case: ScoringInput) -> ScoreResult | None:
        document: Any = case.output
        if isinstance(document, str):
            try:
                document = json.loads(document)
            except json.JSONDecodeError as exc:
                return ScoreResult(scorer=self.name, value=0.0, passed=False, detail=f"not valid JSON: {exc.msg}")
        errors = sorted(self._validator.iter_errors(document), key=lambda e: list(e.path))
        if not errors:
            return ScoreResult(scorer=self.name, value=1.0, passed=True)
        first = errors[0]
        location = "/".join(str(p) for p in first.path) or "<root>"
        return ScoreResult(
            scorer=self.name,
            value=0.0,
            passed=False,
            detail=f"{location}: {first.message}" + (f" (+{len(errors) - 1} more)" if len(errors) > 1 else ""),
        )
