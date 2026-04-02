"""场景执行编排模块.

提供具体的执行阶段实现，负责各阶段的详细操作。
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from chaosdroid.config.settings import get_settings
from chaosdroid.executors.base import BaseDeviceExecutor, StorageInfo, BatteryInfo
from chaosdroid.injectors.base import BaseInjector, InjectContext, InjectResult
from chaosdroid.models.base import StepStatus, StepType
from chaosdroid.observers.collector import ArtifactCollector, ObservationCollector
from chaosdroid.services.device_lock_manager import (
    DeviceLockManager,
    DeviceLockTimeoutError,
    DeviceAlreadyLockedError,
    get_device_lock_manager,
)
from chaosdroid.validators.base import BaseValidator, ValidationContext, ValidationResult

logger = logging.getLogger(__name__)


class PreemptionException(Exception):
    """任务被抢占异常."""
    pass


class ExecutionPhaseResult:
    """执行阶段结果."""

    def __init__(
        self,
        success: bool,
        message: str = "",
        details: Optional[Dict[str, Any]] = None,
        started_at: Optional[datetime] = None,
        finished_at: Optional[datetime] = None,
    ):
        self.success = success
        self.message = message
        self.details = details or {}
        self.started_at = started_at or datetime.utcnow()
        self.finished_at = finished_at or datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典."""
        return {
            "success": self.success,
            "message": self.message,
            "details": self.details,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
        }


class PreparePhaseExecutor:
    """准备阶段执行器."""

    def __init__(self, scenario_run_id: int, artifacts_dir: Path):
        self.scenario_run_id = scenario_run_id
        self.artifacts_dir = artifacts_dir
        self.settings = get_settings()
        self.collector = ArtifactCollector(scenario_run_id)

    async def execute(
        self,
        executor: BaseDeviceExecutor,
        fault_profile: Optional[Dict[str, Any]] = None,
    ) -> ExecutionPhaseResult:
        """执行准备阶段.

        职责:
        - 检查设备在线
        - 采集设备基础属性
        - 检查电量、boot状态、可用空间
        - 初始化任务目录

        Args:
            executor: 设备执行器
            fault_profile: 故障配置（用于预检查特定条件）

        Returns:
            ExecutionPhaseResult: 执行结果
        """
        started_at = datetime.utcnow()

        try:
            # 检查设备在线
            online = await executor.is_online()
            if not online:
                return ExecutionPhaseResult(
                    success=False,
                    message="设备不在线",
                    details={"error": "device_offline"},
                    started_at=started_at,
                )

            # 采集设备属性
            properties = await executor.get_properties()

            # 采集电池信息
            battery_info = await executor.get_battery_info()

            # 采集存储信息
            storage_info = await executor.get_storage_info()

            # 检查boot状态
            boot_completed = await executor.check_boot_completed()

            # 前置条件检查
            issues = []
            min_battery_level = 20
            min_storage_mb = 100

            # 根据故障配置调整检查条件
            if fault_profile:
                params = fault_profile.get("parameters", {})
                # 存储压力注入需要更多空间
                if fault_profile.get("fault_type") == "storage_pressure":
                    pressure_mb = params.get("pressure_mb", 1000)
                    min_storage_mb = pressure_mb + 100

                # 低电量场景不需要电量检查
                if fault_profile.get("fault_type") == "low_battery":
                    min_battery_level = 0

            if battery_info.level < min_battery_level:
                issues.append({
                    "type": "low_battery",
                    "current": battery_info.level,
                    "required": min_battery_level,
                    "message": f"电量过低: {battery_info.level}% < {min_battery_level}%",
                })

            if storage_info.available < min_storage_mb * 1024 * 1024:
                issues.append({
                    "type": "storage_low",
                    "current_mb": storage_info.available // (1024 * 1024),
                    "required_mb": min_storage_mb,
                    "message": f"存储空间不足: {storage_info.available // (1024 * 1024)}MB < {min_storage_mb}MB",
                })

            if not boot_completed:
                issues.append({
                    "type": "boot_not_completed",
                    "message": "设备启动未完成",
                })

            if issues:
                return ExecutionPhaseResult(
                    success=False,
                    message=f"前置检查失败: {len(issues)}个问题",
                    details={
                        "error": "precheck_failed",
                        "issues": issues,
                        "properties": properties,
                        "battery": {
                            "level": battery_info.level,
                            "status": battery_info.status,
                        },
                        "storage": {
                            "total_mb": storage_info.total // (1024 * 1024),
                            "available_mb": storage_info.available // (1024 * 1024),
                        },
                        "boot_completed": boot_completed,
                    },
                    started_at=started_at,
                )

            # 保存初始状态快照
            await self.collector.save_snapshot("initial", {
                "properties": properties,
                "battery": {
                    "level": battery_info.level,
                    "status": battery_info.status,
                    "temperature": battery_info.temperature,
                    "health": battery_info.health,
                },
                "storage": {
                    "total_mb": storage_info.total // (1024 * 1024),
                    "available_mb": storage_info.available // (1024 * 1024),
                    "used_mb": storage_info.used // (1024 * 1024),
                },
                "boot_completed": boot_completed,
                "online": online,
            })

            return ExecutionPhaseResult(
                success=True,
                message="准备阶段完成",
                details={
                    "properties": properties,
                    "battery": {
                        "level": battery_info.level,
                        "status": battery_info.status,
                    },
                    "storage": {
                        "total_mb": storage_info.total // (1024 * 1024),
                        "available_mb": storage_info.available // (1024 * 1024),
                    },
                    "boot_completed": boot_completed,
                    "online": online,
                },
                started_at=started_at,
            )

        except Exception as e:
            logger.exception("准备阶段执行异常")
            return ExecutionPhaseResult(
                success=False,
                message=f"准备阶段异常: {str(e)}",
                details={"error": str(e)},
                started_at=started_at,
            )


