"""Runs API routes."""
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from enum import Enum

router = APIRouter()


class RunStatus(str, Enum):
    """执行状态"""
    queued = "queued"
    preparing = "preparing"
    injecting = "injecting"
    validating = "validating"
    recovering = "recovering"
    passed = "passed"
    failed = "failed"
    partial = "partial"


class RunCreate(BaseModel):
    """创建执行请求"""
    scenario_template_id: int
    device_serial: str
    executor_mode: str = "mock"


class RunResponse(BaseModel):
    """执行响应"""
    id: int
    scenario_template_id: int
    device_serial: str
    status: RunStatus
    started_at: Optional[str]
    finished_at: Optional[str]


class ApiResponse(BaseModel):
    """统一API响应格式"""
    success: bool
    data: Optional[dict] = None
    error: Optional[dict] = None


@router.get("", response_model=ApiResponse)
async def list_runs(
    status: Optional[RunStatus] = None,
    scenario_id: Optional[int] = None,
    device_serial: Optional[str] = None,
    limit: int = 10
):
    """获取执行列表"""
    # TODO: 实现数据库查询
    return ApiResponse(success=True, data={"runs": []})


@router.post("", response_model=ApiResponse)
async def create_run(request: RunCreate):
    """创建执行记录"""
    # TODO: 实现数据库创建
    return ApiResponse(success=True, data={"id": 1, "status": "queued"})


@router.get("/{run_id}", response_model=ApiResponse)
async def get_run(run_id: int):
    """获取执行详情"""
    # TODO: 实现数据库查询
    return ApiResponse(success=True, data={"run": None})


@router.post("/{run_id}/execute", response_model=ApiResponse)
async def execute_run(run_id: int, background_tasks: BackgroundTasks):
    """触发执行（异步）"""
    # TODO: 实现异步执行逻辑
    # background_tasks.add_task(execute_scenario, run_id)
    return ApiResponse(success=True, data={"status": "preparing"})


@router.delete("/{run_id}", response_model=ApiResponse)
async def cancel_run(run_id: int):
    """取消执行"""
    # TODO: 实现取消逻辑
    return ApiResponse(success=True, data={"cancelled": True})