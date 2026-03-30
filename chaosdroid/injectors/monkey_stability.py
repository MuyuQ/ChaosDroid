"""Monkey稳定性注入器."""
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


def _validate_package_name(package: str) -> bool:
    """验证包名是否安全，防止命令注入."""
    # Android包名格式：字母、数字、点、下划线
    safe_pattern = r'^[a-zA-Z0-9_.]+$'
    if not re.match(safe_pattern, package):
        return False
    # 包名不能太长
    if len(package) > 256:
        return False
    return True


class MonkeyStabilityInjector(BaseInjector):
    """Monkey稳定性注入器

    启动monkey测试，采集输出统计crash/ANR。
    每次注入调用独立，不维护实例状态。
    """

    fault_type = FaultType.monkey_stability
    risk_level = RiskLevel.medium

    async def prepare(self, context: InjectContext) -> bool:
        """准备注入环境"""
        executor = context.executor
        fault_profile = context.fault_profile

        # 获取monkey参数（每次调用重新获取）
        params = fault_profile.get("parameters", {})
        package = params.get("package", "")
        event_count = params.get("event_count", 1000)
        seed = params.get("seed", random.randint(1, 10000))
        throttle_ms = params.get("throttle_ms", 50)
        options = params.get("options", {})

        # 检查设备在线
        online = await executor.is_online()
        if not online:
            return False

        # 如果指定了包名，验证并检查包是否存在
        if package:
            if not _validate_package_name(package):
                return False
            # 使用pm list packages检查包是否存在（包名已验证，相对安全）
            result = await executor.execute_shell(f"pm list packages | grep '{package}'", timeout=30)
            if not result.stdout.strip():
                return False

        return True

    async def inject(self, context: InjectContext) -> InjectResult:
        """执行Monkey稳定性注入"""
        executor = context.executor
        fault_profile = context.fault_profile

        # 每次调用重新获取参数（不使用实例状态）
        params = fault_profile.get("parameters", {})
        package = params.get("package", "")
        event_count = params.get("event_count", 1000)
        seed = params.get("seed", random.randint(1, 10000))
        throttle_ms = params.get("throttle_ms", 50)
        options = params.get("options", {})

        # 检查是否是Mock设备
        is_mock = hasattr(executor, 'get_state')
        if is_mock:
            # Mock模式：模拟monkey运行结果
            await asyncio.sleep(random.uniform(2.0, 5.0))

            # 模拟运行monkey
            monkey_result = await executor.run_monkey(
                package or "com.mock.package",
                event_count,
                {
                    "seed": seed,
                    "throttle": throttle_ms
                }
            )

            # 分析结果
            crash_count = monkey_result.crash_count
            anr_count = monkey_result.anr_count

            # 判断稳定性（根据配置）
            max_crashes = options.get("max_crashes_allowed", 0)
            max_anrs = options.get("max_anrs_allowed", 0)

            success = crash_count <= max_crashes and anr_count <= max_anrs

            return InjectResult(
                success=success,
                fault_type=self.fault_type,
                fault_injected=True,
                fault_observed=True,
                message=f"Mock注入: Monkey完成，crash={crash_count}, ANR={anr_count}",
                details={
                    "package": package,
                    "event_count": event_count,
                    "seed": seed,
                    "throttle_ms": throttle_ms,
                    "crash_count": crash_count,
                    "anr_count": anr_count,
                    "total_events": monkey_result.total_events,
                    "duration_ms": monkey_result.duration_ms,
                    "stability_passed": success
                },
                cleanup_required=False
            )
        else:
            # Real模式：运行实际monkey
            monkey_result = await executor.run_monkey(
                package,
                event_count,
                {
                    "seed": seed,
                    "throttle": throttle_ms
                }
            )

            # 分析结果
            crash_count = self._parse_crashes(monkey_result.output)
            anr_count = self._parse_anrs(monkey_result.output)

            # 判断稳定性
            max_crashes = options.get("max_crashes_allowed", 0)
            max_anrs = options.get("max_anrs_allowed", 0)

            success = crash_count <= max_crashes and anr_count <= max_anrs

            return InjectResult(
                success=success,
                fault_type=self.fault_type,
                fault_injected=True,
                fault_observed=True,
                message=f"真实模式: Monkey完成，crash={crash_count}, ANR={anr_count}",
                details={
                    "package": package,
                    "event_count": event_count,
                    "seed": seed,
                    "throttle_ms": throttle_ms,
                    "crash_count": crash_count,
                    "anr_count": anr_count,
                    "total_events": monkey_result.total_events,
                    "duration_ms": monkey_result.duration_ms,
                    "stability_passed": success,
                    "real_mode": True
                },
                cleanup_required=False
            )

    def _parse_crashes(self, output: str) -> int:
        """解析monkey输出中的crash数量"""
        # 查找crash相关的模式
        crash_patterns = [
            r"// CRASH:",
            r"\*\* Monkey aborted due to crash",
            r"CRASH:\s*\d+"
        ]
        count = 0
        for pattern in crash_patterns:
            matches = re.findall(pattern, output)
            count += len(matches)
        return count

    def _parse_anrs(self, output: str) -> int:
        """解析monkey输出中的ANR数量"""
        # 查找ANR相关的模式
        anr_patterns = [
            r"// ANR:",
            r"ANR in",
            r"ANR:\s*\d+"
        ]
        count = 0
        for pattern in anr_patterns:
            matches = re.findall(pattern, output)
            count += len(matches)
        return count

    async def cleanup(self, context: InjectContext) -> bool:
        """清理注入"""
        # Monkey测试不需要清理，测试完成后自动结束
        return True


# 注册注入器
from chaosdroid.injectors.base import register_injector
register_injector(MonkeyStabilityInjector())