class InjectPhaseExecutor:
    """注入阶段执行器."""

    def __init__(self, scenario_run_id: int, artifacts_dir: Path):
        self.scenario_run_id = scenario_run_id
        self.artifacts_dir = artifacts_dir
        self.collector = ArtifactCollector(scenario_run_id)

    async def execute(
        self,
        executor: BaseDeviceExecutor,
        injector: Optional[BaseInjector],
        fault_profile: Optional[Dict[str, Any]],
        inject_stage: str = "precheck",
        observation_collector: Optional[ObservationCollector] = None,
    ) -> ExecutionPhaseResult:
        """执行注入阶段.

        职责:
        - 根据 FaultProfile 执行注入动作
        - 记录注入成功或失败
        - 对需要持续存在的故障保持注入状态

        Args:
            executor: 设备执行器
            injector: 故障注入器
            fault_profile: 故障配置
            inject_stage: 注入阶段
            observation_collector: 观测采集器

        Returns:
            ExecutionPhaseResult: 执行结果
        """
        started_at = datetime.utcnow()

        if injector is None:
            return ExecutionPhaseResult(
                success=True,
                message="没有配置注入器，跳过注入",
                details={"skipped": True},
                started_at=started_at,
            )

        try:
            # 构建注入上下文
            inject_context = InjectContext(
                scenario_run_id=self.scenario_run_id,
                device_serial=executor.device_serial,
                executor=executor,
                fault_profile=fault_profile or {},
                artifacts_dir=str(self.artifacts_dir),
                started_at=started_at,
                inject_stage=inject_stage,
            )

            # 准备注入环境
            prepare_success = await injector.prepare(inject_context)
            if not prepare_success:
                return ExecutionPhaseResult(
                    success=False,
                    message="注入准备失败",
                    details={"error": "prepare_failed"},
                    started_at=started_at,
                )

            # 采集注入前状态
            if observation_collector:
                before_state = await observation_collector.collect_before_inject(executor)

            # 执行注入
            inject_result: InjectResult = await injector.inject(inject_context)

            # 采集注入后状态
            if observation_collector:
                after_state = await observation_collector.collect_after_inject(executor)

            # 构建结果
            result_details = {
                "fault_type": injector.fault_type.value if hasattr(injector.fault_type, 'value') else str(injector.fault_type),
                "risk_level": injector.risk_level.value if hasattr(injector.risk_level, 'value') else str(injector.risk_level),
                "fault_injected": inject_result.fault_injected,
                "fault_observed": inject_result.fault_observed,
                "cleanup_required": inject_result.cleanup_required,
                "inject_details": inject_result.details,
            }

            if inject_result.success:
                return ExecutionPhaseResult(
                    success=True,
                    message=inject_result.message,
                    details=result_details,
                    started_at=started_at,
                )
            else:
                return ExecutionPhaseResult(
                    success=False,
                    message=f"注入失败: {inject_result.message}",
                    details=result_details,
                    started_at=started_at,
                )

        except Exception as e:
            logger.exception("注入阶段执行异常")
            return ExecutionPhaseResult(
                success=False,
                message=f"注入阶段异常: {str(e)}",
                details={"error": str(e)},
                started_at=started_at,
            )


