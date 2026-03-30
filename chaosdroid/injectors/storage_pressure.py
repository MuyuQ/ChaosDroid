"""存储压力注入器."""
import asyncio
import random
import re
from typing import Dict, Any

from chaosdroid.injectors.base import (
    BaseInjector,
    InjectContext,
    InjectResult
)
from chaosdroid.models.base import FaultType, RiskLevel


def _validate_path(path: str) -> bool:
    """验证路径是否安全，防止命令注入."""
    # 只允许安全字符：字母、数字、下划线、斜杠、点
    safe_pattern = r'^[a-zA-Z0-9_/.-]+$'
    if not re.match(safe_pattern, path):
        return False
    # 不允许路径遍历
    if '..' in path:
        return False
    # 路径必须以 /sdcard 或 /data 开始（Android安全路径）
    if not path.startswith('/sdcard/') and not path.startswith('/data/'):
        return False
    return True


class StoragePressureInjector(BaseInjector):
    """存储压力注入器

    向目标目录写入占位文件，模拟存储压力。
    每次注入调用独立，不维护实例状态。
    """

    fault_type = FaultType.storage_pressure
    risk_level = RiskLevel.medium

    async def prepare(self, context: InjectContext) -> bool:
        """准备注入环境"""
        executor = context.executor
        fault_profile = context.fault_profile

        # 获取压力参数（每次调用重新获取，不使用实例状态）
        params = fault_profile.get("parameters", {})
        pressure_mb = params.get("pressure_mb", 1000)  # 默认1GB压力

        # 检查设备在线和存储空间
        online = await executor.is_online()
        if not online:
            return False

        storage_info = await executor.get_storage_info()
        available_mb = storage_info.available // (1024 * 1024)

        # 检查是否有足够空间注入
        if available_mb < pressure_mb + 100:  # 需要额外100MB缓冲
            return False

        return True

    async def inject(self, context: InjectContext) -> InjectResult:
        """执行存储压力注入"""
        executor = context.executor
        fault_profile = context.fault_profile

        # 每次调用重新获取参数（不使用实例状态）
        params = fault_profile.get("parameters", {})
        pressure_mb = params.get("pressure_mb", 1000)
        target_path = params.get("target_path", "/sdcard/chaosdroid_pressure")

        # 验证路径安全性（防止命令注入）
        if not _validate_path(target_path):
            return InjectResult(
                success=False,
                fault_type=self.fault_type,
                fault_injected=False,
                fault_observed=False,
                message=f"路径验证失败: {target_path} 包含不安全字符",
                cleanup_required=False
            )

        # 获取当前存储状态
        storage_before = await executor.get_storage_info()
        available_before = storage_before.available

        # 检查是否是Mock设备
        is_mock = hasattr(executor, 'get_state')
        if is_mock:
            # Mock模式：直接修改状态
            state = executor.get_state()
            state.apply_injection("storage_pressure", {"pressure_mb": pressure_mb})

            await asyncio.sleep(random.uniform(0.5, 1.5))

            storage_after = await executor.get_storage_info()
            available_after = storage_after.available

            # 验证注入是否生效
            expected_reduction = pressure_mb * 1024 * 1024
            actual_reduction = available_before - available_after

            success = actual_reduction >= expected_reduction * 0.9  # 允许10%误差

            return InjectResult(
                success=success,
                fault_type=self.fault_type,
                fault_injected=success,
                fault_observed=True,
                message=f"Mock注入: 减少{actual_reduction // (1024*1024)}MB存储空间",
                details={
                    "pressure_mb": pressure_mb,
                    "available_before_mb": available_before // (1024 * 1024),
                    "available_after_mb": available_after // (1024 * 1024),
                    "target_path": target_path
                },
                cleanup_required=True
            )
        else:
            # Real模式：写入实际文件
            # 创建目标目录（使用单引号包裹路径防止命令注入）
            mkdir_result = await executor.execute_shell(
                f"mkdir -p '{target_path}'",
                timeout=30
            )

            if not mkdir_result.success:
                return InjectResult(
                    success=False,
                    fault_type=self.fault_type,
                    fault_injected=False,
                    fault_observed=False,
                    message=f"创建目标目录失败: {mkdir_result.stderr}",
                    cleanup_required=False
                )

            # 写入占位文件（分块写入避免单文件过大）
            chunk_size_mb = 100  # 每个100MB
            chunks = pressure_mb // chunk_size_mb
            chunks_written = 0

            for i in range(chunks):
                # 文件名使用数字索引，确保安全
                file_path = f"{target_path}/pressure_{i}.dat"
                # 使用单引号包裹路径防止命令注入
                cmd = f"dd if=/dev/zero of='{file_path}' bs=1M count={chunk_size_mb}"
                result = await executor.execute_shell(cmd, timeout=120)

                if not result.success:
                    return InjectResult(
                        success=False,
                        fault_type=self.fault_type,
                        fault_injected=False,
                        fault_observed=False,
                        message=f"写入压力文件失败: chunk {i}",
                        details={
                            "chunks_written": chunks_written,
                            "target_path": target_path
                        },
                        cleanup_required=True
                    )
                chunks_written += 1

            # 检查注入效果
            storage_after = await executor.get_storage_info()
            available_after = storage_after.available

            success = available_after < available_before

            return InjectResult(
                success=success,
                fault_type=self.fault_type,
                fault_injected=success,
                fault_observed=True,
                message=f"注入完成: 减少{pressure_mb}MB存储空间",
                details={
                    "pressure_mb": pressure_mb,
                    "available_before_mb": available_before // (1024 * 1024),
                    "available_after_mb": available_after // (1024 * 1024),
                    "target_path": target_path,
                    "chunks_written": chunks_written
                },
                cleanup_required=True
            )

    async def cleanup(self, context: InjectContext) -> bool:
        """清理注入的存储压力"""
        executor = context.executor
        fault_profile = context.fault_profile

        # 从context重新获取参数（不依赖实例状态）
        params = fault_profile.get("parameters", {})
        target_path = params.get("target_path", "/sdcard/chaosdroid_pressure")
        pressure_mb = params.get("pressure_mb", 1000)

        # 检查是否是Mock设备
        is_mock = hasattr(executor, 'get_state')
        if is_mock:
            # Mock模式：恢复状态
            state = executor.get_state()
            state.apply_recovery("cleanup_storage", {"pressure_mb": pressure_mb})
            return True

        # Real模式：删除注入文件
        # 验证路径安全性
        if not _validate_path(target_path):
            return False

        # 使用单引号包裹路径防止命令注入
        result = await executor.execute_shell(
            f"rm -rf '{target_path}'",
            timeout=60
        )

        return result.success


# 注册注入器
from chaosdroid.injectors.base import register_injector
register_injector(StoragePressureInjector())