"""Devices API routes - 连接设备执行器层."""

from fastapi import APIRouter, HTTPException, Query, Path
from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum
import asyncio

from app.executors.mock_executor import MockDeviceExecutor, MockScenario
from app.executors.base import ExecutorMode, BatteryInfo, StorageInfo

router = APIRouter()


# ==================== 枚举定义 ====================

class DeviceStatusEnum(str, Enum):
    """设备状态枚举"""
    online = "online"
    offline = "offline"
    unauthorized = "unauthorized"


# ==================== 响应模型 ====================

class DeviceInfo(BaseModel):
    """设备信息"""
    serial: str
    status: DeviceStatusEnum
    model: Optional[str] = None
    brand: Optional[str] = None
    android_version: Optional[str] = None
    sdk_version: Optional[str] = None
    battery_level: Optional[int] = None
    battery_status: Optional[str] = None
    storage_total_mb: Optional[int] = None
    storage_available_mb: Optional[int] = None


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


# ==================== Mock设备管理 ====================

# 模拟设备列表（在实际场景中应从ADB获取）
_mock_devices: dict = {}


def _get_mock_device(serial: str) -> MockDeviceExecutor:
    """获取或创建Mock设备"""
    if serial not in _mock_devices:
        _mock_devices[serial] = MockDeviceExecutor(serial, MockScenario.normal)
    return _mock_devices[serial]


async def _list_mock_devices() -> List[DeviceInfo]:
    """列出所有Mock设备"""
    # 返回一些预定义的模拟设备
    default_serials = ["mock_device_001", "mock_device_002", "mock_device_003"]
    devices = []

    for serial in default_serials:
        executor = _get_mock_device(serial)

        try:
            online = await executor.is_online()
            status = DeviceStatusEnum.online if online else DeviceStatusEnum.offline

            properties = await executor.get_properties() if online else {}
            battery_info = await executor.get_battery_info() if online else None
            storage_info = await executor.get_storage_info() if online else None

            device = DeviceInfo(
                serial=serial,
                status=status,
                model=properties.get("ro.product.model"),
                brand=properties.get("ro.product.brand"),
                android_version=properties.get("ro.build.version.release"),
                sdk_version=properties.get("ro.build.version.sdk"),
                battery_level=battery_info.level if battery_info else None,
                battery_status=battery_info.status if battery_info else None,
                storage_total_mb=storage_info.total // (1024 * 1024) if storage_info else None,
                storage_available_mb=storage_info.available // (1024 * 1024) if storage_info else None,
            )
            devices.append(device)

        except Exception:
            # 设备异常时返回offline状态
            devices.append(DeviceInfo(serial=serial, status=DeviceStatusEnum.offline))

    return devices


# ==================== API端点 ====================

@router.get("", response_model=ApiResponse)
async def list_devices(
    mode: str = Query("mock", description="执行器模式: mock 或 real"),
):
    """获取设备列表"""
    try:
        if mode == ExecutorMode.mock.value:
            devices = await _list_mock_devices()
            return ApiResponse(
                success=True,
                data={
                    "devices": [d.model_dump() for d in devices],
                    "mode": mode,
                }
            )
        else:
            # Real模式需要ADB支持，目前返回空列表
            return ApiResponse(
                success=True,
                data={
                    "devices": [],
                    "mode": mode,
                    "message": "Real模式需要ADB连接，暂未实现",
                }
            )

    except Exception as e:
        return ApiResponse(
            success=False,
            error={"code": "internal_error", "message": str(e)}
        )


@router.get("/{serial}", response_model=ApiResponse)
async def get_device(
    serial: str = Path(..., min_length=1, max_length=50, description="设备序列号"),
    mode: str = Query("mock", description="执行器模式"),
):
    """获取设备详情"""
    try:
        # 验证序列号格式
        serial = serial.strip()
        if not serial:
            return ApiResponse(
                success=False,
                error={"code": "validation_error", "message": "设备序列号不能为空"}
            )

        if mode == ExecutorMode.mock.value:
            executor = _get_mock_device(serial)

            online = await executor.is_online()
            if not online:
                return ApiResponse(
                    success=True,
                    data={
                        "device": DeviceInfo(
                            serial=serial,
                            status=DeviceStatusEnum.offline,
                        ).model_dump(),
                    }
                )

            properties = await executor.get_properties()
            battery_info = await executor.get_battery_info()
            storage_info = await executor.get_storage_info()

            device = DeviceInfo(
                serial=serial,
                status=DeviceStatusEnum.online,
                model=properties.get("ro.product.model"),
                brand=properties.get("ro.product.brand"),
                android_version=properties.get("ro.build.version.release"),
                sdk_version=properties.get("ro.build.version.sdk"),
                battery_level=battery_info.level,
                battery_status=battery_info.status,
                storage_total_mb=storage_info.total // (1024 * 1024),
                storage_available_mb=storage_info.available // (1024 * 1024),
            )

            return ApiResponse(
                success=True,
                data={"device": device.model_dump()}
            )
        else:
            return ApiResponse(
                success=False,
                error={"code": "not_implemented", "message": "Real模式暂未实现"}
            )

    except Exception as e:
        return ApiResponse(
            success=False,
            error={"code": "internal_error", "message": str(e)}
        )


