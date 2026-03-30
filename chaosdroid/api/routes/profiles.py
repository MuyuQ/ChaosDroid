"""Profiles API routes - 连接配置文件服务层."""

from fastapi import APIRouter, HTTPException, Query, Path
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Any
from enum import Enum
import json

from chaosdroid.services.profile_service import (
    create_fault_profile,
    get_fault_profile,
    list_fault_profiles,
    update_fault_profile,
    delete_fault_profile,
    create_validation_profile,
    get_validation_profile,
    list_validation_profiles,
    update_validation_profile,
    delete_validation_profile,
    create_recovery_profile,
    get_recovery_profile,
    list_recovery_profiles,
    update_recovery_profile,
    delete_recovery_profile,
    list_profiles,
    get_profile,
    ProfileFilters,
)
from chaosdroid.models import RiskLevel

router = APIRouter()


# ==================== 枚举定义 ====================

class ProfileTypeEnum(str, Enum):
    """配置文件类型枚举"""
    fault = "fault"
    validation = "validation"
    recovery = "recovery"


class RiskLevelEnum(str, Enum):
    """风险等级枚举"""
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class FaultTypeEnum(str, Enum):
    """故障类型枚举"""
    storage_pressure = "storage_pressure"
    low_battery = "low_battery"
    network_jitter = "network_jitter"
    reboot_timeout = "reboot_timeout"
    cpu_io_stress = "cpu_io_stress"
    monkey_stability = "monkey_stability"


# ==================== 请求模型 ====================

class FaultProfileCreate(BaseModel):
    """创建故障配置请求"""
    name: str = Field(..., min_length=1, max_length=100, description="配置名称")
    fault_type: FaultTypeEnum = Field(..., description="故障类型")
    parameters: Optional[dict] = Field(None, description="参数JSON")
    safe_cleanup_required: bool = Field(False, description="是否需要安全清理")
    risk_level: RiskLevelEnum = Field(RiskLevelEnum.low, description="风险等级")
    is_active: bool = Field(True, description="是否启用")
    description: Optional[str] = Field(None, max_length=500, description="配置描述")

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        """验证名称"""
        v = v.strip()
        if not v:
            raise ValueError('配置名称不能为空')
        return v


class FaultProfileUpdate(BaseModel):
    """更新故障配置请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    fault_type: Optional[FaultTypeEnum] = None
    parameters: Optional[dict] = None
    safe_cleanup_required: Optional[bool] = None
    risk_level: Optional[RiskLevelEnum] = None
    is_active: Optional[bool] = None
    description: Optional[str] = Field(None, max_length=500)

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        """验证名称"""
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError('配置名称不能为空')
        return v


class ValidationProfileCreate(BaseModel):
    """创建验证配置请求"""
    name: str = Field(..., min_length=1, max_length=100, description="配置名称")
    checks: Optional[dict] = Field(None, description="检查项JSON")
    timeout_sec: int = Field(180, gt=0, le=3600, description="超时时间（秒）")
    pass_rules: Optional[dict] = Field(None, description="通过规则JSON")
    description: Optional[str] = Field(None, max_length=500, description="配置描述")

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        """验证名称"""
        v = v.strip()
        if not v:
            raise ValueError('配置名称不能为空')
        return v


class ValidationProfileUpdate(BaseModel):
    """更新验证配置请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    checks: Optional[dict] = None
    timeout_sec: Optional[int] = Field(None, gt=0, le=3600)
    pass_rules: Optional[dict] = None
    description: Optional[str] = Field(None, max_length=500)

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        """验证名称"""
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError('配置名称不能为空')
        return v


class RecoveryProfileCreate(BaseModel):
    """创建恢复配置请求"""
    name: str = Field(..., min_length=1, max_length=100, description="配置名称")
    steps: Optional[dict] = Field(None, description="恢复步骤JSON")
    manual_intervention_allowed: bool = Field(True, description="是否允许人工介入")
    timeout_sec: int = Field(300, gt=0, le=7200, description="超时时间（秒）")
    description: Optional[str] = Field(None, max_length=500, description="配置描述")

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        """验证名称"""
        v = v.strip()
        if not v:
            raise ValueError('配置名称不能为空')
        return v


