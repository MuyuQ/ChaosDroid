"""验证器基类和结果判定."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional, List


@dataclass
class ValidationContext:
    """验证上下文"""
    scenario_run_id: int
    device_serial: str
    executor: Any  # BaseDeviceExecutor
    validation_profile: Dict[str, Any]
    artifacts_dir: str
    inject_result: Optional[Dict[str, Any]] = None
    started_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class CheckResult:
    """单项检查结果"""
    check_name: str
    passed: bool
    expected: Any
    actual: Any
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    """验证结果"""
    passed: bool
    checks: List[CheckResult] = field(default_factory=list)
    fault_observed: bool = False
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def add_check(self, check: CheckResult):
        """添加检查结果"""
        self.checks.append(check)

    def get_summary(self) -> Dict[str, Any]:
        """获取摘要"""
        passed_count = sum(1 for c in self.checks if c.passed)
        return {
            "passed": self.passed,
            "fault_observed": self.fault_observed,
            "total_checks": len(self.checks),
            "passed_checks": passed_count,
            "failed_checks": len(self.checks) - passed_count,
            "checks": [c.model_dump() for c in self.checks]
        }


class BaseValidator(ABC):
    """验证器基类"""

    @abstractmethod
    async def validate(self, context: ValidationContext) -> ValidationResult:
        """执行验证"""
        pass

    async def check_boot_completed(self, executor) -> CheckResult:
        """检查boot完成"""
        try:
            result = await executor.execute_shell("getprop sys.boot_completed")
            boot_completed = result.stdout.strip() == "1"
            return CheckResult(
                check_name="boot_completed",
                passed=boot_completed,
                expected="1",
                actual=result.stdout.strip(),
                message=boot_completed and "Boot完成" or "Boot未完成"
            )
        except Exception as e:
            return CheckResult(
                check_name="boot_completed",
                passed=False,
                expected="1",
                actual="error",
                message=f"检查失败: {str(e)}"
            )

    async def check_battery_ok(self, executor, min_level: int = 20) -> CheckResult:
        """检查电池电量"""
        try:
            battery_info = await executor.get_battery_info()
            passed = battery_info.level >= min_level
            return CheckResult(
                check_name="battery_level",
                passed=passed,
                expected=f">={min_level}",
                actual=str(battery_info.level),
                message=passed and f"电量正常({battery_info.level}%)" or f"电量过低({battery_info.level}%)"
            )
        except Exception as e:
            return CheckResult(
                check_name="battery_level",
                passed=False,
                expected=f">={min_level}",
                actual="error",
                message=f"检查失败: {str(e)}"
            )

    async def check_storage_ok(self, executor, min_available: int = 100 * 1024 * 1024) -> CheckResult:
        """检查存储空间"""
        try:
            storage_info = await executor.get_storage_info()
            passed = storage_info.available >= min_available
            return CheckResult(
                check_name="storage_available",
                passed=passed,
                expected=f">={min_available // (1024*1024)}MB",
                actual=f"{storage_info.available // (1024*1024)}MB",
                message=passed and "存储空间充足" or "存储空间不足"
            )
        except Exception as e:
            return CheckResult(
                check_name="storage_available",
                passed=False,
                expected=f">={min_available // (1024*1024)}MB",
                actual="error",
                message=f"检查失败: {str(e)}"
            )

    async def check_device_online(self, executor) -> CheckResult:
        """检查设备在线"""
        try:
            online = await executor.is_online()
            return CheckResult(
                check_name="device_online",
                passed=online,
                expected="online",
                actual=online and "online" or "offline",
                message=online and "设备在线" or "设备离线"
            )
        except Exception as e:
            return CheckResult(
                check_name="device_online",
                passed=False,
                expected="online",
                actual="error",
                message=f"检查失败: {str(e)}"
            )


class DefaultValidator(BaseValidator):
    """默认验证器"""

    def __init__(self, checks_config: Optional[Dict[str, Any]] = None):
        self.checks_config = checks_config or {}

    async def validate(self, context: ValidationContext) -> ValidationResult:
        """执行验证"""
        result = ValidationResult(passed=True)
        executor = context.executor

        # 执行基础检查
        boot_check = await self.check_boot_completed(executor)
        result.add_check(boot_check)

        battery_check = await self.check_battery_ok(executor)
        result.add_check(battery_check)

        storage_check = await self.check_storage_ok(executor)
        result.add_check(storage_check)

        online_check = await self.check_device_online(executor)
        result.add_check(online_check)

        # 根据注入结果判断故障是否被观测到
        inject_result = context.inject_result
        if inject_result and inject_result.get("success"):
            result.fault_observed = True
            result.details["fault_injected"] = inject_result.get("fault_injected")

        # 综合判定
        result.passed = all(c.passed for c in result.checks) or result.fault_observed
        result.message = result.passed and "验证通过" or "验证失败"

        return result


@dataclass
class JudgmentResult:
    """最终判定结果"""
    fault_injected: bool
    fault_observed: bool
    validation_passed: bool
    recovery_passed: bool
    risk_level: str
    manual_action_required: bool
    final_status: str  # passed/failed/partial
    message: str = ""

    def determine_final_status(self) -> str:
        """确定最终状态"""
        if not self.fault_injected:
            return "failed"

        if self.fault_injected and self.validation_passed and self.recovery_passed:
            return "passed"

        if self.fault_injected and not self.validation_passed and self.recovery_passed:
            return "failed"

        if self.fault_injected and self.validation_passed and not self.recovery_passed:
            return "partial"

        return "failed"


def judge_result(
    inject_result: Optional[Dict[str, Any]],
    validation_result: Optional[ValidationResult],
    recovery_result: Optional[Dict[str, Any]],
    risk_level: str = "medium"
) -> JudgmentResult:
    """综合判定结果"""
    fault_injected = inject_result and inject_result.get("success", False)
    fault_observed = validation_result and validation_result.fault_observed
    validation_passed = validation_result and validation_result.passed
    recovery_passed = recovery_result and recovery_result.get("passed", True)

    judgment = JudgmentResult(
        fault_injected=fault_injected,
        fault_observed=fault_observed,
        validation_passed=validation_passed,
        recovery_passed=recovery_passed,
        risk_level=risk_level,
        manual_action_required=not recovery_passed
    )

    judgment.final_status = judgment.determine_final_status()
    judgment.message = f"注入:{fault_injected and '成功' or '失败'}, 验证:{validation_passed and '通过' or '失败'}, 恢复:{recovery_passed and '成功' or '失败'}"

    return judgment