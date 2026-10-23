"""FastAPI application (typed Pydantic models). NOTE: written against the same Service as the stdlib server;
it could NOT be executed in the authoring sandbox because fastapi/pydantic were not installable offline.
Run:  uvicorn backend.fastapi_app:app --port 8000"""
from typing import List, Optional, Literal
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from .logging_setup import setup
from .service import Service, ApiError

setup()
app = FastAPI(title="CompilerX-AI", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])
svc = Service()
Lang = Literal["c", "cpp", "java", "python"]


class SourceReq(BaseModel):
    language: Lang
    source: str = Field(max_length=200_000)


class RunReq(SourceReq):
    stdin: str = Field("", max_length=10_000)
    timeout: float = Field(5, ge=0.5, le=10)


class DiagnoseReq(SourceReq):
    validate_patches: bool = True
    top_k: int = Field(5, ge=1, le=20)
    counterfactual: bool = False
    cf_max_lines: int = Field(6, ge=1, le=12)
    cf_patches_per_line: int = Field(3, ge=1, le=6)


class CounterfactualReq(SourceReq):
    validate_patches: bool = True
    top_k: int = Field(5, ge=1, le=20)
    max_lines: int = Field(6, ge=1, le=12)
    patches_per_line: int = Field(3, ge=1, le=6)


class EditM(BaseModel):
    offset: int = Field(ge=0)
    delete: int = Field(ge=0)
    insert: str = Field(max_length=1000)


class PatchM(BaseModel):
    template: str = "custom"
    description: str = ""
    line: int = 0
    edits: List[EditM] = Field(min_length=1, max_length=20)


class PatchReq(SourceReq):
    patch: PatchM
    accept: bool = False


class BenchReq(BaseModel):
    split: Literal["train", "val", "test"] = "test"
    suggestion_limit: int = Field(10, ge=0, le=200)


def _call(fn, *a):
    try:
        return fn(*a)
    except ApiError as e:
        raise HTTPException(e.status, e.message)


@app.get("/api/health")
def health(): return svc.health()
@app.get("/api/languages")
def languages(): return svc.languages()
@app.get("/api/samples")
def samples(): return svc.samples()
@app.get("/api/model/status")
def model_status(): return svc.model_status()
@app.get("/api/benchmark/results")
def bench_results(): return svc.benchmark_results()
@app.get("/api/benchmark/status")
def bench_status(job: Optional[str] = None): return _call(svc.benchmark_status, job)
@app.get("/api/history")
def history(limit: int = 50): return svc.history(limit)
@app.post("/api/compile")
def compile_(r: SourceReq): return _call(svc.compile, r.model_dump())
@app.post("/api/run")
def run(r: RunReq): return _call(svc.run, r.model_dump())
@app.post("/api/diagnose")
def diagnose(r: DiagnoseReq):
    d = r.model_dump(); d["validate"] = d.pop("validate_patches"); return _call(svc.diagnose, d)
@app.post("/api/counterfactual")
def counterfactual(r: CounterfactualReq):
    d = r.model_dump(); d["validate"] = d.pop("validate_patches"); return _call(svc.counterfactual, d)
@app.post("/api/patch/validate")
def patch_validate(r: PatchReq): return _call(svc.validate_patch, r.model_dump())
@app.post("/api/patch/apply")
def patch_apply(r: PatchReq): return _call(svc.apply_patch, r.model_dump())
@app.post("/api/benchmark/run")
def bench_run(r: BenchReq): return _call(svc.benchmark_start, r.model_dump())
