import json
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from tracebench.evals.models import (
    EmbeddingSimilaritySpec,
    ExactMatchSpec,
    JsonSchemaSpec,
    LlmJudgeSpec,
    ScorerSpec,
)

_specs = TypeAdapter(list[ScorerSpec])


class ScorerSpecError(ValueError):
    pass


def parse_scorer(raw: str) -> ScorerSpec:
    """Parses CLI scorer shorthands.

    exact_match | embedding_similarity[:threshold] | llm_judge[:threshold] | json_schema:@path/to/schema.json
    """
    name, _, arg = raw.partition(":")
    try:
        match name:
            case "exact_match":
                return ExactMatchSpec()
            case "embedding_similarity":
                return EmbeddingSimilaritySpec(threshold=float(arg)) if arg else EmbeddingSimilaritySpec()
            case "llm_judge":
                return LlmJudgeSpec(threshold=float(arg)) if arg else LlmJudgeSpec()
            case "json_schema":
                if not arg.startswith("@"):
                    raise ScorerSpecError("json_schema needs a schema file, e.g. json_schema:@schema.json")
                schema = json.loads(Path(arg[1:]).read_text())
                return JsonSchemaSpec.model_validate({"schema": schema})
    except (ValueError, OSError, ValidationError) as exc:
        if isinstance(exc, ScorerSpecError):
            raise
        raise ScorerSpecError(f"invalid scorer {raw!r}: {exc}") from exc
    raise ScorerSpecError(f"unknown scorer {name!r}; use exact_match, embedding_similarity, llm_judge or json_schema")


def load_scorer_file(path: Path) -> list[ScorerSpec]:
    try:
        return _specs.validate_json(path.read_bytes())
    except (OSError, ValidationError) as exc:
        raise ScorerSpecError(f"cannot load scorers from {path}: {exc}") from exc
