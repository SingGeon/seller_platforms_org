"""Orange Systems sales-intelligence pipeline: collectors + LangGraph signal extraction."""
from .documents import Document, dedupe, docs_hash
from .graph import build_graph, run_signal_pipeline
from .llm import AnthropicBackend, HeuristicBackend, MemoryCache, make_backend
from .schemas import Answer, CompanyInfo, DetectedEvent, Evidence, PipelineResult, QuestionSpec, Usage

__all__ = [
    "Answer", "AnthropicBackend", "CompanyInfo", "DetectedEvent", "Document", "Evidence", "HeuristicBackend",
    "MemoryCache", "PipelineResult", "QuestionSpec", "Usage", "build_graph", "dedupe", "docs_hash",
    "make_backend", "run_signal_pipeline",
]
