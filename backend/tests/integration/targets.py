from typing import Any

from fastapi import FastAPI


def target_app(*, broken_for: str | None = None) -> FastAPI:
    """A stand-in application under test: echoes a canned answer per question."""
    app = FastAPI()

    @app.post("/invoke")
    async def invoke(body: dict[str, Any]) -> dict[str, Any]:
        question = body["messages"][-1]["content"]
        if broken_for and broken_for in question:
            return {"output": "I don't know."}
        return {"output": f"answer to {question}"}

    return app
