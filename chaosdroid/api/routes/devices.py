"""Devices API routes."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List

router = APIRouter()


class DeviceInfo(BaseModel):
    """设备信息"""
    serial: str
    status: str  # online, offline, unauthorized
    model: Optional[str]
    android_version: Optional[str]
    battery_level: Optional[int]
    storage_available: Optional[int]


class DeviceCheckResult(BaseModel):
    """设备检查结果"""
    serial: str
    online: bool
    battery_ok: bool
    storage_ok: bool
    boot_completed: bool
    ready_for_test: bool
    issues: List[str]


class ApiResponse(BaseModel):
    """统一API响应格式"""
    success: bool
    data: Optional[dict] = None
    error: Optional[dict] = None


@router.get("", response_model=ApiResponse)
async def list_devices():
    """获取设备列表"""
    # TODO: 实现ADB设备列表获取
    return ApiResponse(success=True, data={"devices": []})


@router.get("/{serial}/check", response_model=ApiResponse)
async def check_device(serial: str):
    """检查设备状态"""
    # TODO: 实现设备检查逻辑
    result = DeviceCheckResult(
        serial=serial,
        online=True,
        battery_ok=True,
        storage_ok=True,
        boot_completed=True,
        ready_for_test=True,
        issues=[]
    )
    return ApiResponse(success=True, data={"check_result": result.model_dump()})