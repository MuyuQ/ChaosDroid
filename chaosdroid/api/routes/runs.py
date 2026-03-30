"""Runs API routes - 连接执行记录服务层."""

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Path
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from enum import Enum
from datetime import datetime

from chaosdroid.services.run_service import (
    create_run,
    get_run,
    get_run_with_template,
    list_runs,
    get_run_steps,
    update_run_status,
    cancel_run,
    get_run_statistics,
    RunFilters,
)
from chaosdroid.services.execution_service import get_execution_service
from chaosdroid.models import RunStatus, ExecutorMode, InjectStage

router = APIRouter()


# ==================== 枚举定义 ====================

class RunStatusEnum(str, Enum):
    """执行状态枚举"""
    queued = "queued"
    preparing = "preparing"
    injecting = "injecting"
    validating = "validating"
    recovering = "recovering"
    passed = "passed"
    failed = "failed"
    partial = "partial"


class ExecutorModeEnum(str, Enum):
    """执行器模式枚举"""
    real = "real"
    mock = "mock"


class InjectStageEnum(str, Enum):
    """注入阶段枚举"""
    precheck = "precheck"
    postcheck = "postcheck"
    during = "during"


# ==================== 请求模型 ====================

class RunCreate(BaseModel):
    """创建执行请求"""
    scenario_template_id: Optional[int] = Field(None, gt=0, description="场景模板ID")
    device_serial: str = Field(..., min_length=1, max_length=50, description="设备序列号")
    executor_mode: ExecutorModeEnum = Field(ExecutorModeEnum.mock, description="执行器模式")
    inject_stage: Optional[InjectStageEnum] = Field(None, description="注入阶段")

    @field_validator('device_serial')
    @classmethod
    def validate_device_serial(cls, v: str) -> str:
        """验证设备序列号"""
        v = v.strip()
        if not v:
            raise ValueError('设备序列号不能为空')
        return v


# ==================== 响应模型 ====================

class RunResponse(BaseModel):
    """执行响应"""
    id: int
    scenario_template_id: Optional[int]
    device_serial: str
    status: str
    inject_stage: str
    started_at: Optional[str]
    finished_at: Optional[str]
    created_at: Optional[str]
    result_summary: Optional[dict] = None


class StepResponse(BaseModel):
    """步骤响应"""
    id: int
    step_type: str
    step_order: int
    status: str
    started_at: Optional[str]
    finished_at: Optional[str]
    summary: Optional[dict] = None


class ApiResponse(BaseModel):
    """统一API响应格式"""
    success: bool
    data: Optional[dict] = None
    error: Optional[dict] = None


# ==================== 辅助函数 ====================

def _run_to_dict(run) -> dict:
    """将执行记录转换为字典"""
    import json
    return {
        "id": run.id,
        "scenario_template_id": run.scenario_template_id,
        "device_serial": run.device_serial,
        "status": run.status,
        "inject_stage": run.inject_stage,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "result_summary": json.loads(run.result_summary_json or "{}"),
    }


def _step_to_dict(step) -> dict:
    """将步骤转换为字典"""
    import json
    return {
        "id": step.id,
        "step_type": step.step_type,
        "step_order": step.step_order,
        "status": step.status,
        "started_at": step.started_at.isoformat() if step.started_at else None,
        "finished_at": step.finished_at.isoformat() if step.finished_at else None,
        "summary": json.loads(step.summary_json or "{}"),
    }


async def _execute_scenario_background(run_id: int):
    """后台执行场景"""
    execution_service = get_execution_service()
    try:
        await execution_service.execute_scenario(run_id)
    except Exception as e:
        # 记录执行失败
        await update_run_status(run_id, RunStatus.FAILED.value)


# ==================== API端点 ====================

@router.get("", response_model=ApiResponse)
async def list_runs_api(
    status: Optional[RunStatusEnum] = Query(None, description="状态筛选"),
    scenario_id: Optional[int] = Query(None, gt=0, description="场景模板ID筛选"),
    device_serial: Optional[str] = Query(None, max_length=50, description="设备序列号筛选"),
    inject_stage: Optional[InjectStageEnum] = Query(None, description="注入阶段筛选"),
    started_after: Optional[str] = Query(None, description="开始时间筛选（ISO格式）"),
    started_before: Optional[str] = Query(None, description="结束时间筛选（ISO格式）"),
    offset: int = Query(0, ge=0, description="偏移量"),
    limit: int = Query(10, ge=1, le=500, description="返回数量限制"),
):
    """获取执行列表"""
    try:
        # 构建筛选条件
        filters = RunFilters(
            scenario_template_id=scenario_id,
            device_serial=device_serial,
            status=status.value if status else None,
            inject_stage=inject_stage.value if inject_stage else None,
        )

        # 解析时间筛选
        if started_after:
            try:
                filters.started_after = datetime.fromisoformat(started_after)
            except ValueError:
                return ApiResponse(
                    success=False,
                    error={"code": "validation_error", "message": "started_after格式无效，需要ISO格式"}
                )

        if started_before:
            try:
                filters.started_before = datetime.fromisoformat(started_before)
            except ValueError:
                return ApiResponse(
                    success=False,
                    error={"code": "validation_error", "message": "started_before格式无效，需要ISO格式"}
                )

        # 调用服务层
        runs, total = await list_runs(filters, offset, limit)

        # 转换响应
        run_list = [_run_to_dict(r) for r in runs]

        return ApiResponse(
            success=True,
            data={
                "runs": run_list,
                "total": total,
                "offset": offset,
                "limit": limit,
            }
        )

    except Exception as e:
        return ApiResponse(
            success=False,
            error={"code": "internal_error", "message": str(e)}
        )