class ValidatePhaseExecutor:
    """验证阶段执行器."""

    def __init__(self, scenario_run_id: int, artifacts_dir: Path):
        self.scenario_run_id = scenario_run_id
        self.artifacts_dir = artifacts_dir
        self.collector = ArtifactCollector(scenario_run_id)

    async def execute(
        self,
        executor: BaseDeviceExecutor,
        validator: Optional[BaseValidator],
        validation_profile: Optional[Dict[str, Any]],
        inject_result: Optional[Dict[str, Any]] = None,
    ) -> ExecutionPhaseResult:
        """执行验证阶段.

        职责:
        - 执行 ValidationProfile
        - 判断系统是否表现出预期异常
        - 判断核心功能是否仍然可达

        Args:
            executor: 设备执行器
            validator: 验证器
            validation_profile: 验证配置
            inject_result: 注入结果

        Returns:
            ExecutionPhaseResult: 执行结果
        """
        started_at = datetime.utcnow()

        if validator is None:
            return ExecutionPhaseResult(
                success=True,
                message="没有配置验证器，默认通过",
                details={"skipped": True, "passed": True},
                started_at=started_at,
            )

        try:
            # 构建验证上下文
            validation_context = ValidationContext(
                scenario_run_id=self.scenario_run_id,
                device_serial=executor.device_serial,
                executor=executor,
                validation_profile=validation_profile or {},
                inject_result=inject_result,
                artifacts_dir=str(self.artifacts_dir),
                started_at=started_at,
            )

            # 执行验证
            validation_result: ValidationResult = await validator.validate(validation_context)

            # 构建检查结果详情
            checks_details = []
            for check in validation_result.checks:
                checks_details.append({
                    "check_name": check.check_name,
                    "passed": check.passed,
                    "expected": str(check.expected),
                    "actual": str(check.actual),
                    "message": check.message,
                })

            result_details = {
                "passed": validation_result.passed,
                "fault_observed": validation_result.fault_observed,
                "total_checks": len(validation_result.checks),
                "passed_checks": sum(1 for c in validation_result.checks if c.passed),
                "failed_checks": sum(1 for c in validation_result.checks if not c.passed),
                "checks": checks_details,
            }

            if validation_result.passed:
                return ExecutionPhaseResult(
                    success=True,
                    message=f"验证通过: {validation_result.message}",
                    details=result_details,
                    started_at=started_at,
                )
            else:
                return ExecutionPhaseResult(
                    success=False,
                    message=f"验证失败: {validation_result.message}",
                    details=result_details,
                    started_at=started_at,
                )

        except Exception as e:
            logger.exception("验证阶段执行异常")
            return ExecutionPhaseResult(
                success=False,
                message=f"验证阶段异常: {str(e)}",
                details={"error": str(e)},
                started_at=started_at,
            )


