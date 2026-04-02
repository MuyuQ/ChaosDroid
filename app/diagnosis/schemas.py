"""Pydantic schemas模块。"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, Field

from app.diagnosis.enums import Stage, SourceType, EventType, Severity, RunStatus, ResultStatus

if TYPE_CHECKING:
    from app.diagnosis.engine.rule import DiagnosticRule  # 仅用于类型检查，避免循环导入


class NormalizedEvent(BaseModel):
    """标准化事件Pydantic模型。"""

    id: Optional[int] = None
    run_id: str
    device_serial: Optional[str] = None
    source_type: SourceType
    timestamp: Optional[datetime] = None
    line_no: Optional[int] = None
    raw_line: Optional[str] = None
    stage: Stage
    event_type: EventType
    severity: Severity
    normalized_code: str
    message: Optional[str] = None
    kv_payload: Optional[dict] = None


class DiagnosticResult(BaseModel):
    """诊断结果Pydantic模型。"""

    run_id: str
    stage: Stage
    category: str
    root_cause: str
    confidence: float
    result_status: ResultStatus
    key_evidence: list[str] = Field(default_factory=list)
    next_action: Optional[str] = None
    similar_cases: list[dict] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class SimilarCase(BaseModel):
    """相似案例Pydantic模型。"""

    run_id: str
    category: str
    root_cause: str
    similarity_score: float
    reason: Optional[str] = None


class ReportPayload(BaseModel):
    """报告数据结构。"""

    run_id: str
    device_serial: Optional[str] = None
    test_type: Optional[str] = None
    build_fingerprint: Optional[str] = None
    import_path: str
    status: RunStatus
    started_at: datetime
    finished_at: Optional[datetime] = None
    result: Optional[DiagnosticResult] = None
    artifacts: list[dict] = Field(default_factory=list)
    events: list[NormalizedEvent] = Field(default_factory=list)
    rule_hits: list[dict] = Field(default_factory=list)
    similar_cases: list[SimilarCase] = Field(default_factory=list)


class IngestRequest(BaseModel):
    """导入请求模型。"""

    path: str
    device_serial: Optional[str] = None
    test_type: Optional[str] = None
    build_fingerprint: Optional[str] = None