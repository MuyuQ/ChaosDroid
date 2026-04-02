"""诊断 API 路由 - 简化版集成 ChaosDroid 数据模型。"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.diagnosis.services.ingest import IngestService
from app.diagnosis.services.diagnose import DiagnoseService
from app.diagnosis.models.db import get_session
from app.diagnosis.exceptions import NotFoundError, DiagnosisError


router = APIRouter(prefix="/api/diagnosis", tags=["diagnosis"])


class IngestRequest(BaseModel):
    log_path: str
    device_serial: Optional[str] = None
    test_type: Optional[str] = None


class DiagnoseRequest(BaseModel):
    run_id: str


class DiagnoseResponse(BaseModel):
    run_id: str
    stage: str
    category: str
    root_cause: str
    confidence: float
    result_status: str
    key_evidence: list[str]
    next_action: str


@router.post("/ingest")
async def ingest_logs(request: IngestRequest):
    """导入日志。"""
    service = IngestService()
    metadata = {}
    if request.device_serial:
        metadata["device_serial"] = request.device_serial
    if request.test_type:
        metadata["test_type"] = request.test_type

    try:
        run_id = service.ingest_path(request.log_path, metadata)
        return {"run_id": run_id, "status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导入失败：{str(e)}")


@router.post("/run", response_model=DiagnoseResponse)
async def run_diagnose(request: DiagnoseRequest):
    """执行诊断。"""
    session = get_session()
    service = DiagnoseService(session=session)

    try:
        result = service.diagnose(request.run_id)
        if not result:
            raise HTTPException(status_code=404, detail="诊断失败")

        return DiagnoseResponse(
            run_id=result.run_id,
            stage=result.stage.value if hasattr(result.stage, 'value') else result.stage,
            category=result.category,
            root_cause=result.root_cause,
            confidence=result.confidence,
            result_status=result.result_status.value if hasattr(result.result_status, 'value') else result.result_status,
            key_evidence=result.key_evidence,
            next_action=result.next_action,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DiagnosisError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/result/{run_id}")
async def get_diagnosis_result(run_id: str):
    """获取诊断结果。"""
    session = get_session()
    service = DiagnoseService(session=session)
    result = service.get_result(run_id)

    if not result:
        raise HTTPException(status_code=404, detail="诊断结果不存在")

    return {
        "run_id": result.run_id,
        "stage": result.stage.value if hasattr(result.stage, 'value') else result.stage,
        "category": result.category,
        "root_cause": result.root_cause,
        "confidence": result.confidence,
        "result_status": result.result_status.value if hasattr(result.result_status, 'value') else result.result_status,
        "key_evidence": result.key_evidence,
        "next_action": result.next_action,
        "generated_at": result.generated_at.isoformat() if result.generated_at else None,
    }