class RecoveryProfileUpdate(BaseModel):
    """更新恢复配置请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    steps: Optional[dict] = None
    manual_intervention_allowed: Optional[bool] = None
    timeout_sec: Optional[int] = Field(None, gt=0, le=7200)
    description: Optional[str] = Field(None, max_length=500)

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        """验证名称"""
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError('配置名称不能为空')
        return v


# ==================== 响应模型 ====================

class ApiResponse(BaseModel):
    """统一API响应格式"""
    success: bool
    data: Optional[dict] = None
    error: Optional[dict] = None


# ==================== 辅助函数 ====================

def _fault_profile_to_dict(profile) -> dict:
    """将故障配置模型转换为字典"""
    return {
        "id": profile.id,
        "name": profile.name,
        "fault_type": profile.fault_type,
        "parameters": profile.parameters or {},
        "safe_cleanup_required": profile.safe_cleanup_required,
        "risk_level": profile.risk_level,
        "is_active": profile.is_active,
        "description": profile.description,
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }


def _validation_profile_to_dict(profile) -> dict:
    """将验证配置模型转换为字典"""
    return {
        "id": profile.id,
        "name": profile.name,
        "checks": json.loads(profile.checks_json or "{}"),
        "timeout_sec": profile.timeout_sec,
        "pass_rules": json.loads(profile.pass_rules_json or "{}"),
        "description": profile.description,
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }


def _recovery_profile_to_dict(profile) -> dict:
    """将恢复配置模型转换为字典"""
    return {
        "id": profile.id,
        "name": profile.name,
        "steps": json.loads(profile.steps_json or "{}"),
        "manual_intervention_allowed": profile.manual_intervention_allowed,
        "timeout_sec": profile.timeout_sec,
        "description": profile.description,
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }


def _profile_to_dict(profile, profile_type: str) -> dict:
    """根据类型将配置模型转换为字典"""
    if profile_type == "fault":
        return _fault_profile_to_dict(profile)
    elif profile_type == "validation":
        return _validation_profile_to_dict(profile)
    elif profile_type == "recovery":
        return _recovery_profile_to_dict(profile)
    return {}


# ==================== Fault Profiles API ====================

@router.get("/fault", response_model=ApiResponse)
async def list_fault_profiles_api(
    name: Optional[str] = Query(None, max_length=100, description="名称筛选"),
    risk_level: Optional[RiskLevelEnum] = Query(None, description="风险等级筛选"),
    offset: int = Query(0, ge=0, description="偏移量"),
    limit: int = Query(100, ge=1, le=500, description="返回数量限制"),
):
    """获取故障配置列表"""
    try:
        filters = ProfileFilters(
            name=name,
            risk_level=risk_level.value if risk_level else None,
        )

        profiles, total = await list_fault_profiles(filters, offset, limit)
        profile_list = [_fault_profile_to_dict(p) for p in profiles]

        return ApiResponse(
            success=True,
            data={
                "profiles": profile_list,
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


@router.post("/fault", response_model=ApiResponse)
async def create_fault_profile_api(request: FaultProfileCreate):
    """创建故障配置"""
    try:
        profile = await create_fault_profile(
            name=request.name,
            fault_type=request.fault_type.value,
            parameters=request.parameters or {},
            safe_cleanup_required=request.safe_cleanup_required,
            risk_level=request.risk_level.value,
            is_active=request.is_active,
            description=request.description,
        )

        return ApiResponse(
            success=True,
            data={"profile": _fault_profile_to_dict(profile)}
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


@router.get("/fault/{profile_id}", response_model=ApiResponse)
async def get_fault_profile_api(profile_id: int = Path(..., gt=0, description="配置ID")):
    """获取故障配置详情"""
    try:
        profile = await get_fault_profile(profile_id)

        if not profile:
            return ApiResponse(
                success=False,
                error={"code": "not_found", "message": f"故障配置不存在: id={profile_id}"}
            )

        return ApiResponse(
            success=True,
            data={"profile": _fault_profile_to_dict(profile)}
        )

    except Exception as e:
        return ApiResponse(
            success=False,
            error={"code": "internal_error", "message": str(e)}
        )


@router.put("/fault/{profile_id}", response_model=ApiResponse)
async def update_fault_profile_api(
    profile_id: int = Path(..., gt=0, description="配置ID"),
    request: FaultProfileUpdate = None,
):
    """更新故障配置"""
    try:
        updates = {}
        if request.name is not None:
            updates["name"] = request.name
        if request.fault_type is not None:
            updates["fault_type"] = request.fault_type.value
        if request.parameters is not None:
            updates["parameters"] = request.parameters
        if request.safe_cleanup_required is not None:
            updates["safe_cleanup_required"] = request.safe_cleanup_required
        if request.risk_level is not None:
            updates["risk_level"] = request.risk_level.value
        if request.is_active is not None:
            updates["is_active"] = request.is_active
        if request.description is not None:
            updates["description"] = request.description

        if not updates:
            return ApiResponse(
                success=False,
                error={"code": "validation_error", "message": "没有提供更新字段"}
            )

        profile = await update_fault_profile(profile_id, updates)

        if not profile:
            return ApiResponse(
                success=False,
                error={"code": "not_found", "message": f"故障配置不存在: id={profile_id}"}
            )

        return ApiResponse(
            success=True,
            data={"profile": _fault_profile_to_dict(profile)}
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


@router.delete("/fault/{profile_id}", response_model=ApiResponse)
async def delete_fault_profile_api(profile_id: int = Path(..., gt=0, description="配置ID")):
    """删除故障配置"""
    try:
        deleted = await delete_fault_profile(profile_id)

        if not deleted:
            return ApiResponse(
                success=False,
                error={"code": "not_found", "message": f"故障配置不存在: id={profile_id}"}
            )

        return ApiResponse(
            success=True,
            data={"deleted": True, "profile_id": profile_id}
        )

    except Exception as e:
        return ApiResponse(
            success=False,
            error={"code": "internal_error", "message": str(e)}
        )


# ==================== Validation Profiles API ====================

@router.get("/validation", response_model=ApiResponse)
async def list_validation_profiles_api(
    name: Optional[str] = Query(None, max_length=100, description="名称筛选"),
    offset: int = Query(0, ge=0, description="偏移量"),
    limit: int = Query(100, ge=1, le=500, description="返回数量限制"),
):
    """获取验证配置列表"""
    try:
        filters = ProfileFilters(name=name)

        profiles, total = await list_validation_profiles(filters, offset, limit)
        profile_list = [_validation_profile_to_dict(p) for p in profiles]

        return ApiResponse(
            success=True,
            data={
                "profiles": profile_list,
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


@router.post("/validation", response_model=ApiResponse)
async def create_validation_profile_api(request: ValidationProfileCreate):
    """创建验证配置"""
    try:
        checks_json = json.dumps(request.checks or {}, ensure_ascii=False)
        pass_rules_json = json.dumps(request.pass_rules or {}, ensure_ascii=False)

        profile = await create_validation_profile(
            name=request.name,
            checks_json=checks_json,
            timeout_sec=request.timeout_sec,
            pass_rules_json=pass_rules_json,
            description=request.description,
        )

        return ApiResponse(
            success=True,
            data={"profile": _validation_profile_to_dict(profile)}
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


@router.get("/validation/{profile_id}", response_model=ApiResponse)
async def get_validation_profile_api(profile_id: int = Path(..., gt=0, description="配置ID")):
    """获取验证配置详情"""
    try:
        profile = await get_validation_profile(profile_id)

        if not profile:
            return ApiResponse(
                success=False,
                error={"code": "not_found", "message": f"验证配置不存在: id={profile_id}"}
            )

        return ApiResponse(
            success=True,
            data={"profile": _validation_profile_to_dict(profile)}
        )

    except Exception as e:
        return ApiResponse(
            success=False,
            error={"code": "internal_error", "message": str(e)}
        )


@router.put("/validation/{profile_id}", response_model=ApiResponse)
async def update_validation_profile_api(
    profile_id: int = Path(..., gt=0, description="配置ID"),
    request: ValidationProfileUpdate = None,
):
    """更新验证配置"""
    try:
        updates = {}
        if request.name is not None:
            updates["name"] = request.name
        if request.checks is not None:
            updates["checks_json"] = json.dumps(request.checks, ensure_ascii=False)
        if request.timeout_sec is not None:
            updates["timeout_sec"] = request.timeout_sec
        if request.pass_rules is not None:
            updates["pass_rules_json"] = json.dumps(request.pass_rules, ensure_ascii=False)
        if request.description is not None:
            updates["description"] = request.description

        if not updates:
            return ApiResponse(
                success=False,
                error={"code": "validation_error", "message": "没有提供更新字段"}
            )

        profile = await update_validation_profile(profile_id, updates)

        if not profile:
            return ApiResponse(
                success=False,
                error={"code": "not_found", "message": f"验证配置不存在: id={profile_id}"}
            )

        return ApiResponse(
            success=True,
            data={"profile": _validation_profile_to_dict(profile)}
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


@router.delete("/validation/{profile_id}", response_model=ApiResponse)
async def delete_validation_profile_api(profile_id: int = Path(..., gt=0, description="配置ID")):
    """删除验证配置"""
    try:
        deleted = await delete_validation_profile(profile_id)

        if not deleted:
            return ApiResponse(
                success=False,
                error={"code": "not_found", "message": f"验证配置不存在: id={profile_id}"}
            )

        return ApiResponse(
            success=True,
            data={"deleted": True, "profile_id": profile_id}
        )

    except Exception as e:
        return ApiResponse(
            success=False,
            error={"code": "internal_error", "message": str(e)}
        )


# ==================== Recovery Profiles API ====================

@router.get("/recovery", response_model=ApiResponse)
async def list_recovery_profiles_api(
    name: Optional[str] = Query(None, max_length=100, description="名称筛选"),
    offset: int = Query(0, ge=0, description="偏移量"),
    limit: int = Query(100, ge=1, le=500, description="返回数量限制"),
):
    """获取恢复配置列表"""
    try:
        filters = ProfileFilters(name=name)

        profiles, total = await list_recovery_profiles(filters, offset, limit)
        profile_list = [_recovery_profile_to_dict(p) for p in profiles]

        return ApiResponse(
            success=True,
            data={
                "profiles": profile_list,
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


@router.post("/recovery", response_model=ApiResponse)
async def create_recovery_profile_api(request: RecoveryProfileCreate):
    """创建恢复配置"""
    try:
        steps_json = json.dumps(request.steps or {}, ensure_ascii=False)

        profile = await create_recovery_profile(
            name=request.name,
            steps_json=steps_json,
            manual_intervention_allowed=request.manual_intervention_allowed,
            timeout_sec=request.timeout_sec,
            description=request.description,
        )

        return ApiResponse(
            success=True,
            data={"profile": _recovery_profile_to_dict(profile)}
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


@router.get("/recovery/{profile_id}", response_model=ApiResponse)
async def get_recovery_profile_api(profile_id: int = Path(..., gt=0, description="配置ID")):
    """获取恢复配置详情"""
    try:
        profile = await get_recovery_profile(profile_id)

        if not profile:
            return ApiResponse(
                success=False,
                error={"code": "not_found", "message": f"恢复配置不存在: id={profile_id}"}
            )

        return ApiResponse(
            success=True,
            data={"profile": _recovery_profile_to_dict(profile)}
        )

    except Exception as e:
        return ApiResponse(
            success=False,
            error={"code": "internal_error", "message": str(e)}
        )


@router.put("/recovery/{profile_id}", response_model=ApiResponse)
async def update_recovery_profile_api(
    profile_id: int = Path(..., gt=0, description="配置ID"),
    request: RecoveryProfileUpdate = None,
):
    """更新恢复配置"""
    try:
        updates = {}
        if request.name is not None:
            updates["name"] = request.name
        if request.steps is not None:
            updates["steps_json"] = json.dumps(request.steps, ensure_ascii=False)
        if request.manual_intervention_allowed is not None:
            updates["manual_intervention_allowed"] = request.manual_intervention_allowed
        if request.timeout_sec is not None:
            updates["timeout_sec"] = request.timeout_sec
        if request.description is not None:
            updates["description"] = request.description

        if not updates:
            return ApiResponse(
                success=False,
                error={"code": "validation_error", "message": "没有提供更新字段"}
            )

        profile = await update_recovery_profile(profile_id, updates)

        if not profile:
            return ApiResponse(
                success=False,
                error={"code": "not_found", "message": f"恢复配置不存在: id={profile_id}"}
            )

        return ApiResponse(
            success=True,
            data={"profile": _recovery_profile_to_dict(profile)}
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


@router.delete("/recovery/{profile_id}", response_model=ApiResponse)
async def delete_recovery_profile_api(profile_id: int = Path(..., gt=0, description="配置ID")):
    """删除恢复配置"""
    try:
        deleted = await delete_recovery_profile(profile_id)

        if not deleted:
            return ApiResponse(
                success=False,
                error={"code": "not_found", "message": f"恢复配置不存在: id={profile_id}"}
            )

        return ApiResponse(
            success=True,
            data={"deleted": True, "profile_id": profile_id}
        )

    except Exception as e:
        return ApiResponse(
            success=False,
            error={"code": "internal_error", "message": str(e)}
        )