"""低电量注入器."""
import asyncio
import random
from typing import Dict, Any

from chaosdroid.injectors.base import (
    BaseInjector,
    InjectContext,
    InjectResult
)
from chaosdroid.models.base import FaultType, RiskLevel


class LowBatteryInjector(BaseInjector):
    """低电量注入器

    模拟低电量条件，验证系统在低电量状态下的行为。
    每次注入调用独立，不维护实例状态。
    """

    fault_type = FaultType.low_battery
    risk_level = RiskLevel.low

    async def prepare(self, context: InjectContext) -> bool:
        """准备注入环境"""
        executor = context.executor
        fault_profile = context.fault_profile

        # 获取目标电量参数（每次调用重新获取）
        params = fault_profile.get("parameters", {})
        target_level = params.get("target_level", 10)  # 默认10%

        # 检查设备在线
        online = await executor.is_online()
        if not online:
            return False

        # 获取当前电量
        battery_info = await executor.get_battery_info()
        original_battery_level = battery_info.level

        # 检查是否适合注入（电量应该足够高才能模拟下降）
        if original_battery_level <= target_level:
            return True  # 已经是低电量状态

        return True

    async def inject(self, context: InjectContext) -> InjectResult:
        """执行低电量注入"""
        executor = context.executor
        fault_profile = context.fault_profile

        # 每次调用重新获取参数（不使用实例状态）
        params = fault_profile.get("parameters", {})
        target_level = params.get("target_level", 10)

        # 获取当前电池状态
        battery_before = await executor.get_battery_info()

        # 检查是否是Mock设备
        is_mock = hasattr(executor, 'get_state')
        if is_mock:
            # Mock模式：修改状态
            state = executor.get_state()
            state.apply_injection("low_battery", {"level": target_level})

            await asyncio.sleep(random.uniform(0.3, 0.8))

            battery_after = await executor.get_battery_info()

            success = battery_after.level <= target_level

            return InjectResult(
                success=success,
                fault_type=self.fault_type,
                fault_injected=success,
                fault_observed=True,
                message=f"Mock注入: 电量从{battery_before.level}%降至{battery_after.level}%",
                details={
                    "target_level": target_level,
                    "battery_before": battery_before.level,
                    "battery_after": battery_after.level
                },
                cleanup_required=True
            )
        else:
            # Real模式：读取真实低电量设备状态
            # 注意：实际设备不能通过软件降低电量，需要使用已处于低电量的设备
            return InjectResult(
                success=battery_before.level <= target_level,
                fault_type=self.fault_type,
                fault_injected=battery_before.level <= target_level,
                fault_observed=True,
                message=f"真实模式: 当前电量{battery_before.level}%，目标{target_level}%",
                details={
                    "target_level": target_level,
                    "battery_before": battery_before.level,
                    "real_mode": True,
                    "note": "真实模式需要使用已处于低电量的设备"
                },
                cleanup_required=False
            )

    async def cleanup(self, context: InjectContext) -> bool:
        """清理注入"""
        executor = context.executor

        # 检查是否是Mock设备
        is_mock = hasattr(executor, 'get_state')
        if is_mock:
            # Mock模式：恢复电量状态
            state = executor.get_state()
            state.apply_recovery("reset_battery")
            return True

        # Real模式：无法恢复电量，需要等待充电
        return True


# 注册注入器
from chaosdroid.injectors.base import register_injector
register_injector(LowBatteryInjector())