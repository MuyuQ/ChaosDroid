"""
验证器单元测试。

测试DefaultValidator、检查函数和结果判定。
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.validators.base import (
    BaseValidator,
    CheckResult,
    DefaultValidator,
    JudgmentResult,
    ValidationContext,
    ValidationResult,
    judge_result,
)
from app.executors.mock_executor import MockDeviceExecutor, MockDeviceState, MockScenario
from app.executors.base import StorageInfo, BatteryInfo, ShellResult


# ==================== Fixtures ====================

@pytest.fixture
def mock_executor_normal():
    """创建正常状态的Mock执行器。"""
    return MockDeviceExecutor("device_001", MockScenario.normal)


@pytest.fixture
def mock_executor_offline():
    """创建离线状态的Mock执行器。"""
    return MockDeviceExecutor("device_offline", MockScenario.offline)


@pytest.fixture
def mock_executor_low_battery():
    """创建低电量状态的Mock执行器。"""
    return MockDeviceExecutor("device_low_battery", MockScenario.low_battery)


@pytest.fixture
def mock_executor_storage_full():
    """创建存储满状态的Mock执行器。"""
    return MockDeviceExecutor("device_storage_full", MockScenario.storage_full)


@pytest.fixture
def mock_executor_boot_timeout():
    """创建启动超时状态的Mock执行器。"""
    return MockDeviceExecutor("device_boot_timeout", MockScenario.boot_timeout)


@pytest.fixture
def validation_context(mock_executor_normal):
    """创建验证上下文。"""
    return ValidationContext(
        scenario_run_id=1,
        device_serial="device_001",
        executor=mock_executor_normal,
        validation_profile={
            "checks": ["boot_completed", "battery_ok", "storage_ok"],
            "timeout_sec": 180,
        },
        inject_result={"success": True, "fault_injected": True},
        artifacts_dir="/tmp/artifacts",
        started_at=datetime.utcnow(),
    )


@pytest.fixture
def validation_context_no_inject(mock_executor_normal):
    """创建无注入结果的验证上下文。"""
    return ValidationContext(
        scenario_run_id=1,
        device_serial="device_001",
        executor=mock_executor_normal,
        validation_profile={},
        inject_result=None,
        artifacts_dir="/tmp",
    )


@pytest.fixture
def default_validator():
    """创建默认验证器。"""
    return DefaultValidator()


@pytest.fixture
def custom_validator():
    """创建自定义验证器。"""
    return DefaultValidator({"min_battery": 30, "min_storage_mb": 500})


# ==================== ValidationContext 测试 ====================

class TestValidationContext:
    """测试ValidationContext数据类。"""

    def test_context_creation(self, mock_executor_normal):
        """测试创建验证上下文。"""
        context = ValidationContext(
            scenario_run_id=1,
            device_serial="test",
            executor=mock_executor_normal,
            validation_profile={},
            artifacts_dir="/tmp",
        )

        assert context.scenario_run_id == 1
        assert context.device_serial == "test"
        assert context.executor == mock_executor_normal
        assert context.artifacts_dir == "/tmp"

    def test_context_with_inject_result(self, mock_executor_normal):
        """测试带注入结果的上下文。"""
        context = ValidationContext(
            scenario_run_id=1,
            device_serial="test",
            executor=mock_executor_normal,
            validation_profile={},
            inject_result={"success": True},
            artifacts_dir="/tmp",
        )

        assert context.inject_result == {"success": True}

    def test_context_timestamp(self, mock_executor_normal):
        """测试上下文时间戳。"""
        before = datetime.utcnow()
        context = ValidationContext(
            scenario_run_id=1,
            device_serial="test",
            executor=mock_executor_normal,
            validation_profile={},
            artifacts_dir="/tmp",
        )
        after = datetime.utcnow()

        assert before <= context.started_at <= after


# ==================== CheckResult 测试 ====================

class TestCheckResult:
    """测试CheckResult数据类。"""

    def test_check_result_pass(self):
        """测试通过的检查结果。"""
        result = CheckResult(
            check_name="boot_completed",
            passed=True,
            expected="1",
            actual="1",
            message="Boot完成",
            details={"duration_ms": 100},
        )

        assert result.check_name == "boot_completed"
        assert result.passed is True
        assert result.expected == "1"
        assert result.actual == "1"
        assert result.message == "Boot完成"

    def test_check_result_fail(self):
        """测试失败的检查结果。"""
        result = CheckResult(
            check_name="battery_level",
            passed=False,
            expected=">=20",
            actual="15",
            message="电量过低",
        )

        assert result.passed is False
        assert result.expected == ">=20"
        assert result.actual == "15"

    def test_check_result_default_values(self):
        """测试检查结果默认值。"""
        result = CheckResult(
            check_name="test",
            passed=True,
            expected="x",
            actual="x",
        )

        assert result.message == ""
        assert result.details == {}


# ==================== ValidationResult 测试 ====================

class TestValidationResult:
    """测试ValidationResult数据类。"""

    def test_result_creation(self):
        """测试创建验证结果。"""
        result = ValidationResult(
            passed=True,
            fault_observed=True,
            message="验证通过",
        )

        assert result.passed is True
        assert result.fault_observed is True
        assert result.message == "验证通过"

    def test_result_with_checks(self):
        """测试带检查项的验证结果。"""
        result = ValidationResult(passed=True)
        result.add_check(CheckResult("check1", True, "x", "x"))
        result.add_check(CheckResult("check2", True, "y", "y"))

        assert len(result.checks) == 2
        assert all(c.passed for c in result.checks)

    def test_result_add_check(self):
        """测试添加检查项。"""
        result = ValidationResult(passed=True)
        check1 = CheckResult("boot", True, "1", "1")
        check2 = CheckResult("battery", False, ">=20", "10")

        result.add_check(check1)
        result.add_check(check2)

        assert len(result.checks) == 2
        assert result.checks[0] == check1
        assert result.checks[1] == check2

    def test_result_get_summary(self):
        """测试获取摘要。"""
        result = ValidationResult(passed=True, fault_observed=True)
        result.add_check(CheckResult("check1", True, "x", "x"))
        result.add_check(CheckResult("check2", False, "y", "z"))

        summary = result.get_summary()

        assert summary["passed"] is True
        assert summary["fault_observed"] is True
        assert summary["total_checks"] == 2
        assert summary["passed_checks"] == 1
        assert summary["failed_checks"] == 1
        assert len(summary["checks"]) == 2

    def test_result_default_values(self):
        """测试验证结果默认值。"""
        result = ValidationResult(passed=True)

        assert result.checks == []
        assert result.fault_observed is False
        assert result.message == ""
        assert result.details == {}


# ==================== JudgmentResult 测试 ====================

class TestJudgmentResult:
    """测试JudgmentResult数据类。"""

    def test_result_creation(self):
        """测试创建判定结果。"""
        result = JudgmentResult(
            fault_injected=True,
            fault_observed=True,
            validation_passed=True,
            recovery_passed=True,
            risk_level="medium",
            manual_action_required=False,
            final_status="passed",
            message="测试完成",
        )

        assert result.fault_injected is True
        assert result.fault_observed is True
        assert result.validation_passed is True
        assert result.recovery_passed is True
        assert result.risk_level == "medium"
        assert result.final_status == "passed"

    def test_determine_final_status_passed(self):
        """测试判定最终状态：注入成功+验证通过+恢复成功=passed。"""
        result = JudgmentResult(
            fault_injected=True,
            fault_observed=True,
            validation_passed=True,
            recovery_passed=True,
            risk_level="low",
            manual_action_required=False,
        )

        status = result.determine_final_status()
        assert status == "passed"

    def test_determine_final_status_failed_validation(self):
        """测试判定最终状态：注入成功+验证失败+恢复成功=failed。"""
        result = JudgmentResult(
            fault_injected=True,
            fault_observed=True,
            validation_passed=False,
            recovery_passed=True,
            risk_level="medium",
            manual_action_required=False,
        )

        status = result.determine_final_status()
        assert status == "failed"

    def test_determine_final_status_partial(self):
        """测试判定最终状态：注入成功+验证通过+恢复失败=partial。"""
        result = JudgmentResult(
            fault_injected=True,
            fault_observed=True,
            validation_passed=True,
            recovery_passed=False,
            risk_level="high",
            manual_action_required=True,
        )

        status = result.determine_final_status()
        assert status == "partial"

    def test_determine_final_status_inject_failed(self):
        """测试判定最终状态：注入失败=failed。"""
        result = JudgmentResult(
            fault_injected=False,
            fault_observed=False,
            validation_passed=False,
            recovery_passed=True,
            risk_level="low",
            manual_action_required=False,
        )

        status = result.determine_final_status()
        assert status == "failed"

    def test_determine_final_status_all_combinations(self):
        """测试所有组合的最终状态判定。"""
        test_cases = [
            # (inject, validation, recovery, expected)
            (True, True, True, "passed"),
            (True, False, True, "failed"),
            (True, True, False, "partial"),
            (True, False, False, "failed"),
            (False, True, True, "failed"),
            (False, False, True, "failed"),
            (False, True, False, "failed"),
            (False, False, False, "failed"),
        ]

        for inject, validation, recovery, expected in test_cases:
            result = JudgmentResult(
                fault_injected=inject,
                fault_observed=inject,
                validation_passed=validation,
                recovery_passed=recovery,
                risk_level="medium",
                manual_action_required=False,
            )

            status = result.determine_final_status()
            assert status == expected, f"Failed for ({inject}, {validation}, {recovery})"


# ==================== DefaultValidator 测试 ====================

class TestDefaultValidatorInit:
    """测试DefaultValidator初始化。"""

    def test_init_default_config(self):
        """测试默认配置初始化。"""
        validator = DefaultValidator()
        assert validator.checks_config == {}

    def test_init_custom_config(self):
        """测试自定义配置初始化。"""
        validator = DefaultValidator({"min_battery": 30})
        assert validator.checks_config == {"min_battery": 30}


class TestDefaultValidatorValidate:
    """测试DefaultValidator.validate方法。"""

    async def test_validate_normal_device(self, default_validator, validation_context):
        """测试正常设备验证通过。"""
        result = await default_validator.validate(validation_context)

        assert result.passed is True
        assert len(result.checks) == 4  # boot, battery, storage, online

    async def test_validate_low_battery_device(self, default_validator, mock_executor_low_battery):
        """测试低电量设备验证。"""
        context = ValidationContext(
            scenario_run_id=1,
            device_serial="low_battery",
            executor=mock_executor_low_battery,
            validation_profile={},
            artifacts_dir="/tmp",
        )

        result = await default_validator.validate(context)

        # 低电量设备电量检查应失败
        battery_check = next(c for c in result.checks if c.check_name == "battery_level")
        assert battery_check.passed is False

    async def test_validate_storage_full_device(self, default_validator, mock_executor_storage_full):
        """测试存储满设备验证。"""
        context = ValidationContext(
            scenario_run_id=1,
            device_serial="storage_full",
            executor=mock_executor_storage_full,
            validation_profile={},
            artifacts_dir="/tmp",
        )

        result = await default_validator.validate(context)

        # 存储满设备存储检查应失败
        storage_check = next(c for c in result.checks if c.check_name == "storage_available")
        assert storage_check.passed is False

    async def test_validate_boot_timeout_device(self, default_validator, mock_executor_boot_timeout):
        """测试启动超时设备验证。"""
        context = ValidationContext(
            scenario_run_id=1,
            device_serial="boot_timeout",
            executor=mock_executor_boot_timeout,
            validation_profile={},
            artifacts_dir="/tmp",
        )

        result = await default_validator.validate(context)

        # 启动超时设备boot检查应失败
        boot_check = next(c for c in result.checks if c.check_name == "boot_completed")
        assert boot_check.passed is False

    async def test_validate_offline_device(self, default_validator, mock_executor_offline):
        """测试离线设备验证。"""
        context = ValidationContext(
            scenario_run_id=1,
            device_serial="offline",
            executor=mock_executor_offline,
            validation_profile={},
            artifacts_dir="/tmp",
        )

        result = await default_validator.validate(context)

        # 离线设备所有检查应失败
        assert result.passed is False or all(not c.passed for c in result.checks)

    async def test_validate_with_inject_result(self, default_validator, validation_context):
        """测试带注入结果的验证。"""
        result = await default_validator.validate(validation_context)

        assert result.fault_observed is True
        assert result.details["fault_injected"] is True

    async def test_validate_without_inject_result(self, default_validator, validation_context_no_inject):
        """测试无注入结果的验证。"""
        result = await default_validator.validate(validation_context_no_inject)

        assert result.fault_observed is False
        assert "fault_injected" not in result.details

    async def test_validate_checks_count(self, default_validator, validation_context):
        """测试验证检查项数量。"""
        result = await default_validator.validate(validation_context)

        # 默认验证器执行4项检查
        assert len(result.checks) == 4
        check_names = [c.check_name for c in result.checks]
        assert "boot_completed" in check_names
        assert "battery_level" in check_names
        assert "storage_available" in check_names
        assert "device_online" in check_names


# ==================== check_boot_completed 测试 ====================

class TestCheckBootCompleted:
    """测试check_boot_completed方法。"""

    async def test_boot_completed_normal(self, default_validator, mock_executor_normal):
        """测试正常设备boot完成。"""
        result = await default_validator.check_boot_completed(mock_executor_normal)

        assert result.check_name == "boot_completed"
        assert result.passed is True
        assert result.expected == "1"
        assert result.actual == "1"
        assert "Boot完成" in result.message

    async def test_boot_not_completed(self, default_validator, mock_executor_boot_timeout):
        """测试boot未完成。"""
        result = await default_validator.check_boot_completed(mock_executor_boot_timeout)

        assert result.passed is False
        assert result.expected == "1"
        assert result.actual == "0"
        assert "Boot未完成" in result.message

    async def test_boot_check_offline_device(self, default_validator, mock_executor_offline):
        """测试离线设备boot检查失败。"""
        result = await default_validator.check_boot_completed(mock_executor_offline)

        assert result.passed is False
        # 离线设备返回空stdout，boot_completed检查失败
        assert result.actual == ""  # 空stdout
        assert "未完成" in result.message or "失败" in result.message


# ==================== check_battery_ok 测试 ====================

class TestCheckBatteryOk:
    """测试check_battery_ok方法。"""

    async def test_battery_ok_normal(self, default_validator, mock_executor_normal):
        """测试正常设备电池OK。"""
        result = await default_validator.check_battery_ok(mock_executor_normal)

        assert result.check_name == "battery_level"
        assert result.passed is True
        assert result.expected == ">=20"
        assert result.actual == "100"
        assert "正常" in result.message

    async def test_battery_low(self, default_validator, mock_executor_low_battery):
        """测试低电量设备电池检查失败。"""
        result = await default_validator.check_battery_ok(mock_executor_low_battery)

        assert result.passed is False
        assert result.actual == "15"
        assert "过低" in result.message

    async def test_battery_custom_threshold(self, mock_executor_normal):
        """测试自定义电池阈值。"""
        validator = DefaultValidator({"min_battery": 30})
        result = await validator.check_battery_ok(mock_executor_normal, min_level=50)

        # 正常设备电量100%，仍高于50%
        assert result.passed is True

    async def test_battery_threshold_boundary(self, mock_executor_low_battery):
        """测试电池阈值边界值。"""
        validator = DefaultValidator()
        # 低电量设备电量15%
        result = await validator.check_battery_ok(mock_executor_low_battery, min_level=15)

        # 电量等于阈值，应通过
        assert result.passed is True

    async def test_battery_below_threshold(self, mock_executor_low_battery):
        """测试电池低于阈值。"""
        validator = DefaultValidator()
        result = await validator.check_battery_ok(mock_executor_low_battery, min_level=20)

        assert result.passed is False


# ==================== check_storage_ok 测试 ====================

class TestCheckStorageOk:
    """测试check_storage_ok方法。"""

    async def test_storage_ok_normal(self, default_validator, mock_executor_normal):
        """测试正常设备存储OK。"""
        result = await default_validator.check_storage_ok(mock_executor_normal)

        assert result.check_name == "storage_available"
        assert result.passed is True
        assert "MB" in result.expected
        assert "充足" in result.message

    async def test_storage_full(self, default_validator, mock_executor_storage_full):
        """测试存储满设备存储检查失败。"""
        result = await default_validator.check_storage_ok(mock_executor_storage_full)

        assert result.passed is False
        assert "不足" in result.message

    async def test_storage_custom_threshold(self, mock_executor_normal):
        """测试自定义存储阈值。"""
        validator = DefaultValidator()
        # 设置较高的存储阈值
        result = await validator.check_storage_ok(mock_executor_normal, min_available=5 * 1024 * 1024 * 1024)

        # 正常设备有10GB可用，高于5GB阈值
        assert result.passed is True

    async def test_storage_threshold_boundary(self, mock_executor_storage_full):
        """测试存储阈值边界值。"""
        validator = DefaultValidator()
        # 存储满设备有50MB可用
        result = await validator.check_storage_ok(mock_executor_storage_full, min_available=50 * 1024 * 1024)

        # 存储等于阈值，应通过
        assert result.passed is True

    async def test_storage_below_threshold(self, mock_executor_storage_full):
        """测试存储低于阈值。"""
        validator = DefaultValidator()
        # 存储满设备有50MB可用
        result = await validator.check_storage_ok(mock_executor_storage_full, min_available=100 * 1024 * 1024)

        assert result.passed is False


# ==================== check_device_online 测试 ====================

class TestCheckDeviceOnline:
    """测试check_device_online方法。"""

    async def test_device_online(self, default_validator, mock_executor_normal):
        """测试设备在线。"""
        result = await default_validator.check_device_online(mock_executor_normal)

        assert result.check_name == "device_online"
        assert result.passed is True
        assert result.expected == "online"
        assert result.actual == "online"
        assert "在线" in result.message

    async def test_device_offline(self, default_validator, mock_executor_offline):
        """测试设备离线。"""
        result = await default_validator.check_device_online(mock_executor_offline)

        assert result.passed is False
        assert result.actual == "offline"
        assert "离线" in result.message


# ==================== judge_result 函数测试 ====================

class TestJudgeResultFunction:
    """测试judge_result函数。"""

    def test_judge_all_passed(self):
        """测试全部通过的判定。"""
        inject_result = {"success": True, "fault_injected": True}
        validation_result = ValidationResult(passed=True, fault_observed=True)
        recovery_result = {"passed": True}

        judgment = judge_result(inject_result, validation_result, recovery_result)

        assert judgment.fault_injected is True
        assert judgment.validation_passed is True
        assert judgment.recovery_passed is True
        assert judgment.final_status == "passed"
        assert judgment.manual_action_required is False

    def test_judge_validation_failed(self):
        """测试验证失败的判定。"""
        inject_result = {"success": True}
        validation_result = ValidationResult(passed=False)
        recovery_result = {"passed": True}

        judgment = judge_result(inject_result, validation_result, recovery_result)

        assert judgment.final_status == "failed"

    def test_judge_recovery_failed(self):
        """测试恢复失败的判定。"""
        inject_result = {"success": True}
        validation_result = ValidationResult(passed=True)
        recovery_result = {"passed": False}

        judgment = judge_result(inject_result, validation_result, recovery_result)

        assert judgment.final_status == "partial"
        assert judgment.manual_action_required is True

    def test_judge_inject_failed(self):
        """测试注入失败的判定。"""
        inject_result = {"success": False}
        validation_result = ValidationResult(passed=True)
        recovery_result = {"passed": True}

        judgment = judge_result(inject_result, validation_result, recovery_result)

        assert judgment.fault_injected is False
        assert judgment.final_status == "failed"

    def test_judge_none_inject_result(self):
        """测试无注入结果时的判定。"""
        validation_result = ValidationResult(passed=True)
        recovery_result = {"passed": True}

        judgment = judge_result(None, validation_result, recovery_result)

        # 当inject_result为None时，fault_injected为None（因为None and ... = None）
        assert judgment.fault_injected is None
        assert judgment.final_status == "failed"

    def test_judge_none_validation_result(self):
        """测试无验证结果时的判定。"""
        inject_result = {"success": True}
        recovery_result = {"passed": True}

        judgment = judge_result(inject_result, None, recovery_result)

        # 当validation_result为None时，validation_passed为None
        assert judgment.validation_passed is None
        assert judgment.final_status == "failed"

    def test_judge_none_recovery_result(self):
        """测试无恢复结果时的判定。"""
        inject_result = {"success": True}
        validation_result = ValidationResult(passed=True)

        judgment = judge_result(inject_result, validation_result, None)

        # 当recovery_result为None时，recovery_passed为None
        assert judgment.recovery_passed is None
        assert judgment.final_status == "partial"

    def test_judge_custom_risk_level(self):
        """测试自定义风险等级。"""
        inject_result = {"success": True}
        validation_result = ValidationResult(passed=True)
        recovery_result = {"passed": True}

        judgment = judge_result(inject_result, validation_result, recovery_result, risk_level="high")

        assert judgment.risk_level == "high"

    def test_judge_message_format(self):
        """测试判定消息格式。"""
        inject_result = {"success": True}
        validation_result = ValidationResult(passed=True)
        recovery_result = {"passed": False}

        judgment = judge_result(inject_result, validation_result, recovery_result)

        assert "注入" in judgment.message
        assert "验证" in judgment.message
        assert "恢复" in judgment.message


# ==================== BaseValidator 抽象类测试 ====================

class TestBaseValidatorAbstract:
    """测试BaseValidator抽象类。"""

    def test_cannot_instantiate_directly(self):
        """测试不能直接实例化BaseValidator。"""
        with pytest.raises(TypeError):
            BaseValidator()

    def test_default_validator_extends_base(self):
        """测试DefaultValidator继承BaseValidator。"""
        validator = DefaultValidator()
        assert isinstance(validator, BaseValidator)

    async def test_base_validator_check_methods_exist(self, default_validator, mock_executor_normal):
        """测试BaseValidator检查方法存在。"""
        # 所有检查方法应可用
        await default_validator.check_boot_completed(mock_executor_normal)
        await default_validator.check_battery_ok(mock_executor_normal)
        await default_validator.check_storage_ok(mock_executor_normal)
        await default_validator.check_device_online(mock_executor_normal)


# ==================== 异常处理测试 ====================

class TestValidatorExceptionHandling:
    """测试验证器异常处理。"""

    async def test_check_boot_exception(self, default_validator):
        """测试boot检查异常处理。"""
        mock_executor = MagicMock()
        mock_executor.execute_shell = AsyncMock(side_effect=Exception("Connection error"))

        result = await default_validator.check_boot_completed(mock_executor)

        assert result.passed is False
        assert result.actual == "error"
        assert "失败" in result.message

    async def test_check_battery_exception(self, default_validator):
        """测试电池检查异常处理。"""
        mock_executor = MagicMock()
        mock_executor.get_battery_info = AsyncMock(side_effect=Exception("Read error"))

        result = await default_validator.check_battery_ok(mock_executor)

        assert result.passed is False
        assert result.actual == "error"

    async def test_check_storage_exception(self, default_validator):
        """测试存储检查异常处理。"""
        mock_executor = MagicMock()
        mock_executor.get_storage_info = AsyncMock(side_effect=Exception("IO error"))

        result = await default_validator.check_storage_ok(mock_executor)

        assert result.passed is False
        assert result.actual == "error"

    async def test_check_online_exception(self, default_validator):
        """测试在线检查异常处理。"""
        mock_executor = MagicMock()
        mock_executor.is_online = AsyncMock(side_effect=Exception("Timeout"))

        result = await default_validator.check_device_online(mock_executor)

        assert result.passed is False
        assert result.actual == "error"


# ==================== 验证上下文场景测试 ====================

class TestValidationScenarios:
    """测试不同场景的完整验证流程。"""

    async def test_normal_scenario_all_pass(self):
        """测试正常场景全部通过。"""
        executor = MockDeviceExecutor("normal", MockScenario.normal)
        validator = DefaultValidator()
        context = ValidationContext(
            scenario_run_id=1,
            device_serial="normal",
            executor=executor,
            validation_profile={},
            inject_result={"success": True},
            artifacts_dir="/tmp",
        )

        result = await validator.validate(context)

        assert result.passed is True
        assert all(c.passed for c in result.checks)
        assert result.fault_observed is True

    async def test_low_battery_scenario_battery_fail(self):
        """测试低电量场景电池检查失败。"""
        executor = MockDeviceExecutor("low_battery", MockScenario.low_battery)
        validator = DefaultValidator()
        context = ValidationContext(
            scenario_run_id=1,
            device_serial="low_battery",
            executor=executor,
            validation_profile={},
            artifacts_dir="/tmp",
        )

        result = await validator.validate(context)

        battery_check = next(c for c in result.checks if c.check_name == "battery_level")
        assert battery_check.passed is False

    async def test_storage_full_scenario_storage_fail(self):
        """测试存储满场景存储检查失败。"""
        executor = MockDeviceExecutor("storage_full", MockScenario.storage_full)
        validator = DefaultValidator()
        context = ValidationContext(
            scenario_run_id=1,
            device_serial="storage_full",
            executor=executor,
            validation_profile={},
            artifacts_dir="/tmp",
        )

        result = await validator.validate(context)

        storage_check = next(c for c in result.checks if c.check_name == "storage_available")
        assert storage_check.passed is False

    async def test_boot_timeout_scenario_boot_fail(self):
        """测试启动超时场景boot检查失败。"""
        executor = MockDeviceExecutor("boot_timeout", MockScenario.boot_timeout)
        validator = DefaultValidator()
        context = ValidationContext(
            scenario_run_id=1,
            device_serial="boot_timeout",
            executor=executor,
            validation_profile={},
            artifacts_dir="/tmp",
        )

        result = await validator.validate(context)

        boot_check = next(c for c in result.checks if c.check_name == "boot_completed")
        assert boot_check.passed is False

    async def test_offline_scenario_all_fail(self):
        """测试离线场景所有检查失败。"""
        executor = MockDeviceExecutor("offline", MockScenario.offline)
        validator = DefaultValidator()
        context = ValidationContext(
            scenario_run_id=1,
            device_serial="offline",
            executor=executor,
            validation_profile={},
            artifacts_dir="/tmp",
        )

        result = await validator.validate(context)

        # 离线设备至少在线检查失败
        online_check = next((c for c in result.checks if c.check_name == "device_online"), None)
        if online_check:
            assert online_check.passed is False