@router.get("/{serial}/check", response_model=ApiResponse)
async def check_device(
    serial: str = Path(..., min_length=1, max_length=50, description="设备序列号"),
    mode: str = Query("mock", description="执行器模式"),
    min_battery: int = Query(20, ge=0, le=100, description="最低电池电量要求"),
    min_storage_mb: int = Query(100, ge=10, le=10000, description="最低可用存储要求(MB)"),
):
    """检查设备状态，判断是否适合执行测试"""
    try:
        # 验证序列号
        serial = serial.strip()
        if not serial:
            return ApiResponse(
                success=False,
                error={"code": "validation_error", "message": "设备序列号不能为空"}
            )

        issues: List[str] = []

        if mode == ExecutorMode.mock.value:
            executor = _get_mock_device(serial)

            # 检查在线状态
            online = await executor.is_online()
            if not online:
                issues.append("device_offline")
                result = DeviceCheckResult(
                    serial=serial,
                    online=False,
                    battery_ok=False,
                    storage_ok=False,
                    boot_completed=False,
                    ready_for_test=False,
                    issues=issues,
                )
                return ApiResponse(
                    success=True,
                    data={"check_result": result.model_dump()}
                )

            # 检查电池
            battery_info = await executor.get_battery_info()
            battery_ok = battery_info.level >= min_battery
            if not battery_ok:
                issues.append(f"low_battery ({battery_info.level}% < {min_battery}%)")

            # 检查存储
            storage_info = await executor.get_storage_info()
            storage_available_mb = storage_info.available // (1024 * 1024)
            storage_ok = storage_available_mb >= min_storage_mb
            if not storage_ok:
                issues.append(f"storage_low ({storage_available_mb}MB < {min_storage_mb}MB)")

            # 检查启动状态
            boot_completed = await executor.check_boot_completed()
            if not boot_completed:
                issues.append("boot_not_completed")

            # 综合判断
            ready_for_test = battery_ok and storage_ok and boot_completed

            result = DeviceCheckResult(
                serial=serial,
                online=True,
                battery_ok=battery_ok,
                storage_ok=storage_ok,
                boot_completed=boot_completed,
                ready_for_test=ready_for_test,
                issues=issues,
            )

            return ApiResponse(
                success=True,
                data={"check_result": result.model_dump()}
            )
        else:
            return ApiResponse(
                success=False,
                error={"code": "not_implemented", "message": "Real模式暂未实现"}
            )

    except Exception as e:
        return ApiResponse(
            success=False,
            error={"code": "internal_error", "message": str(e)}
        )


@router.post("/{serial}/reboot", response_model=ApiResponse)
async def reboot_device(
    serial: str = Path(..., min_length=1, max_length=50, description="设备序列号"),
    mode: str = Query("mock", description="执行器模式"),
    wait_timeout: int = Query(120, ge=10, le=600, description="等待超时时间(秒)"),
):
    """重启设备"""
    try:
        serial = serial.strip()
        if not serial:
            return ApiResponse(
                success=False,
                error={"code": "validation_error", "message": "设备序列号不能为空"}
            )

        if mode == ExecutorMode.mock.value:
            executor = _get_mock_device(serial)

            # 检查设备是否在线
            online = await executor.is_online()
            if not online:
                return ApiResponse(
                    success=False,
                    error={"code": "device_offline", "message": "设备不在线，无法重启"}
                )

            # 执行重启
            success = await executor.reboot(wait_timeout)

            return ApiResponse(
                success=True,
                data={
                    "rebooted": success,
                    "serial": serial,
                    "boot_completed": await executor.check_boot_completed() if success else False,
                }
            )
        else:
            return ApiResponse(
                success=False,
                error={"code": "not_implemented", "message": "Real模式暂未实现"}
            )

    except Exception as e:
        return ApiResponse(
            success=False,
            error={"code": "internal_error", "message": str(e)}
        )


@router.get("/{serial}/logcat", response_model=ApiResponse)
async def get_device_logcat(
    serial: str = Path(..., min_length=1, max_length=50, description="设备序列号"),
    mode: str = Query("mock", description="执行器模式"),
    lines: int = Query(1000, ge=100, le=10000, description="日志行数"),
):
    """获取设备logcat日志"""
    try:
        serial = serial.strip()
        if not serial:
            return ApiResponse(
                success=False,
                error={"code": "validation_error", "message": "设备序列号不能为空"}
            )

        if mode == ExecutorMode.mock.value:
            executor = _get_mock_device(serial)

            online = await executor.is_online()
            if not online:
                return ApiResponse(
                    success=False,
                    error={"code": "device_offline", "message": "设备不在线"}
                )

            logcat = await executor.get_logcat(lines)

            return ApiResponse(
                success=True,
                data={
                    "serial": serial,
                    "lines": lines,
                    "logcat": logcat,
                }
            )
        else:
            return ApiResponse(
                success=False,
                error={"code": "not_implemented", "message": "Real模式暂未实现"}
            )

    except Exception as e:
        return ApiResponse(
            success=False,
            error={"code": "internal_error", "message": str(e)}
        )


