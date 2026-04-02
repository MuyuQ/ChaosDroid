"""Scenarios API routes - 连接场景服务层."""

from fastapi import APIRouter, HTTPException, Query, Path
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from enum import Enum

from app.services.scenario_service import (
    create_scenario,
    get_scenario,
    list_scenarios,
    update_scenario,
    delete_scenario,
    clone_scenario,
    get_scenario_with_runs,
    ScenarioFilters,
)
from app.models import TargetType, InjectStage, ExecutorMode

router = APIRouter()


# ==================== 枚举定义 ====================

class TargetTypeEnum(str, Enum):
    """目标类型枚举"""
    upgrade = "upgrade"
    stability = "stability"
    monkey = "monkey"
    recovery = "recovery"


class InjectStageEnum(str, Enum):
    """注入阶段枚举"""
    precheck = "precheck"
    postcheck = "postcheck"
    during = "during"


class ExecutorModeEnum(str, Enum):
    """执行器模式枚举"""
    real = "real"
    mock = "mock"


# ==================== 请求模型 ====================

class ScenarioCreate(BaseModel):
    """创建场景请求"""
    name: str = Field(..., min_length=1, max_length=100, description="场景名称")
    description: Optional[str] = Field(None, max_length=500, description="场景描述")
    target_type: TargetTypeEnum = Field(TargetTypeEnum.stability, description="目标类型")
    fault_profile_id: Optional[int] = Field(None, gt=0, description="故障配置ID")
    inject_stage: InjectStageEnum = Field(InjectStageEnum.precheck, description="注入阶段")
    validation_profile_id: Optional[int] = Field(None, gt=0, description="验证配置ID")
    recovery_profile_id: Optional[int] = Field(None, gt=0, description="恢复配置ID")
    executor_mode: ExecutorModeEnum = Field(ExecutorModeEnum.mock, description="执行器模式")
    enabled: bool = Field(True, description="是否启用")

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        """验证名称不为空且去除首尾空格"""
        v = v.strip()
        if not v:
            raise ValueError('场景名称不能为空')
        return v


