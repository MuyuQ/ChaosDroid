"""Scenarios API routes."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


class ScenarioCreate(BaseModel):
    """创建场景请求"""
    name: str
    description: Optional[str] = None
    target_type: str = "upgrade"
    fault_profile_id: int
    inject_stage: str = "precheck"
    validation_profile_id: Optional[int] = None
    recovery_profile_id: Optional[int] = None
    executor_mode: str = "mock"
    enabled: bool = True


class ScenarioUpdate(BaseModel):
    """更新场景请求"""
    name: Optional[str] = None
    description: Optional[str] = None
    target_type: Optional[str] = None
    fault_profile_id: Optional[int] = None
    inject_stage: Optional[str] = None
    validation_profile_id: Optional[int] = None
    recovery_profile_id: Optional[int] = None
    executor_mode: Optional[str] = None
    enabled: Optional[bool] = None


class ScenarioResponse(BaseModel):
    """场景响应"""
    id: int
    name: str
    description: Optional[str]
    target_type: str
    fault_profile_id: int
    inject_stage: str
    validation_profile_id: Optional[int]
    recovery_profile_id: Optional[int]
    executor_mode: str
    enabled: bool


class ApiResponse(BaseModel):
    """统一API响应格式"""
    success: bool
    data: Optional[dict] = None
    error: Optional[dict] = None


@router.get("", response_model=ApiResponse)
async def list_scenarios():
    """获取场景列表"""
    # TODO: 实现数据库查询
    return ApiResponse(success=True, data={"scenarios": []})


@router.post("", response_model=ApiResponse)
async def create_scenario(request: ScenarioCreate):
    """创建场景"""
    # TODO: 实现数据库创建
    return ApiResponse(success=True, data={"id": 1, "name": request.name})


@router.get("/{scenario_id}", response_model=ApiResponse)
async def get_scenario(scenario_id: int):
    """获取场景详情"""
    # TODO: 实现数据库查询
    return ApiResponse(success=True, data={"scenario": None})


@router.put("/{scenario_id}", response_model=ApiResponse)
async def update_scenario(scenario_id: int, request: ScenarioUpdate):
    """更新场景"""
    # TODO: 实现数据库更新
    return ApiResponse(success=True, data={"updated": True})


@router.delete("/{scenario_id}", response_model=ApiResponse)
async def delete_scenario(scenario_id: int):
    """删除场景"""
    # TODO: 实现数据库删除
    return ApiResponse(success=True, data={"deleted": True})


@router.post("/{scenario_id}/clone", response_model=ApiResponse)
async def clone_scenario(scenario_id: int, new_name: Optional[str] = None):
    """克隆场景"""
    # TODO: 实现克隆逻辑
    return ApiResponse(success=True, data={"id": 2, "name": new_name or "clone"})