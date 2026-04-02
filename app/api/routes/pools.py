"""Device pool API routes - 设备池管理接口."""

from fastapi import APIRouter, HTTPException, Query, Path, Depends
from pydantic import BaseModel, Field
from typing import Optional, List

from app.models import get_session_context
from app.models.device_pool import DevicePool
from app.scheduling import PoolManager
from app.scheduling.enums import DevicePoolPurpose

router = APIRouter()


# ==================== 响应模型 ====================

class PoolCreateRequest(BaseModel):
    """创建设备池请求."""
    name: str = Field(..., min_length=1, max_length=64, description="设备池名称")
    purpose: str = Field(..., description="用途: stable/stress/emergency")
    reserved_emergency_ratio: float = Field(0.2, ge=0.0, le=1.0, description="预留应急比例")
    max_parallel_jobs: Optional[int] = Field(None, ge=1, description="最大并行任务数")
    enabled: bool = Field(True, description="是否启用")


class PoolUpdateRequest(BaseModel):
    """更新设备池请求."""
    name: Optional[str] = Field(None, min_length=1, max_length=64, description="设备池名称")
    purpose: Optional[str] = Field(None, description="用途: stable/stress/emergency")
    reserved_emergency_ratio: Optional[float] = Field(None, ge=0.0, le=1.0, description="预留应急比例")
    max_parallel_jobs: Optional[int] = Field(None, ge=1, description="最大并行任务数")
    enabled: Optional[bool] = Field(None, description="是否启用")


class PoolResponse(BaseModel):
    """设备池响应."""
    id: int
    name: str
    purpose: str
    reserved_emergency_ratio: float
    max_parallel_jobs: Optional[int]
    enabled: bool
    created_at: str
    updated_at: str


class PoolListResponse(BaseModel):
    """设备池列表响应."""
    pools: List[PoolResponse]
    total: int


class ApiResponse(BaseModel):
    """统一API响应格式."""
    success: bool
    data: Optional[dict] = None
    error: Optional[dict] = None


# ==================== API端点 ====================

@router.get("", response_model=ApiResponse)
async def list_pools(
    enabled_only: bool = Query(True, description="仅返回启用的设备池"),
):
    """获取设备池列表."""
    try:
        with get_session_context() as session:
            pool_manager = PoolManager(session)
            pools = pool_manager.list_pools(enabled_only=enabled_only)

            pool_responses = [
                PoolResponse(
                    id=p.id,
                    name=p.name,
                    purpose=p.purpose,
                    reserved_emergency_ratio=p.reserved_emergency_ratio,
                    max_parallel_jobs=p.max_parallel_jobs,
                    enabled=p.enabled,
                    created_at=p.created_at.isoformat() if p.created_at else "",
                    updated_at=p.updated_at.isoformat() if p.updated_at else "",
                )
                for p in pools
            ]

            return ApiResponse(
                success=True,
                data={
                    "pools": [r.model_dump() for r in pool_responses],
                    "total": len(pool_responses),
                }
            )

    except Exception as e:
        return ApiResponse(
            success=False,
            error={"code": "internal_error", "message": str(e)}
        )


@router.post("", response_model=ApiResponse)
async def create_pool(request: PoolCreateRequest):
    """创建设备池."""
    try:
        # 验证purpose值
        valid_purposes = [p.value for p in DevicePoolPurpose]
        if request.purpose not in valid_purposes:
            return ApiResponse(
                success=False,
                error={
                    "code": "validation_error",
                    "message": f"无效的purpose值: {request.purpose}，有效值为: {valid_purposes}"
                }
            )

        with get_session_context() as session:
            pool_manager = PoolManager(session)
            pool = pool_manager.create_pool(
                name=request.name,
                purpose=request.purpose,
                reserved_emergency_ratio=request.reserved_emergency_ratio,
                max_parallel_jobs=request.max_parallel_jobs,
                enabled=request.enabled,
            )

            return ApiResponse(
                success=True,
                data={
                    "pool": PoolResponse(
                        id=pool.id,
                        name=pool.name,
                        purpose=pool.purpose,
                        reserved_emergency_ratio=pool.reserved_emergency_ratio,
                        max_parallel_jobs=pool.max_parallel_jobs,
                        enabled=pool.enabled,
                        created_at=pool.created_at.isoformat() if pool.created_at else "",
                        updated_at=pool.updated_at.isoformat() if pool.updated_at else "",
                    ).model_dump()
                }
            )

    except Exception as e:
        return ApiResponse(
            success=False,
            error={"code": "internal_error", "message": str(e)}
        )