class ScenarioUpdate(BaseModel):
    """更新场景请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="场景名称")
    description: Optional[str] = Field(None, max_length=500, description="场景描述")
    target_type: Optional[TargetTypeEnum] = Field(None, description="目标类型")
    fault_profile_id: Optional[int] = Field(None, gt=0, description="故障配置ID")
    inject_stage: Optional[InjectStageEnum] = Field(None, description="注入阶段")
    validation_profile_id: Optional[int] = Field(None, gt=0, description="验证配置ID")
    recovery_profile_id: Optional[int] = Field(None, gt=0, description="恢复配置ID")
    executor_mode: Optional[ExecutorModeEnum] = Field(None, description="执行器模式")
    enabled: Optional[bool] = Field(None, description="是否启用")

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        """验证名称"""
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError('场景名称不能为空')
        return v


# ==================== 响应模型 ====================

class ScenarioResponse(BaseModel):
    """场景响应"""
    id: int
    name: str
    description: Optional[str]
    target_type: str
    fault_profile_id: Optional[int]
    inject_stage: str
    validation_profile_id: Optional[int]
    recovery_profile_id: Optional[int]
    executor_mode: str
    enabled: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ApiResponse(BaseModel):
    """统一API响应格式"""
    success: bool
    data: Optional[dict] = None
    error: Optional[dict] = None


# ==================== 辅助函数 ====================

def _scenario_to_dict(scenario) -> dict:
    """将场景模型转换为字典"""
    return {
        "id": scenario.id,
        "name": scenario.name,
        "description": scenario.description,
        "target_type": scenario.target_type,
        "fault_profile_id": scenario.fault_profile_id,
        "inject_stage": scenario.inject_stage,
        "validation_profile_id": scenario.validation_profile_id,
        "recovery_profile_id": scenario.recovery_profile_id,
        "executor_mode": scenario.executor_mode,
        "enabled": scenario.enabled,
        "created_at": scenario.created_at.isoformat() if scenario.created_at else None,
        "updated_at": scenario.updated_at.isoformat() if scenario.updated_at else None,
    }


# ==================== API端点 ====================

@router.get("", response_model=ApiResponse)
async def list_scenarios_api(
    name: Optional[str] = Query(None, max_length=100, description="场景名称筛选"),
    target_type: Optional[TargetTypeEnum] = Query(None, description="目标类型筛选"),
    inject_stage: Optional[InjectStageEnum] = Query(None, description="注入阶段筛选"),
    executor_mode: Optional[ExecutorModeEnum] = Query(None, description="执行器模式筛选"),
    enabled: Optional[bool] = Query(None, description="是否启用筛选"),
    offset: int = Query(0, ge=0, description="偏移量"),
    limit: int = Query(100, ge=1, le=500, description="返回数量限制"),
):
    """获取场景列表"""
    try:
        # 构建筛选条件
        filters = ScenarioFilters(
            name=name,
            target_type=target_type.value if target_type else None,
            inject_stage=inject_stage.value if inject_stage else None,
            executor_mode=executor_mode.value if executor_mode else None,
            enabled=enabled,
        )

        # 调用服务层
        scenarios, total = await list_scenarios(filters, offset, limit)

        # 转换响应
        scenario_list = [_scenario_to_dict(s) for s in scenarios]

        return ApiResponse(
            success=True,
            data={
                "scenarios": scenario_list,
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


@router.post("", response_model=ApiResponse)
async def create_scenario_api(request: ScenarioCreate):
    """创建场景"""
    try:
        # 调用服务层创建场景
        scenario = await create_scenario(
            name=request.name,
            description=request.description,
            target_type=request.target_type.value,
            fault_profile_id=request.fault_profile_id,
            inject_stage=request.inject_stage.value,
            validation_profile_id=request.validation_profile_id,
            recovery_profile_id=request.recovery_profile_id,
            executor_mode=request.executor_mode.value,
            enabled=request.enabled,
        )

        return ApiResponse(
            success=True,
            data={"scenario": _scenario_to_dict(scenario)}
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


@router.get("/{scenario_id}", response_model=ApiResponse)
async def get_scenario_api(scenario_id: int = Path(..., gt=0, description="场景ID")):
    """获取场景详情"""
    try:
        scenario = await get_scenario(scenario_id)

        if not scenario:
            return ApiResponse(
                success=False,
                error={"code": "not_found", "message": f"场景不存在: id={scenario_id}"}
            )

        return ApiResponse(
            success=True,
            data={"scenario": _scenario_to_dict(scenario)}
        )

    except Exception as e:
        return ApiResponse(
            success=False,
            error={"code": "internal_error", "message": str(e)}
        )


@router.get("/{scenario_id}/runs", response_model=ApiResponse)
async def get_scenario_runs_api(scenario_id: int = Path(..., gt=0, description="场景ID")):
    """获取场景及其关联的执行记录"""
    try:
        result = await get_scenario_with_runs(scenario_id)

        if not result:
            return ApiResponse(
                success=False,
                error={"code": "not_found", "message": f"场景不存在: id={scenario_id}"}
            )

        scenario_dict = _scenario_to_dict(result["scenario"])
        runs_list = [
            {
                "id": r.id,
                "device_serial": r.device_serial,
                "status": r.status,
                "inject_stage": r.inject_stage,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            }
            for r in result["recent_runs"]
        ]

        return ApiResponse(
            success=True,
            data={
                "scenario": scenario_dict,
                "recent_runs": runs_list,
            }
        )

    except Exception as e:
        return ApiResponse(
            success=False,
            error={"code": "internal_error", "message": str(e)}
        )


@router.put("/{scenario_id}", response_model=ApiResponse)
async def update_scenario_api(
    scenario_id: int = Path(..., gt=0, description="场景ID"),
    request: ScenarioUpdate = None,
):
    """更新场景"""
    try:
        # 构建更新字段字典
        updates = {}
        if request.name is not None:
            updates["name"] = request.name
        if request.description is not None:
            updates["description"] = request.description
        if request.target_type is not None:
            updates["target_type"] = request.target_type.value
        if request.fault_profile_id is not None:
            updates["fault_profile_id"] = request.fault_profile_id
        if request.inject_stage is not None:
            updates["inject_stage"] = request.inject_stage.value
        if request.validation_profile_id is not None:
            updates["validation_profile_id"] = request.validation_profile_id
        if request.recovery_profile_id is not None:
            updates["recovery_profile_id"] = request.recovery_profile_id
        if request.executor_mode is not None:
            updates["executor_mode"] = request.executor_mode.value
        if request.enabled is not None:
            updates["enabled"] = request.enabled

        if not updates:
            return ApiResponse(
                success=False,
                error={"code": "validation_error", "message": "没有提供更新字段"}
            )

        # 调用服务层更新
        scenario = await update_scenario(scenario_id, updates)

        if not scenario:
            return ApiResponse(
                success=False,
                error={"code": "not_found", "message": f"场景不存在: id={scenario_id}"}
            )

        return ApiResponse(
            success=True,
            data={"scenario": _scenario_to_dict(scenario)}
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


@router.delete("/{scenario_id}", response_model=ApiResponse)
async def delete_scenario_api(scenario_id: int = Path(..., gt=0, description="场景ID")):
    """删除场景"""
    try:
        deleted = await delete_scenario(scenario_id)

        if not deleted:
            return ApiResponse(
                success=False,
                error={"code": "not_found", "message": f"场景不存在: id={scenario_id}"}
            )

        return ApiResponse(
            success=True,
            data={"deleted": True, "scenario_id": scenario_id}
        )

    except Exception as e:
        return ApiResponse(
            success=False,
            error={"code": "internal_error", "message": str(e)}
        )


@router.post("/{scenario_id}/clone", response_model=ApiResponse)
async def clone_scenario_api(
    scenario_id: int = Path(..., gt=0, description="场景ID"),
    new_name: Optional[str] = Query(None, max_length=100, description="新场景名称"),
):
    """克隆场景"""
    try:
        # 验证名称
        if new_name:
            new_name = new_name.strip()
            if not new_name:
                return ApiResponse(
                    success=False,
                    error={"code": "validation_error", "message": "新场景名称不能为空"}
                )

        # 调用服务层克隆
        cloned = await clone_scenario(scenario_id, new_name)

        if not cloned:
            return ApiResponse(
                success=False,
                error={"code": "not_found", "message": f"场景不存在: id={scenario_id}"}
            )

        return ApiResponse(
            success=True,
            data={"scenario": _scenario_to_dict(cloned)}
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