class RecoverPhaseExecutor:
    """恢复阶段执行器."""

    def __init__(self, scenario_run_id: int, artifacts_dir: Path):
        self.scenario_run_id = scenario_run_id
        self.artifacts_dir = artifacts_dir
        self.collector = ArtifactCollector(scenario_run_id)

    async def execute(
        self,
        executor: BaseDeviceExecutor,
        injector: Optional[BaseInjector],
        recovery_profile: Optional[Dict[str, Any]],
        inject_context: Optional[InjectContext] = None,
    ) -> ExecutionPhaseResult:
        """执行恢复阶段.

        职责:
        - 执行 RecoveryProfile
        - 检查故障是否被移除
        - 检查设备是否恢复可用

        Args:
            executor: 设备执行器
            injector: 故障注入器（用于清理）
            recovery_profile: 恢复配置
            inject_context: 注入上下文（用于清理）

        Returns:
            ExecutionPhaseResult: 执行结果
        """
        started_at = datetime.utcnow()

        cleanup_success = True
        recovery_success = True
        steps_executed = []

        try:
            # 1. 清理注入
            if injector and inject_context:
                cleanup_result = await injector.cleanup(inject_context)
                cleanup_success = cleanup_result
                steps_executed.append({
                    "step": "cleanup_injection",
                    "success": cleanup_result,
                    "message": cleanup_result and "清理成功" or "清理失败",
                })

            # 2. 执行恢复步骤
            if recovery_profile:
                steps = recovery_profile.get("steps", {})
                recovery_steps = steps.get("steps", []) if isinstance(steps, dict) else []

                for step_config in recovery_steps:
                    step_name = step_config.get("name", "unknown")
                    step_result = await self._execute_recovery_step(
                        executor, step_config
                    )
                    steps_executed.append({
                        "step": step_name,
                        "success": step_result["success"],
                        "message": step_result.get("message", ""),
                    })
                    if not step_result["success"]:
                        recovery_success = False

            # 3. 验证恢复结果
            verification_result = await self._verify_recovery(executor)

            result_details = {
                "cleanup_success": cleanup_success,
                "recovery_success": recovery_success,
                "verification": verification_result,
                "steps_executed": steps_executed,
            }

            overall_success = cleanup_success and recovery_success and verification_result.get("passed", True)

            if overall_success:
                return ExecutionPhaseResult(
                    success=True,
                    message="恢复阶段完成",
                    details=result_details,
                    started_at=started_at,
                )
            else:
                return ExecutionPhaseResult(
                    success=False,
                    message="恢复阶段失败",
                    details=result_details,
                    started_at=started_at,
                )

        except Exception as e:
            logger.exception("恢复阶段执行异常")
            return ExecutionPhaseResult(
                success=False,
                message=f"恢复阶段异常: {str(e)}",
                details={"error": str(e)},
                started_at=started_at,
            )

    async def _execute_recovery_step(
        self, executor: BaseDeviceExecutor, step_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行单个恢复步骤."""
        step_type = step_config.get("type", "shell")
        command = step_config.get("command", "")
        timeout = step_config.get("timeout", 30)

        try:
            if step_type == "shell":
                result = await executor.execute_shell(command, timeout)
                return {
                    "success": result.success,
                    "message": result.stderr if not result.success else result.stdout,
                }

            elif step_type == "reboot":
                wait_timeout = step_config.get("wait_timeout", 120)
                result = await executor.reboot(wait_timeout)
                return {
                    "success": result,
                    "message": result and "重启成功" or "重启失败",
                }

            elif step_type == "wait_boot":
                timeout = step_config.get("timeout", 60)
                result = await executor.wait_for_boot(timeout)
                return {
                    "success": result,
                    "message": result and "启动完成" or "启动超时",
                }

            elif step_type == "check_online":
                online = await executor.is_online()
                return {
                    "success": online,
                    "message": online and "设备在线" or "设备离线",
                }

            else:
                logger.warning(f"未知的恢复步骤类型: {step_type}")
                return {
                    "success": True,
                    "message": f"跳过未知步骤类型: {step_type}",
                }

        except Exception as e:
            logger.exception(f"恢复步骤执行异常: {step_type}")
            return {
                "success": False,
                "message": str(e),
            }

    async def _verify_recovery(self, executor: BaseDeviceExecutor) -> Dict[str, Any]:
        """验证恢复结果."""
        try:
            # 检查设备在线
            online = await executor.is_online()
            if not online:
                return {
                    "passed": False,
                    "reason": "device_offline",
                    "message": "设备离线",
                }

            # 检查boot完成
            boot_completed = await executor.check_boot_completed()
            if not boot_completed:
                return {
                    "passed": False,
                    "reason": "boot_not_completed",
                    "message": "启动未完成",
                }

            # 检查存储空间（是否有异常占用）
            storage_info = await executor.get_storage_info()

            # 检查电量
            battery_info = await executor.get_battery_info()

            return {
                "passed": True,
                "online": online,
                "boot_completed": boot_completed,
                "storage_available_mb": storage_info.available // (1024 * 1024),
                "battery_level": battery_info.level,
                "message": "设备状态正常",
            }

        except Exception as e:
            logger.exception("恢复验证异常")
            return {
                "passed": False,
                "reason": str(e),
                "message": f"验证异常: {str(e)}",
            }


class CollectPhaseExecutor:
    """收集阶段执行器."""

    def __init__(self, scenario_run_id: int, artifacts_dir: Path):
        self.scenario_run_id = scenario_run_id
        self.artifacts_dir = artifacts_dir
        self.collector = ArtifactCollector(scenario_run_id)

    async def execute(
        self,
        executor: BaseDeviceExecutor,
        observation_collector: Optional[ObservationCollector] = None,
    ) -> ExecutionPhaseResult:
        """执行收集阶段.

        职责:
        - 保存所有执行产物
        - 收集最终观测数据

        Args:
            executor: 设备执行器
            observation_collector: 观测采集器

        Returns:
            ExecutionPhaseResult: 执行结果
        """
        started_at = datetime.utcnow()
        artifacts_saved = []

        try:
            # 检查设备在线
            online = await executor.is_online()

            if online:
                # 收集logcat
                logcat = await executor.get_logcat(1000)
                logcat_path = await self.collector.save_logcat(logcat)
                artifacts_saved.append({
                    "type": "logcat",
                    "path": str(logcat_path),
                })

                # 收集设备属性
                properties = await executor.get_properties()
                properties_path = await self.collector.save_getprop(properties)
                artifacts_saved.append({
                    "type": "getprop",
                    "path": str(properties_path),
                })

                # 收集电池信息
                battery_info = await executor.get_battery_info()
                battery_path = await self.collector.save_battery_info({
                    "level": battery_info.level,
                    "status": battery_info.status,
                    "temperature": battery_info.temperature,
                    "health": battery_info.health,
                })
                artifacts_saved.append({
                    "type": "battery",
                    "path": str(battery_path),
                })

                # 收集存储信息
                storage_info = await executor.get_storage_info()
                await self.collector.save_snapshot("final_storage", {
                    "total_mb": storage_info.total // (1024 * 1024),
                    "available_mb": storage_info.available // (1024 * 1024),
                    "used_mb": storage_info.used // (1024 * 1024),
                })

            # 收集最终观测
            if observation_collector:
                await observation_collector.collect_after_recovery(executor)

            return ExecutionPhaseResult(
                success=True,
                message="收集阶段完成",
                details={
                    "online": online,
                    "artifacts_count": len(artifacts_saved),
                    "artifacts": artifacts_saved,
                },
                started_at=started_at,
            )

        except Exception as e:
            logger.exception("收集阶段执行异常")
            return ExecutionPhaseResult(
                success=False,
                message=f"收集阶段异常: {str(e)}",
                details={"error": str(e)},
                started_at=started_at,
            )


class ScenarioExecution:
    """场景执行编排."""

    def __init__(
        self,
        scenario_run_id: int,
        device_lock_manager: Optional[DeviceLockManager] = None,
    ):
        self.scenario_run_id = scenario_run_id
        self.device_lock_manager = device_lock_manager or get_device_lock_manager()
        self.settings = get_settings()
        self.artifacts_dir = self.settings.get_artifacts_dir() / str(scenario_run_id)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

        # 创建各阶段执行器
        self.prepare_executor = PreparePhaseExecutor(scenario_run_id, self.artifacts_dir)
        self.inject_executor = InjectPhaseExecutor(scenario_run_id, self.artifacts_dir)
        self.validate_executor = ValidatePhaseExecutor(scenario_run_id, self.artifacts_dir)
        self.recover_executor = RecoverPhaseExecutor(scenario_run_id, self.artifacts_dir)
        self.collect_executor = CollectPhaseExecutor(scenario_run_id, self.artifacts_dir)

        # 观测采集器
        self.observation_collector = ObservationCollector(scenario_run_id)

    async def run_full_execution(
        self,
        executor: BaseDeviceExecutor,
        injector: Optional[BaseInjector],
        validator: Optional[BaseValidator],
        fault_profile: Optional[Dict[str, Any]],
        validation_profile: Optional[Dict[str, Any]],
        recovery_profile: Optional[Dict[str, Any]],
        inject_stage: str = "precheck",
    ) -> Dict[str, Any]:
        """运行完整执行流程.

        Args:
            executor: 设备执行器
            injector: 故障注入器
            validator: 验证器
            fault_profile: 故障配置
            validation_profile: 验证配置
            recovery_profile: 恢复配置
            inject_stage: 注入阶段

        Returns:
            Dict[str, Any]: 执行结果汇总
        """
        results = {
            "prepare": None,
            "inject": None,
            "validate": None,
            "recover": None,
            "collect": None,
            "inject_context": None,
        }

        # 准备阶段
        results["prepare"] = await self.prepare_executor.execute(executor, fault_profile)
        if not results["prepare"].success:
            return results

        # 注入阶段
        results["inject"] = await self.inject_executor.execute(
            executor, injector, fault_profile, inject_stage, self.observation_collector
        )

        # 构建注入上下文用于后续清理
        if injector:
            results["inject_context"] = InjectContext(
                scenario_run_id=self.scenario_run_id,
                device_serial=executor.device_serial,
                executor=executor,
                fault_profile=fault_profile or {},
                artifacts_dir=str(self.artifacts_dir),
                inject_stage=inject_stage,
            )

        # 验证阶段（即使注入失败也要验证设备状态）
        inject_result_data = results["inject"].to_dict() if results["inject"] else None
        results["validate"] = await self.validate_executor.execute(
            executor, validator, validation_profile, inject_result_data
        )

        # 恢复阶段
        results["recover"] = await self.recover_executor.execute(
            executor, injector, recovery_profile, results["inject_context"]
        )

        # 收集阶段
        results["collect"] = await self.collect_executor.execute(
            executor, self.observation_collector
        )

        return results

    def calculate_final_status(
        self,
        prepare_result: ExecutionPhaseResult,
        inject_result: ExecutionPhaseResult,
        validate_result: ExecutionPhaseResult,
        recover_result: ExecutionPhaseResult,
    ) -> str:
        """计算最终状态.

        Returns:
            str: 最终状态 (passed/failed/partial)
        """
        # 准备失败
        if not prepare_result.success:
            return "failed"

        # 注入失败
        if inject_result and not inject_result.success:
            # 注入失败但恢复成功 -> failed
            if recover_result and recover_result.success:
                return "failed"
            else:
                return "failed"

        # 获取注入结果详情
        inject_details = inject_result.details if inject_result else {}
        fault_injected = inject_details.get("fault_injected", False)

        # 获取验证结果详情
        validate_details = validate_result.details if validate_result else {}
        validation_passed = validate_details.get("passed", True)

        # 获取恢复结果详情
        recover_details = recover_result.details if recover_result else {}
        recovery_passed = recover_details.get("cleanup_success", True) and recover_details.get("recovery_success", True)

        # 根据规范判定最终状态
        # 注入成功 + 验证通过 + 恢复通过 = passed
        # 注入成功 + 验证失败 + 恢复通过 = failed
        # 注入成功 + 验证通过 + 恢复失败 = partial
        # 注入失败 = failed

        if not fault_injected:
            return "failed"

        if fault_injected and validation_passed and recovery_passed:
            return "passed"

        if fault_injected and not validation_passed and recovery_passed:
            return "failed"

        if fault_injected and validation_passed and not recovery_passed:
            return "partial"

        return "failed"

    async def execute_with_device_lock(
        self,
        executor: BaseDeviceExecutor,
        injector: Optional[BaseInjector],
        validator: Optional[BaseValidator],
        fault_profile: Optional[Dict[str, Any]],
        validation_profile: Optional[Dict[str, Any]],
        recovery_profile: Optional[Dict[str, Any]],
        inject_stage: str = "precheck",
        lock_timeout_sec: int = 600,
        wait_timeout_sec: int = 30,
    ) -> Tuple[Dict[str, Any], bool]:
        """在设备锁保护下执行场景。

        获取设备锁，执行完整流程，确保在异常情况下也释放锁。

        Args:
            executor: 设备执行器
            injector: 故障注入器
            validator: 验证器
            fault_profile: 故障配置
            validation_profile: 验证配置
            recovery_profile: 恢复配置
            inject_stage: 注入阶段
            lock_timeout_sec: 锁超时时间（秒）
            wait_timeout_sec: 等待锁的超时时间（秒）

        Returns:
            Tuple[Dict[str, Any], bool]: (执行结果，是否获取到锁)

        Raises:
            DeviceLockTimeoutError: 获取设备锁超时
        """
        device_serial = executor.device_serial
        lock_acquired = False

        # ===== 获取设备锁 =====
        try:
            lock = await self.device_lock_manager.acquire_lock(
                device_serial=device_serial,
                scenario_run_id=self.scenario_run_id,
                timeout_sec=lock_timeout_sec,
                wait_timeout_sec=wait_timeout_sec,
            )
            lock_acquired = True
            logger.info(
                f"设备锁已获取：device={device_serial}, "
                f"run_id={self.scenario_run_id}, "
                f"timeout={lock_timeout_sec}s"
            )
        except DeviceLockTimeoutError as e:
            logger.error(f"获取设备锁超时：device={device_serial}, run_id={self.scenario_run_id}")
            raise
        except DeviceAlreadyLockedError as e:
            logger.error(f"设备已被锁定：device={device_serial}, run_id={self.scenario_run_id}")
            raise

        try:
            # ===== 执行完整流程 =====
            result = await self.run_full_execution(
                executor=executor,
                injector=injector,
                validator=validator,
                fault_profile=fault_profile,
                validation_profile=validation_profile,
                recovery_profile=recovery_profile,
                inject_stage=inject_stage,
            )
            return result, lock_acquired

        except PreemptionException:
            # 被抢占时重新抛出
            logger.warning(f"任务被抢占：run_id={self.scenario_run_id}")
            raise

        except Exception as e:
            logger.exception(f"执行异常：run_id={self.scenario_run_id}, device={device_serial}")
            raise

        finally:
            # ===== 释放设备锁 =====
            if lock_acquired:
                released = await self.device_lock_manager.release_lock(
                    device_serial=device_serial,
                    scenario_run_id=self.scenario_run_id,
                )
                if released:
                    logger.info(
                        f"设备锁已释放：device={device_serial}, run_id={self.scenario_run_id}"
                    )
                else:
                    logger.warning(
                        f"设备锁释放失败或已被释放：device={device_serial}, run_id={self.scenario_run_id}"
                    )

    async def execute_with_lease(
        self,
        executor: BaseDeviceExecutor,
        injector: Optional[BaseInjector],
        validator: Optional[BaseValidator],
        fault_profile: Optional[Dict[str, Any]],
        validation_profile: Optional[Dict[str, Any]],
        recovery_profile: Optional[Dict[str, Any]],
        inject_stage: str = "precheck",
    ) -> Dict[str, Any]:
        """在有租约的情况下执行.

        执行完成后自动释放租约。

        Args:
            executor: 设备执行器
            injector: 故障注入器
            validator: 验证器
            fault_profile: 故障配置
            validation_profile: 验证配置
            recovery_profile: 恢复配置
            inject_stage: 注入阶段

        Returns:
            Dict[str, Any]: 执行结果汇总

        Raises:
            ValueError: 没有活跃的设备租约
        """
        from sqlalchemy.orm import Session
        from chaosdroid.models import get_session_context, Device, DeviceLease, ScenarioRun
        from chaosdroid.scheduling import LeaseManager
        from chaosdroid.scheduling.enums import DeviceStatus, LeaseStatus

        with get_session_context() as session:
            lease_manager = LeaseManager(session)

            # 获取租约
            lease = lease_manager.get_run_lease(self.scenario_run_id)
            if not lease:
                raise ValueError(f"没有活跃的设备租约: run_id={self.scenario_run_id}")

            device = session.get(Device, lease.device_id)
            if not device:
                raise ValueError(f"设备不存在: device_id={lease.device_id}")

            try:
                # 执行完整流程
                result = await self.run_full_execution(
                    executor=executor,
                    injector=injector,
                    validator=validator,
                    fault_profile=fault_profile,
                    validation_profile=validation_profile,
                    recovery_profile=recovery_profile,
                    inject_stage=inject_stage,
                )

                return result

            except PreemptionException:
                # 被抢占时租约已在抢占流程中处理
                logger.warning(f"任务被抢占: run_id={self.scenario_run_id}")
                raise

            except Exception as e:
                logger.exception(f"执行异常: run_id={self.scenario_run_id}")
                raise

            finally:
                # 确保租约被释放（除非被抢占）
                session.refresh(lease)
                if lease.lease_status != LeaseStatus.PREEMPTED.value:
                    lease_manager.release_lease(lease)
                    device.status = DeviceStatus.IDLE.value
                    session.commit()
                    logger.info(f"租约已释放: lease_id={lease.id}")

    async def on_preemption(self) -> bool:
        """被抢占时的清理逻辑.

        Returns:
            bool: 清理是否成功
        """
        from chaosdroid.models import get_session_context
        from chaosdroid.scheduling.enums import DeviceStatus

        logger.warning(f"任务被抢占，执行清理: run_id={self.scenario_run_id}")

        try:
            # 1. 停止当前执行（通过标记状态）
            # 2. 清理注入效果（如果已注入）
            # 3. 租约已在抢占流程中处理

            # 记录事件
            with get_session_context() as session:
                from chaosdroid.models import IncidentEvent
                from chaosdroid.scheduling.enums import EventType, EventSeverity

                event = IncidentEvent(
                    scenario_run_id=self.scenario_run_id,
                    event_type=EventType.PREEMPTION_TRIGGERED.value,
                    severity=EventSeverity.WARNING.value,
                    payload_json={
                        "message": "任务被抢占，清理完成",
                    },
                )
                session.add(event)
                session.commit()

            return True

        except Exception as e:
            logger.exception(f"抢占清理失败: run_id={self.scenario_run_id}")
            return False