@router.get("/statistics", response_model=ApiResponse)
async def get_run_statistics_api():
    """获取执行记录统计信息"""
    try:
        stats = await get_run_statistics()

        return ApiResponse(
            success=True,
            data={"statistics": stats}
        )

    except Exception as e:
        return ApiResponse(
            success=False,
            error={"code": "internal_error", "message": str(e)}
        )


@router.post("", response_model=ApiResponse)
async def create_run_api(request: RunCreate):
    """创建执行记录"""
    try:
        # 调用服务层创建执行记录
        run = await create_run(
            scenario_template_id=request.scenario_template_id,
            device_serial=request.device_serial,
            executor_mode=request.executor_mode.value,
            inject_stage=request.inject_stage.value if request.inject_stage else None,
        )

        return ApiResponse(
            success=True,
            data={"run": _run_to_dict(run)}
        )

    except ValueError as e:
        return ApiResponse(
            success=False,
            error={"code": "validation_error", "message": str(e)}
        )
    except Exception as e:
        return ApiResponse(
            success=False,
            error={"code": "internal_error", "message": str(e)}
        )


@router.get("/{run_id}", response_model=ApiResponse)
async def get_run_api(run_id: int = Path(..., gt=0, description="执行记录ID")):
    """获取执行详情"""
    try:
        result = await get_run_with_template(run_id)

        if not result:
            return ApiResponse(
                success=False,
                error={"code": "not_found", "message": f"执行记录不存在: id={run_id}"}
            )

        run_dict = _run_to_dict(result["run"])
        template = result["template"]

        template_dict = None
        if template:
            template_dict = {
                "id": template.id,
                "name": template.name,
                "target_type": template.target_type,
                "executor_mode": template.executor_mode,
            }

        return ApiResponse(
            success=True,
            data={
                "run": run_dict,
                "template": template_dict,
            }
        )

    except Exception as e:
        return ApiResponse(
            success=False,
            error={"code": "internal_error", "message": str(e)}
        )


@router.get("/{run_id}/steps", response_model=ApiResponse)
async def get_run_steps_api(run_id: int = Path(..., gt=0, description="执行记录ID")):
    """获取执行步骤详情"""
    try:
        # 先检查执行记录是否存在
        run = await get_run(run_id)
        if not run:
            return ApiResponse(
                success=False,
                error={"code": "not_found", "message": f"执行记录不存在: id={run_id}"}
            )

        # 获取步骤列表
        steps = await get_run_steps(run_id)
        steps_list = [_step_to_dict(s) for s in steps]

        return ApiResponse(
            success=True,
            data={
                "run_id": run_id,
                "steps": steps_list,
                "total": len(steps_list),
            }
        )

    except Exception as e:
        return ApiResponse(
            success=False,
            error={"code": "internal_error", "message": str(e)}
        )


@router.post("/{run_id}/execute", response_model=ApiResponse)
async def execute_run_api(
    run_id: int = Path(..., gt=0, description="执行记录ID"),
    background_tasks: BackgroundTasks = None,
):
    """触发执行（异步）"""
    try:
        # 检查执行记录是否存在
        run = await get_run(run_id)
        if not run:
            return ApiResponse(
                success=False,
                error={"code": "not_found", "message": f"执行记录不存在: id={run_id}"}
            )

        # 检查状态是否可以执行
        if run.status not in (RunStatus.QUEUED.value,):
            return ApiResponse(
                success=False,
                error={
                    "code": "invalid_status",
                    "message": f"当前状态'{run.status}'不允许执行，只有'queued'状态的执行记录可以触发执行"
                }
            )

        # 更新状态为preparing
        await update_run_status(run_id, RunStatus.PREPARING.value)

        # 添加后台任务执行场景
        background_tasks.add_task(_execute_scenario_background, run_id)

        return ApiResponse(
            success=True,
            data={
                "run_id": run_id,
                "status": RunStatus.PREPARING.value,
                "message": "执行已触发，正在后台执行",
            }
        )

    except ValueError as e:
        return ApiResponse(
            success=False,
            error={"code": "validation_error", "message": str(e)}
        )
    except Exception as e:
        return ApiResponse(
            success=False,
            error={"code": "internal_error", "message": str(e)}
        )


@router.delete("/{run_id}", response_model=ApiResponse)
async def cancel_run_api(run_id: int = Path(..., gt=0, description="执行记录ID")):
    """取消执行"""
    try:
        run = await cancel_run(run_id)

        if not run:
            # 检查是否存在
            existing = await get_run(run_id)
            if not existing:
                return ApiResponse(
                    success=False,
                    error={"code": "not_found", "message": f"执行记录不存在: id={run_id}"}
                )

            # 无法取消
            return ApiResponse(
                success=False,
                error={
                    "code": "cannot_cancel",
                    "message": f"当前状态'{existing.status}'不允许取消，只有'queued'或'preparing'状态的执行记录可以取消"
                }
            )

        return ApiResponse(
            success=True,
            data={
                "cancelled": True,
                "run": _run_to_dict(run),
            }
        )

    except Exception as e:
        return ApiResponse(
            success=False,
            error={"code": "internal_error", "message": str(e)}
        )