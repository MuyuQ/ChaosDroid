"""场景编排服务模块.

提供场景执行的完整编排逻辑，负责协调执行器、注入器、验证器和恢复策略。
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chaosdroid.config.settings import get_settings
from chaosdroid.executors.base import BaseDeviceExecutor, ExecutorMode
from chaosdroid.executors.mock_executor import MockDeviceExecutor, MockScenario
from chaosdroid.models import (
    Artifact,
    FaultProfile,
    RecoveryProfile,
    Report,
    ScenarioRun,
    ScenarioStep,
    ScenarioTemplate,
    ValidationProfile,
    RunStatus,
    StepStatus,
    StepType,
)
from chaosdroid.models.database import get_session_context
from chaosdroid.observers.collector import ArtifactCollector, ObservationCollector
from chaosdroid.services.device_lock_manager import (
    DeviceLockManager,
    DeviceLockTimeoutError,
    DeviceAlreadyLockedError,
    get_device_lock_manager,
)
from chaosdroid.services.report_generator import ReportData, ReportGenerator
from chaosdroid.validators.base import (
    BaseValidator,
    DefaultValidator,
    ValidationContext,
    ValidationResult,
    JudgmentResult,
    judge_result,
)

logger = logging.getLogger(__name__)


class ScenarioOrchestratorService:
    """场景编排服务.

    负责完整的场景执行流程编排，包括：
    - 设备锁定防止并发执行
    - 设置执行器（real/mock）
    - 协调注入器、验证器、恢复服务
    - 执行状态机
    - 生成报告
    - 超时处理
    """

    # 默认各阶段超时配置（秒）
    DEFAULT_PREPARE_TIMEOUT = 60
    DEFAULT_INJECT_TIMEOUT = 180
    DEFAULT_VALIDATE_TIMEOUT = 180
    DEFAULT_RECOVERY_TIMEOUT = 300
    DEFAULT_COLLECT_TIMEOUT = 60

    def __init__(
        self,
        device_lock_manager: Optional[DeviceLockManager] = None,
        prepare_timeout: int = DEFAULT_PREPARE_TIMEOUT,
        inject_timeout: int = DEFAULT_INJECT_TIMEOUT,
        validate_timeout: int = DEFAULT_VALIDATE_TIMEOUT,
        recovery_timeout: int = DEFAULT_RECOVERY_TIMEOUT,
        collect_timeout: int = DEFAULT_COLLECT_TIMEOUT,
    ):
        """初始化编排服务.

        Args:
            device_lock_manager: 设备锁管理器实例
            prepare_timeout: 准备阶段超时（秒）
            inject_timeout: 注入阶段超时（秒）
            validate_timeout: 验证阶段超时（秒）
            recovery_timeout: 恢复阶段超时（秒）
            collect_timeout: 收集阶段超时（秒）
        """
        self.settings = get_settings()
        self._device_lock_manager = device_lock_manager or get_device_lock_manager()
        self._timeout_config = {
            "prepare": prepare_timeout,
            "inject": inject_timeout,
            "validate": validate_timeout,
            "recovery": recovery_timeout,
            "collect": collect_timeout,
        }

    async def execute_scenario(
        self,
        scenario_run_id: int,
        injector_service: Any,
        validation_service: Any,
        recovery_service: Any,
        observation_service: Any,
    ) -> RunStatus:
        """执行场景的完整流程.

        包含设备锁定机制，防止同一设备的并发执行。

        Args:
            scenario_run_id: 场景执行记录 ID
            injector_service: 注入器分发服务实例
            validation_service: 验证服务实例
            recovery_service: 恢复服务实例
            observation_service: 观测服务实例

        Returns:
            最终执行状态
        """
        logger.info(f"开始执行场景 run_id={scenario_run_id}")

        # 获取执行记录和相关配置
        async with get_session_context() as session:
            scenario_run = await self._get_scenario_run(session, scenario_run_id)
            if not scenario_run:
                logger.error(f"找不到执行记录 run_id={scenario_run_id}")
                return RunStatus.FAILED

            # 获取场景模板
            scenario_template = await self._get_scenario_template(
                session, scenario_run.scenario_template_id
            )
            if not scenario_template:
                logger.error(f"找不到场景模板 template_id={scenario_run.scenario_template_id}")
                return RunStatus.FAILED

            # 获取关联的配置
            fault_profile = await self._get_fault_profile(
                session, scenario_template.fault_profile_id
            )
            validation_profile = await self._get_validation_profile(
                session, scenario_template.validation_profile_id
            )
            recovery_profile = await self._get_recovery_profile(
                session, scenario_template.recovery_profile_id
            )

            device_serial = scenario_run.device_serial

        # ===== 设备锁定 =====
        try:
            lock = await self._device_lock_manager.acquire_lock(
                device_serial=device_serial,
                scenario_run_id=scenario_run_id,
                timeout_sec=self._timeout_config["recovery"] + 120,
                wait_timeout_sec=30,
            )
            logger.info(f"设备锁已获取：device={device_serial}, run_id={scenario_run_id}")
        except DeviceLockTimeoutError as e:
            logger.error(f"获取设备锁超时：{e}")
            await self._update_run_status(scenario_run_id, RunStatus.FAILED, finished=True)
            return RunStatus.FAILED
        except DeviceAlreadyLockedError as e:
            logger.error(f"设备已被锁定：{e}")
            await self._update_run_status(scenario_run_id, RunStatus.FAILED, finished=True)
            return RunStatus.FAILED

        try:
            # 创建 artifacts 目录
            artifacts_dir = self.settings.get_artifacts_dir() / str(scenario_run_id)
            artifacts_dir.mkdir(parents=True, exist_ok=True)

            # 设置执行上下文
            context = self._build_execution_context(
                scenario_run=scenario_run,
                scenario_template=scenario_template,
                fault_profile=fault_profile,
                validation_profile=validation_profile,
                recovery_profile=recovery_profile,
                artifacts_dir=artifacts_dir,
            )

            # 设置执行器
            executor = self._setup_executor(
                mode=scenario_template.executor_mode,
                device_serial=device_serial,
                context=context,
            )
            context["executor"] = executor

            # 设置注入器
            injector = await injector_service.setup_injector(
                fault_profile=fault_profile,
                context=context,
            )
            context["injector"] = injector

            # 设置验证器
            validator = await validation_service.setup_validator(
                validation_profile=validation_profile,
                context=context,
            )
            context["validator"] = validator

            # 设置恢复策略
            context["recovery_service"] = recovery_service

            # 创建观测采集器
            observation_collector = ObservationCollector(scenario_run_id)
            context["observation_collector"] = observation_collector

            # 执行流程
            final_status = await self._run_execution_flow(
                scenario_run_id=scenario_run_id,
                context=context,
                injector_service=injector_service,
                validation_service=validation_service,
                observation_service=observation_service,
            )

            # 生成报告
            await self._generate_report(
                scenario_run_id=scenario_run_id,
                context=context,
                final_status=final_status,
            )

            logger.info(f"场景执行完成 run_id={scenario_run_id}, status={final_status}")
            return final_status

        finally:
            # ===== 释放设备锁 =====
            await self._device_lock_manager.release_lock(
                device_serial=device_serial,
                scenario_run_id=scenario_run_id,
            )
            logger.info(f"设备锁已释放：device={device_serial}, run_id={scenario_run_id}")

    async def _get_scenario_run(
        self, session: AsyncSession, scenario_run_id: int
    ) -> Optional[ScenarioRun]:
        """获取场景执行记录."""
        result = await session.execute(
            select(ScenarioRun).where(ScenarioRun.id == scenario_run_id)
        )
        return result.scalar_one_or_none()

    async def _get_scenario_template(
        self, session: AsyncSession, template_id: Optional[int]
    ) -> Optional[ScenarioTemplate]:
        """获取场景模板."""
        if template_id is None:
            return None
        result = await session.execute(
            select(ScenarioTemplate).where(ScenarioTemplate.id == template_id)
        )
        return result.scalar_one_or_none()

    async def _get_fault_profile(
        self, session: AsyncSession, profile_id: Optional[int]
    ) -> Optional[Dict[str, Any]]:
        """获取故障配置."""
        if profile_id is None:
            return None
        result = await session.execute(
            select(FaultProfile).where(FaultProfile.id == profile_id)
        )
        profile = result.scalar_one_or_none()
        if profile is None:
            return None
        return {
            "id": profile.id,
            "name": profile.name,
            "fault_type": profile.fault_type,
            "parameters": profile.parameters or {},
            "safe_cleanup_required": profile.safe_cleanup_required,
            "risk_level": profile.risk_level,
        }

    async def _get_validation_profile(
        self, session: AsyncSession, profile_id: Optional[int]
    ) -> Optional[Dict[str, Any]]:
        """获取验证配置."""
        if profile_id is None:
            return None
        result = await session.execute(
            select(ValidationProfile).where(ValidationProfile.id == profile_id)
        )
        profile = result.scalar_one_or_none()
        if profile is None:
            return None
        return {
            "id": profile.id,
            "name": profile.name,
            "checks": json.loads(profile.checks_json or "{}"),
            "timeout_sec": profile.timeout_sec,
            "pass_rules": json.loads(profile.pass_rules_json or "{}"),
        }

    async def _get_recovery_profile(
        self, session: AsyncSession, profile_id: Optional[int]
    ) -> Optional[Dict[str, Any]]:
        """获取恢复配置."""
        if profile_id is None:
            return None
        result = await session.execute(
            select(RecoveryProfile).where(RecoveryProfile.id == profile_id)
        )
        profile = result.scalar_one_or_none()
        if profile is None:
            return None
        return {
            "id": profile.id,
            "name": profile.name,
            "steps": json.loads(profile.steps_json or "{}"),
            "manual_intervention_allowed": profile.manual_intervention_allowed,
            "timeout_sec": profile.timeout_sec,
        }

    def _build_execution_context(
        self,
        scenario_run: ScenarioRun,
        scenario_template: Optional[ScenarioTemplate],
        fault_profile: Optional[Dict[str, Any]],
        validation_profile: Optional[Dict[str, Any]],
        recovery_profile: Optional[Dict[str, Any]],
        artifacts_dir: Any,
    ) -> Dict[str, Any]:
        """构建执行上下文."""
        return {
            "scenario_run_id": scenario_run.id,
            "device_serial": scenario_run.device_serial,
            "inject_stage": scenario_run.inject_stage,
            "scenario_name": scenario_template and scenario_template.name or "Unknown",
            "target_type": scenario_template and scenario_template.target_type or "stability",
            "fault_profile": fault_profile or {},
            "validation_profile": validation_profile or {},
            "recovery_profile": recovery_profile or {},
            "artifacts_dir": str(artifacts_dir),
            "started_at": datetime.utcnow(),
            "inject_result": None,
            "validation_result": None,
            "recovery_result": None,
            "inject_failed": False,
            "steps_results": {},
            "observations": {},
            "judgment": None,
        }

    def _setup_executor(
        self, mode: str, device_serial: str, context: Dict[str, Any]
    ) -> BaseDeviceExecutor:
        """设置设备执行器."""
        if mode == ExecutorMode.mock.value:
            mock_scenario = MockScenario.normal
            executor = MockDeviceExecutor(device_serial, mock_scenario)
            logger.info(f"使用 Mock 执行器 serial={device_serial}")
        else:
            from chaosdroid.executors.real_executor import RealDeviceExecutor
            executor = RealDeviceExecutor(device_serial)
            logger.info(f"使用真实设备执行器 serial={device_serial}")
        return executor

    async def _run_execution_flow(
        self,
        scenario_run_id: int,
        context: Dict[str, Any],
        injector_service: Any,
        validation_service: Any,
        observation_service: Any,
    ) -> RunStatus:
        """执行完整的流程."""
        executor = context["executor"]
        injector = context.get("injector")
        validator = context.get("validator")
        recovery_service = context["recovery_service"]
        observation_collector = context["observation_collector"]

        # 更新状态为 preparing
        await self._update_run_status(scenario_run_id, RunStatus.PREPARING)

        # ===== 准备阶段 =====
        prepare_result = await self._execute_prepare_phase(
            scenario_run_id, context
        )
        if not prepare_result["success"]:
            logger.error("准备阶段失败")
            await self._record_step(
                scenario_run_id, StepType.PRECHECK, StepStatus.FAILED,
                prepare_result
            )
            return RunStatus.FAILED

        await self._record_step(
            scenario_run_id, StepType.PRECHECK, StepStatus.SUCCESS,
            prepare_result
        )

        # 采集初始观测
        context["observations"]["before"] = await observation_service.collect_before_inject(
            observation_collector, executor
        )

        # 更新状态为 injecting
        await self._update_run_status(scenario_run_id, RunStatus.INJECTING)

        # ===== 注入阶段 =====
        inject_result = await injector_service.execute_inject(
            scenario_run_id, context
        )
        context["inject_result"] = inject_result

        if not inject_result.get("success"):
            logger.error("注入阶段失败")
            context["inject_failed"] = True
            await self._update_run_status(scenario_run_id, RunStatus.RECOVERING)
            await recovery_service.execute_recovery_steps(executor, context)
            return RunStatus.FAILED

        # 采集注入后观测
        context["observations"]["after_inject"] = await observation_service.collect_after_inject(
            observation_collector, executor
        )

        # 更新状态为 validating
        await self._update_run_status(scenario_run_id, RunStatus.VALIDATING)

        # ===== 验证阶段 =====
        validation_result = await validation_service.execute_validation(
            scenario_run_id, context
        )
        context["validation_result"] = validation_result

        # 更新状态为 recovering
        await self._update_run_status(scenario_run_id, RunStatus.RECOVERING)

        # ===== 恢复阶段 =====
        recovery_result = await recovery_service.execute_recovery_steps(executor, context)
        context["recovery_result"] = recovery_result

        # 采集恢复后观测
        context["observations"]["after_recovery"] = await observation_service.collect_after_recovery(
            observation_collector, executor
        )

        # ===== 收集阶段 =====
        collect_result = await self._execute_collect_phase(scenario_run_id, context)

        # ===== 最终判定 =====
        judgment = self._make_final_judgment(context)
        context["judgment"] = judgment

        final_status = RunStatus(judgment.final_status)
        await self._update_run_status(scenario_run_id, final_status, finished=True)

        return final_status

    async def _execute_prepare_phase(
        self, scenario_run_id: int, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行准备阶段（带超时控制）."""
        executor = context["executor"]
        started_at = datetime.utcnow()
        timeout_sec = self._timeout_config["prepare"]

        result = {
            "success": True,
            "started_at": started_at.isoformat(),
            "finished_at": None,
            "details": {},
            "timeout_sec": timeout_sec,
        }

        try:
            async with asyncio.timeout(timeout_sec):
                online = await executor.is_online()
                if not online:
                    result["success"] = False
                    result["error"] = "device_offline"
                    result["message"] = "设备不在线"
                    return result

                properties = await executor.get_properties()
                result["details"]["properties"] = properties

                battery_info = await executor.get_battery_info()
                result["details"]["battery"] = {
                    "level": battery_info.level,
                    "status": battery_info.status,
                }

                storage_info = await executor.get_storage_info()
                result["details"]["storage"] = {
                    "total_mb": storage_info.total // (1024 * 1024),
                    "available_mb": storage_info.available // (1024 * 1024),
                }

                issues = []
                if battery_info.level < 20:
                    issues.append("low_battery")
                if storage_info.available < 100 * 1024 * 1024:
                    issues.append("storage_low")

                if issues:
                    result["success"] = False
                    result["error"] = "precheck_failed"
                    result["issues"] = issues
                    result["message"] = f"前置检查失败：{', '.join(issues)}"
                    return result

            result["finished_at"] = datetime.utcnow().isoformat()
            result["message"] = "准备阶段完成"

        except asyncio.TimeoutError:
            result["success"] = False
            result["error"] = "timeout"
            result["timeout"] = True
            result["message"] = f"准备阶段超时（{timeout_sec}秒）"
            logger.error(f"准备阶段超时：run_id={scenario_run_id}, timeout={timeout_sec}s")
            await self._record_step(
                scenario_run_id, StepType.PRECHECK, StepStatus.TIMEOUT, result
            )

        except Exception as e:
            result["success"] = False
            result["error"] = str(e)
            result["message"] = f"准备阶段异常：{str(e)}"
            logger.exception("准备阶段异常")

        return result

    async def _execute_collect_phase(
        self, scenario_run_id: int, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行收集阶段（带超时控制）."""
        executor = context["executor"]
        started_at = datetime.utcnow()
        timeout_sec = self._timeout_config["collect"]

        result = {
            "success": True,
            "started_at": started_at.isoformat(),
            "finished_at": None,
            "artifacts": [],
            "timeout_sec": timeout_sec,
        }

        try:
            async with asyncio.timeout(timeout_sec):
                if await executor.is_online():
                    logcat = await executor.get_logcat(1000)
                    properties = await executor.get_properties()
                    battery_info = await executor.get_battery_info()

                    collector = ArtifactCollector(scenario_run_id)
                    await collector.save_logcat(logcat)
                    await collector.save_getprop(properties)
                    await collector.save_battery_info({
                        "level": battery_info.level,
                        "status": battery_info.status,
                        "temperature": battery_info.temperature,
                    })

                    result["artifacts"] = ["logcat", "getprop", "battery"]

            result["finished_at"] = datetime.utcnow().isoformat()

            await self._record_step(
                scenario_run_id, StepType.COLLECT, StepStatus.SUCCESS, result
            )

        except asyncio.TimeoutError:
            result["success"] = False
            result["error"] = "timeout"
            result["timeout"] = True
            result["message"] = f"收集阶段超时（{timeout_sec}秒）"
            logger.error(f"收集阶段超时：run_id={scenario_run_id}, timeout={timeout_sec}s")
            await self._record_step(
                scenario_run_id, StepType.COLLECT, StepStatus.TIMEOUT, result
            )

        except Exception as e:
            result["success"] = False
            result["error"] = str(e)
            result["message"] = f"收集阶段异常：{str(e)}"
            logger.exception("收集阶段异常")
            await self._record_step(
                scenario_run_id, StepType.COLLECT, StepStatus.FAILED, result
            )

        return result

    def _make_final_judgment(self, context: Dict[str, Any]) -> JudgmentResult:
        """做出最终判定."""
        inject_result = context.get("inject_result")
        validation_result = context.get("validation_result")
        recovery_result = context.get("recovery_result")
        fault_profile = context.get("fault_profile", {})
        risk_level = fault_profile.get("risk_level", "medium")

        inject_data = None
        if inject_result:
            inject_data = {
                "success": inject_result.get("success", False),
                "fault_injected": inject_result.get("fault_injected", False),
            }

        validation_data = None
        if validation_result:
            validation_data = ValidationResult(
                passed=validation_result.get("passed", False),
                fault_observed=validation_result.get("fault_observed", False),
            )

        recovery_data = None
        if recovery_result:
            recovery_data = {
                "passed": recovery_result.get("passed", True),
            }

        judgment = judge_result(
            inject_result=inject_data,
            validation_result=validation_data,
            recovery_result=recovery_data,
            risk_level=risk_level,
        )

        logger.info(f"最终判定：{judgment.final_status}, {judgment.message}")
        return judgment

    async def _update_run_status(
        self, scenario_run_id: int, status: RunStatus, finished: bool = False
    ) -> None:
        """更新执行记录状态."""
        async with get_session_context() as session:
            result = await session.execute(
                select(ScenarioRun).where(ScenarioRun.id == scenario_run_id)
            )
            scenario_run = result.scalar_one_or_none()
            if scenario_run:
                if scenario_run.status == RunStatus.QUEUED.value:
                    scenario_run.started_at = datetime.utcnow()
                scenario_run.status = status.value
                if finished:
                    scenario_run.finished_at = datetime.utcnow()
                await session.commit()

    async def _record_step(
        self,
        scenario_run_id: int,
        step_type: StepType,
        step_status: StepStatus,
        summary: Dict[str, Any],
    ) -> None:
        """记录执行步骤."""
        async with get_session_context() as session:
            from sqlalchemy import select

            result = await session.execute(
                select(ScenarioStep)
                .where(ScenarioStep.scenario_run_id == scenario_run_id)
                .order_by(ScenarioStep.step_order.desc())
                .limit(1)
            )
            last_step = result.scalar_one_or_none()
            next_order = (last_step and last_step.step_order or 0) + 1

            step = ScenarioStep(
                scenario_run_id=scenario_run_id,
                step_type=step_type.value,
                step_order=next_order,
                status=step_status.value,
                started_at=datetime.utcnow(),
                finished_at=datetime.utcnow(),
                summary_json=json.dumps(summary, ensure_ascii=False),
            )
            session.add(step)
            await session.commit()

            logger.debug(f"记录步骤：{step_type.value} -> {step_status.value}")

    async def _generate_report(
        self,
        scenario_run_id: int,
        context: Dict[str, Any],
        final_status: RunStatus,
    ) -> None:
        """生成报告."""
        try:
            started_at = context.get("started_at")
            finished_at = datetime.utcnow()
            duration_sec = 0.0
            if started_at:
                duration_sec = (finished_at - started_at).total_seconds()

            report_data = ReportData(
                scenario_name=context.get("scenario_name", "Unknown"),
                device_serial=context.get("device_serial", ""),
                inject_stage=context.get("inject_stage", "precheck"),
                fault_type=context.get("fault_profile", {}).get("fault_type", ""),
                inject_summary=context.get("inject_result", {}),
                validation_summary=context.get("validation_result", {}),
                recovery_summary=context.get("recovery_result", {}),
                judgment=context.get("judgment"),
                evidence=context.get("observations", {}),
                started_at=started_at,
                finished_at=finished_at,
                duration_sec=duration_sec,
            )

            generator = ReportGenerator(scenario_run_id)
            paths = generator.save_reports(report_data)
            summary_json = generator.generate_summary_json(report_data)

            async with get_session_context() as session:
                report = Report(
                    scenario_run_id=scenario_run_id,
                    markdown_path=paths["markdown_path"],
                    html_path=paths["html_path"],
                    summary_json=summary_json,
                )
                session.add(report)

                result = await session.execute(
                    select(ScenarioRun).where(ScenarioRun.id == scenario_run_id)
                )
                scenario_run = result.scalar_one_or_none()
                if scenario_run:
                    scenario_run.result_summary_json = summary_json

                await session.commit()

            logger.info(f"报告已生成：{paths['markdown_path']}")

        except Exception as e:
            logger.exception(f"生成报告失败：{str(e)}")


# 全局编排服务实例
_orchestrator_service: Optional[ScenarioOrchestratorService] = None


def get_scenario_orchestrator_service() -> ScenarioOrchestratorService:
    """获取编排服务实例."""
    global _orchestrator_service
    if _orchestrator_service is None:
        _orchestrator_service = ScenarioOrchestratorService()
    return _orchestrator_service
