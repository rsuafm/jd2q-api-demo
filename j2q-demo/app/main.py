from __future__ import annotations

from fastapi import FastAPI

from app.models import CompileOutput, GenerateRequest
from app.pipeline import run_pipeline

app = FastAPI(title="JD-to-Query Demo API", version="0.1.0")


@app.post("/generate", response_model=CompileOutput)
def generate(request: GenerateRequest) -> dict:
    request_dict = request.model_dump()
    return run_pipeline(request_dict)
