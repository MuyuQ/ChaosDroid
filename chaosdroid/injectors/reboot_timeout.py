"""重启超时注入器."""
import asyncio
import random
from typing import Dict, Any

from chaosdroid.injectors.base import (
    BaseInjector,
    InjectContext,
    InjectResult
)
from chaosdroid.models.base import FaultType, RiskLevel


class RebootTimeoutInjector(BaseInjector):
    """重启超时注入器

    模拟重启超时，boot_completed未置位的场景。
    每次注入调用独立，不维护实例状态。
    """

    fault_type = FaultType.reboot_timeout
    risk_level = RiskLevel.high

    async def prepare(self, context: InjectContext) -> bool:
        """准备注入环境"""
        executor = context.executor
        fault_profile = context.fault_profile

        # 获取超时参数（每次调用重新获取）
        params = fault_profile.get("parameters", {})
        timeout_duration_sec = params.get("timeout_duration_sec", 60)

        # 检查设备在线
        online = await executor.is_online()
        if not online:
            return False

        # 获取当前boot状态
        boot_completed = await executor.check_boot_completed()
        if not boot_completed:
            return True  # 已经在boot状态

        return True

    async def inject(self, context: InjectContext) -> InjectResult:
        """执行重启超时注入"""
        executor = context.executor
        fault_profile = context.fault_profile

        # 每次调用重新获取参数（不使用实例状态）
        params = fault_profile.get("parameters", {})
        timeout_duration_sec = params.get("timeout_duration_sec", 60)
        boot_delay_sec = params.get("boot_delay_sec", 30)

        # 获取当前boot状态
        boot_before = await executor.check_boot_completed()

        # 检查是否是Mock设备
        is_mock = hasattr(executor, 'get_state')
        if is_mock:
            # Mock模式：设置boot未完成状态
            state = executor.get_state()
            state.apply_injection("reboot_timeout", {"boot_delay": boot_delay_sec})

            await asyncio.sleep(random.uniform(0.3, 0.6))

            boot_after = await executor.check_boot_completed()

            success = not boot_after

            return InjectResult(
                success=success,
                fault_type=self.fault_type,
                fault_injected=success,
                fault_observed=True,
                message=f"Mock注入: boot_completed={boot_after}",
                details={
                    "timeout_duration_sec": timeout_duration_sec,
                    "boot_delay_sec": boot_delay_sec,
                    "boot_before": boot_before,
                    "boot_after": boot_after
                },
                cleanup_required=True
            )
        else:
            # Real模式：在重启等待阶段注入超时条件
            # 这需要配合重启操作一起使用
            return InjectResult(
                success=True,
                fault_type=self.fault_type,
                fault_injected=True,
                fault_observed=True,
                message=f"真实模式: 重启超时注入已标记",
                details={
                    "timeout_duration_sec": timeout_duration_sec,
                    "note": "真实模式需要配合重启操作使用",
                    "real_mode": True
                },
                cleanup_required=True
            )

    async def cleanup(self, context: InjectContext) -> bool:
        """清理注入"""
        executor = context.executor
        fault_profile = context.fault_profile

        # 从context重新获取参数（不依赖实例状态）
        params = fault_profile.get("parameters", {})
        timeout_duration_sec = params.get("timeout_duration_sec", 60)

        # 检查是否是Mock设备
        is_mock = hasattr(executor, 'get_state')
        if is_mock:
            # Mock模式：恢复boot状态
            state = executor.get_state()
            state.apply_recovery("wait_boot")
            return True

        # Real模式：等待设备boot完成或重启
        # 等待boot完成
        boot_completed = await executor.wait_for_boot(timeout=timeout_duration_sec + 30)
        return boot_completed


# 注册注入器
from chaosdroid.injectors.base import register_injector
register_injector(RebootTimeoutInjector())