@router.get("/{pool_id}", response_model=ApiResponse)
async def get_pool(
    pool_id: int = Path(..., ge=1, description="设备池ID"),
):
    """获取设备池详情."""
    try:
        with get_session_context() as session:
            pool_manager = PoolManager(session)
            pool = pool_manager.get_pool(pool_id)

            if not pool:
                return ApiResponse(
                    success=False,
                    error={"code": "not_found", "message": f"设备池不存在: {pool_id}"}
                )

            return ApiResponse(
                success=True,
                data={
                    "pool": PoolResponse(
                        id=pool.id,
                        name=pool.name,
                        purpose=pool.purpose,
                        reserved_emergency_ratio=pool.reserved_emergency_ratio,
                        max_parallel_jobs=pool.max_parallel_jobs,
                        enabled=pool.enabled,
                        created_at=pool.created_at.isoformat() if pool.created_at else "",
                        updated_at=pool.updated_at.isoformat() if pool.updated_at else "",
                    ).model_dump()
                }
            )

    except Exception as e:
        return ApiResponse(
            success=False,
            error={"code": "internal_error", "message": str(e)}
        )


@router.put("/{pool_id}", response_model=ApiResponse)
async def update_pool(
    pool_id: int = Path(..., ge=1, description="设备池ID"),
    request: PoolUpdateRequest = None,
):
    """更新设备池."""
    try:
        with get_session_context() as session:
            pool_manager = PoolManager(session)
            pool = pool_manager.update_pool(
                pool_id=pool_id,
                name=request.name,
                purpose=request.purpose,
                reserved_emergency_ratio=request.reserved_emergency_ratio,
                max_parallel_jobs=request.max_parallel_jobs,
                enabled=request.enabled,
            )

            if not pool:
                return ApiResponse(
                    success=False,
                    error={"code": "not_found", "message": f"设备池不存在: {pool_id}"}
                )

            return ApiResponse(
                success=True,
                data={
                    "pool": PoolResponse(
                        id=pool.id,
                        name=pool.name,
                        purpose=pool.purpose,
                        reserved_emergency_ratio=pool.reserved_emergency_ratio,
                        max_parallel_jobs=pool.max_parallel_jobs,
                        enabled=pool.enabled,
                        created_at=pool.created_at.isoformat() if pool.created_at else "",
                        updated_at=pool.updated_at.isoformat() if pool.updated_at else "",
                    ).model_dump()
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


@router.delete("/{pool_id}", response_model=ApiResponse)
async def delete_pool(
    pool_id: int = Path(..., ge=1, description="设备池ID"),
):
    """删除设备池."""
    try:
        with get_session_context() as session:
            pool_manager = PoolManager(session)
            deleted = pool_manager.delete_pool(pool_id)

            if not deleted:
                return ApiResponse(
                    success=False,
                    error={"code": "not_found", "message": f"设备池不存在: {pool_id}"}
                )

            return ApiResponse(
                success=True,
                data={"deleted": True, "pool_id": pool_id}
            )

    except Exception as e:
        return ApiResponse(
            success=False,
            error={"code": "internal_error", "message": str(e)}
        )


@router.get("/{pool_id}/capacity", response_model=ApiResponse)
async def get_pool_capacity(
    pool_id: int = Path(..., ge=1, description="设备池ID"),
):
    """获取设备池可用容量."""
    try:
        with get_session_context() as session:
            pool_manager = PoolManager(session)
            pool = pool_manager.get_pool(pool_id)

            if not pool:
                return ApiResponse(
                    success=False,
                    error={"code": "not_found", "message": f"设备池不存在: {pool_id}"}
                )

            capacity = pool_manager.get_available_capacity(pool)

            return ApiResponse(
                success=True,
                data={
                    "pool_id": pool_id,
                    "pool_name": pool.name,
                    "available_capacity": capacity,
                    "reserved_ratio": pool.reserved_emergency_ratio,
                }
            )

    except Exception as e:
        return ApiResponse(
            success=False,
            error={"code": "internal_error", "message": str(e)}
        )