@router.post("/{serial}/shell", response_model=ApiResponse)
async def execute_shell_command(
    serial: str = Path(..., min_length=1, max_length=50, description="设备序列号"),
    command: str = Query(..., min_length=1, max_length=500, description="Shell命令"),
    mode: str = Query("mock", description="执行器模式"),
    timeout: int = Query(30, ge=5, le=120, description="超时时间(秒)"),
):
    """在设备上执行Shell命令"""
    try:
        serial = serial.strip()
        command = command.strip()
        if not serial:
            return ApiResponse(
                success=False,
                error={"code": "validation_error", "message": "设备序列号不能为空"}
            )
        if not command:
            return ApiResponse(
                success=False,
                error={"code": "validation_error", "message": "Shell命令不能为空"}
            )

        if mode == ExecutorMode.mock.value:
            executor = _get_mock_device(serial)

            online = await executor.is_online()
            if not online:
                return ApiResponse(
                    success=False,
                    error={"code": "device_offline", "message": "设备不在线"}
                )

            result = await executor.execute_shell(command, timeout)

            return ApiResponse(
                success=result.success,
                data={
                    "serial": serial,
                    "command": command,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "exit_code": result.exit_code,
                    "duration_ms": result.duration_ms,
                }
            )
        else:
            return ApiResponse(
                success=False,
                error={"code": "not_implemented", "message": "Real模式暂未实现"}
            )

    except Exception as e:
        return ApiResponse(
            success=False,
            error={"code": "internal_error", "message": str(e)}
        )


# ==================== 调度相关端点 ====================

@router.post("/sync", response_model=ApiResponse)
async def sync_devices():
    """同步设备状态（触发设备健康检查和隔离判定）."""
    try:
        from app.models import get_session_context
        from app.scheduling import DeviceSyncService

        with get_session_context() as session:
            sync_service = DeviceSyncService(session)
            await sync_service.check_and_quarantine()

            return ApiResponse(
                success=True,
                data={"message": "设备同步完成"}
            )

    except Exception as e:
        return ApiResponse(
            success=False,
            error={"code": "internal_error", "message": str(e)}
        )


@router.post("/{device_id}/recover", response_model=ApiResponse)
async def recover_device(
    device_id: int = Path(..., ge=1, description="设备ID"),
):
    """恢复隔离设备."""
    try:
        from app.models import get_session_context, Device
        from app.scheduling import QuarantineService

        with get_session_context() as session:
            device = session.get(Device, device_id)
            if not device:
                return ApiResponse(
                    success=False,
                    error={"code": "not_found", "message": f"设备不存在: {device_id}"}
                )

            quarantine_service = QuarantineService(session)
            success = quarantine_service.recover_device(device)

            if not success:
                return ApiResponse(
                    success=False,
                    error={"code": "invalid_state", "message": "设备未处于隔离状态"}
                )

            return ApiResponse(
                success=True,
                data={
                    "device_id": device_id,
                    "serial": device.serial,
                    "status": device.status,
                    "message": "设备已恢复"
                }
            )

    except Exception as e:
        return ApiResponse(
            success=False,
            error={"code": "internal_error", "message": str(e)}
        )


@router.post("/{device_id}/quarantine", response_model=ApiResponse)
async def quarantine_device(
    device_id: int = Path(..., ge=1, description="设备ID"),
    reason: str = Query("手动隔离", description="隔离原因"),
):
    """手动隔离设备."""
    try:
        from app.models import get_session_context, Device
        from app.scheduling import QuarantineService

        with get_session_context() as session:
            device = session.get(Device, device_id)
            if not device:
                return ApiResponse(
                    success=False,
                    error={"code": "not_found", "message": f"设备不存在: {device_id}"}
                )

            quarantine_service = QuarantineService(session)
            quarantine_service.quarantine_device(device, reason)

            return ApiResponse(
                success=True,
                data={
                    "device_id": device_id,
                    "serial": device.serial,
                    "status": device.status,
                    "quarantine_reason": reason,
                    "message": "设备已隔离"
                }
            )

    except Exception as e:
        return ApiResponse(
            success=False,
            error={"code": "internal_error", "message": str(e)}
        )


@router.get("/quarantined", response_model=ApiResponse)
async def list_quarantined_devices():
    """获取隔离设备列表."""
    try:
        from app.models import get_session_context
        from app.scheduling import QuarantineService

        with get_session_context() as session:
            quarantine_service = QuarantineService(session)
            devices = quarantine_service.get_quarantined()

            return ApiResponse(
                success=True,
                data={
                    "devices": [
                        {
                            "id": d.id,
                            "serial": d.serial,
                            "status": d.status,
                            "quarantine_reason": d.quarantine_reason,
                            "health_score": d.health_score,
                        }
                        for d in devices
                    ],
                    "total": len(devices),
                }
            )

    except Exception as e:
        return ApiResponse(
            success=False,
            error={"code": "internal_error", "message": str(e)}
        )