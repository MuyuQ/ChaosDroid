"""测试数据工厂模块.

提供用于创建测试数据的工厂类，支持 Scenario、Device、Run 等模型的快速创建。
"""
import random
import json
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, List

from app.models import (
    FaultProfile,
    ValidationProfile,
    RecoveryProfile,
    ScenarioTemplate,
    ScenarioRun,
    ScenarioStep,
    Device,
    DevicePool,
    DeviceLease,
    Report,
    RunStatus,
    StepStatus,
    StepType,
    FaultType,
    InjectStage,
    TargetType,
    RiskLevel,
    ExecutorMode,
    DeviceStatus,
    DevicePoolPurpose,
    LeaseStatus,
    Priority,
)


class BaseFactory:
    """基础工厂类，提供通用方法."""

    @classmethod
    def _random_choice(cls, choices: List[Any]) -> Any:
        """从列表中随机选择一个元素."""
        return random.choice(choices)

    @classmethod
    def _random_id(cls, prefix: str = "") -> str:
        """生成随机 ID 字符串."""
        return f"{prefix}{random.randint(1000, 9999)}"


class FaultProfileFactory(BaseFactory):
    """故障配置工厂."""

    FAULT_TYPE_PARAMS: Dict[str, Dict[str, Any]] = {
        FaultType.storage_pressure: {"pressure_mb": 500, "target_path": "/sdcard/test"},
        FaultType.low_battery: {"level": 10, "duration_sec": 60},
        FaultType.network_jitter: {"delay_ms": 500, "packet_loss": 0.1, "duration_sec": 30},
        FaultType.reboot_timeout: {"timeout_sec": 300},
        FaultType.cpu_io_stress: {"cpu_threads": 2, "io_operations": 100},
        FaultType.monkey_stability: {"event_count": 1000, "package": "com.mock.app"},
    }

    @classmethod
    def create(
        cls,
        name: Optional[str] = None,
        fault_type: Optional[FaultType] = None,
        parameters: Optional[Dict[str, Any]] = None,
        risk_level: Optional[RiskLevel] = None,
        is_active: bool = True,
        **kwargs,
    ) -> FaultProfile:
        """创建故障配置.

        Args:
            name: 配置名称
            fault_type: 故障类型
            parameters: 故障参数
            risk_level: 风险等级
            is_active: 是否激活

        Returns:
            FaultProfile: 故障配置实例
        """
        if fault_type is None:
            fault_type = cls._random_choice(list(FaultType))

        if parameters is None:
            parameters = cls.FAULT_TYPE_PARAMS.get(fault_type, {})

        if risk_level is None:
            risk_level = RiskLevel.medium

        return FaultProfile(
            name=name or f"Fault Profile {cls._random_id()}",
            fault_type=fault_type.value if hasattr(fault_type, 'value') else str(fault_type),
            parameters=parameters,
            risk_level=risk_level.value if hasattr(risk_level, 'value') else str(risk_level),
            is_active=is_active,
            **kwargs,
        )


class ValidationProfileFactory(BaseFactory):
    """验证配置工厂."""

    CHECKS_TEMPLATES: Dict[str, List[str]] = {
        "basic": ["boot_completed", "battery_ok", "network_connected"],
        "storage": ["storage_available", "storage_readable", "storage_writable"],
        "network": ["wifi_connected", "dns_resolvable", "http_reachable"],
        "app": ["app_installed", "app_launchable", "app_responsive"],
        "complete": ["boot_completed", "battery_ok", "network_connected", "app_installed", "app_launchable"],
    }

    @classmethod
    def create(
        cls,
        name: Optional[str] = None,
        checks: Optional[List[str]] = None,
        timeout_sec: int = 180,
        **kwargs,
    ) -> ValidationProfile:
        """创建验证配置.

        Args:
            name: 配置名称
            checks: 验证检查项列表
            timeout_sec: 超时时间（秒）

        Returns:
            ValidationProfile: 验证配置实例
        """
        if checks is None:
            checks = cls._random_choice(list(cls.CHECKS_TEMPLATES.values()))

        return ValidationProfile(
            name=name or f"Validation Profile {cls._random_id()}",
            checks_json=json.dumps(checks),
            timeout_sec=timeout_sec,
            **kwargs,
        )


class RecoveryProfileFactory(BaseFactory):
    """恢复配置工厂."""

    STEPS_TEMPLATES: Dict[str, List[Dict[str, Any]]] = {
        "basic": [
            {"action": "cleanup_storage", "required": True},
            {"action": "check_connectivity", "required": True},
        ],
        "reboot": [
            {"action": "reboot_device", "required": True},
            {"action": "wait_boot", "required": True, "timeout": 120},
            {"action": "verify_boot", "required": True},
        ],
        "network": [
            {"action": "reset_network", "required": True},
            {"action": "verify_network", "required": True},
        ],
        "full": [
            {"action": "stop_stress", "required": False},
            {"action": "cleanup_storage", "required": True},
            {"action": "reset_battery", "required": False},
            {"action": "reset_network", "required": True},
            {"action": "verify_all", "required": True},
        ],
    }

    @classmethod
    def create(
        cls,
        name: Optional[str] = None,
        steps: Optional[List[Dict[str, Any]]] = None,
        manual_intervention_allowed: bool = True,
        timeout_sec: int = 300,
        **kwargs,
    ) -> RecoveryProfile:
        """创建恢复配置.

        Args:
            name: 配置名称
            steps: 恢复步骤列表
            manual_intervention_allowed: 是否允许手动干预
            timeout_sec: 超时时间（秒）

        Returns:
            RecoveryProfile: 恢复配置实例
        """
        if steps is None:
            steps = cls._random_choice(list(cls.STEPS_TEMPLATES.values()))

        return RecoveryProfile(
            name=name or f"Recovery Profile {cls._random_id()}",
            steps_json=json.dumps(steps),
            manual_intervention_allowed=manual_intervention_allowed,
            timeout_sec=timeout_sec,
            **kwargs,
        )


class ScenarioTemplateFactory(BaseFactory):
    """场景模板工厂."""

    TARGET_TYPES = [TargetType.STABILITY, TargetType.MONKEY, TargetType.RECOVERY, TargetType.UPGRADE]
    STAGES = [InjectStage.PRECHECK, InjectStage.PREPARE, InjectStage.POST_BOOT]
    MODES = [ExecutorMode.MOCK, ExecutorMode.REAL]

    @classmethod
    def create(
        cls,
        name: Optional[str] = None,
        description: Optional[str] = None,
        target_type: Optional[TargetType] = None,
        fault_profile_id: Optional[int] = None,
        validation_profile_id: Optional[int] = None,
        recovery_profile_id: Optional[int] = None,
        inject_stage: Optional[InjectStage] = None,
        executor_mode: Optional[ExecutorMode] = None,
        enabled: bool = True,
        **kwargs,
    ) -> ScenarioTemplate:
        """创建场景模板.

        Args:
            name: 场景名称
            description: 场景描述
            target_type: 目标类型
            fault_profile_id: 故障配置 ID
            validation_profile_id: 验证配置 ID
            recovery_profile_id: 恢复配置 ID
            inject_stage: 注入阶段
            executor_mode: 执行器模式
            enabled: 是否启用

        Returns:
            ScenarioTemplate: 场景模板实例
        """
        return ScenarioTemplate(
            name=name or f"Scenario {cls._random_id()}",
            description=description or "Test scenario created by factory",
            target_type=target_type.value if target_type else cls._random_choice(cls.TARGET_TYPES).value,
            fault_profile_id=fault_profile_id or 1,
            validation_profile_id=validation_profile_id or 1,
            recovery_profile_id=recovery_profile_id or 1,
            inject_stage=inject_stage.value if inject_stage else cls._random_choice(cls.STAGES).value,
            executor_mode=executor_mode.value if executor_mode else cls._random_choice(cls.MODES).value,
            enabled=enabled,
            **kwargs,
        )


class ScenarioRunFactory(BaseFactory):
    """场景执行记录工厂."""

    STATUSES = [RunStatus.QUEUED, RunStatus.PREPARING, RunStatus.INJECTING,
                RunStatus.VALIDATING, RunStatus.RECOVERING, RunStatus.PASSED,
                RunStatus.FAILED, RunStatus.PARTIAL]

    @classmethod
    def create(
        cls,
        scenario_template_id: int = 1,
        device_serial: Optional[str] = None,
        status: Optional[RunStatus] = None,
        inject_stage: Optional[InjectStage] = None,
        started_at: Optional[datetime] = None,
        **kwargs,
    ) -> ScenarioRun:
        """创建场景执行记录.

        Args:
            scenario_template_id: 场景模板 ID
            device_serial: 设备序列号
            status: 执行状态
            inject_stage: 注入阶段
            started_at: 开始时间

        Returns:
            ScenarioRun: 场景执行记录实例
        """
        return ScenarioRun(
            scenario_template_id=scenario_template_id,
            device_serial=device_serial or f"device_{cls._random_id()}",
            status=status.value if status else RunStatus.queued.value,
            inject_stage=inject_stage.value if inject_stage else InjectStage.precheck.value,
            started_at=started_at,
            **kwargs,
        )


class ScenarioStepFactory(BaseFactory):
    """场景步骤工厂."""

    STEP_TYPES = [StepType.PRECHECK, StepType.INJECT, StepType.OBSERVE,
                  StepType.VALIDATE, StepType.RECOVER, StepType.COLLECT]
    STATUSES = [StepStatus.PENDING, StepStatus.RUNNING, StepStatus.SUCCESS,
                StepStatus.FAILED, StepStatus.SKIPPED]

    @classmethod
    def create(
        cls,
        scenario_run_id: int = 1,
        step_type: Optional[StepType] = None,
        step_order: int = 1,
        status: Optional[StepStatus] = None,
        **kwargs,
    ) -> ScenarioStep:
        """创建场景步骤.

        Args:
            scenario_run_id: 场景执行记录 ID
            step_type: 步骤类型
            step_order: 步骤顺序
            status: 步骤状态

        Returns:
            ScenarioStep: 场景步骤实例
        """
        return ScenarioStep(
            scenario_run_id=scenario_run_id,
            step_type=step_type.value if step_type else cls._random_choice(cls.STEP_TYPES).value,
            step_order=step_order,
            status=status.value if status else StepStatus.pending.value,
            **kwargs,
        )


class DeviceFactory(BaseFactory):
    """设备工厂."""

    MODELS = ["Pixel 6", "Pixel 7", "Galaxy S23", "OnePlus 11", "Xiaomi 13"]
    BRANDS = ["Google", "Samsung", "OnePlus", "Xiaomi"]
    STATUS_LIST = [DeviceStatus.IDLE, DeviceStatus.BUSY, DeviceStatus.OFFLINE, DeviceStatus.RECOVERING]

    @classmethod
    def create(
        cls,
        serial: Optional[str] = None,
        model: Optional[str] = None,
        brand: Optional[str] = None,
        status: Optional[DeviceStatus] = None,
        pool_id: Optional[int] = None,
        is_active: bool = True,
        **kwargs,
    ) -> Device:
        """创建设备.

        Args:
            serial: 设备序列号
            model: 设备型号
            brand: 设备品牌
            status: 设备状态
            pool_id: 所属设备池 ID
            is_active: 是否激活

        Returns:
            Device: 设备实例
        """
        return Device(
            serial=serial or cls._random_id("device_"),
            model=model or cls._random_choice(cls.MODELS),
            brand=brand or cls._random_choice(cls.BRANDS),
            status=status.value if status else cls._random_choice(cls.STATUS_LIST).value,
            pool_id=pool_id,
            is_active=is_active,
            **kwargs,
        )

    @classmethod
    def create_batch(cls, count: int, **kwargs) -> List[Device]:
        """批量创建设备.

        Args:
            count: 创建数量

        Returns:
            List[Device]: 设备实例列表
        """
        return [cls.create(serial=f"device_{i:04d}", **kwargs) for i in range(count)]


class DevicePoolFactory(BaseFactory):
    """设备池工厂."""

    PURPOSES = [DevicePoolPurpose.STABLE, DevicePoolPurpose.STRESS, DevicePoolPurpose.EMERGENCY]

    @classmethod
    def create(
        cls,
        name: Optional[str] = None,
        purpose: Optional[DevicePoolPurpose] = None,
        description: Optional[str] = None,
        is_active: bool = True,
        **kwargs,
    ) -> DevicePool:
        """创建设备池.

        Args:
            name: 设备池名称
            purpose: 设备池用途
            description: 设备池描述
            is_active: 是否激活

        Returns:
            DevicePool: 设备池实例
        """
        return DevicePool(
            name=name or f"Device Pool {cls._random_id()}",
            purpose=purpose.value if purpose else cls._random_choice(cls.PURPOSES).value,
            description=description or "Device pool created by factory",
            is_active=is_active,
            **kwargs,
        )


class DeviceLeaseFactory(BaseFactory):
    """设备租赁记录工厂."""

    LEASE_STATUSES = [LeaseStatus.ACTIVE, LeaseStatus.RELEASED, LeaseStatus.EXPIRED, LeaseStatus.PREEMPTED]

    @classmethod
    def create(
        cls,
        device_id: int = 1,
        worker_id: Optional[str] = None,
        status: Optional[LeaseStatus] = None,
        expires_at: Optional[datetime] = None,
        **kwargs,
    ) -> DeviceLease:
        """创建设备租赁记录.

        Args:
            device_id: 设备 ID
            worker_id: 工作者 ID
            status: 租赁状态
            expires_at: 过期时间

        Returns:
            DeviceLease: 设备租赁记录实例
        """
        if expires_at is None:
            expires_at = datetime.utcnow() + timedelta(hours=1)

        return DeviceLease(
            device_id=device_id,
            worker_id=worker_id or f"worker_{cls._random_id()}",
            status=status.value if status else LeaseStatus.active.value,
            expires_at=expires_at,
            **kwargs,
        )


class ReportFactory(BaseFactory):
    """报告工厂."""

    @classmethod
    def create(
        cls,
        scenario_run_id: int = 1,
        markdown_path: Optional[str] = None,
        html_path: Optional[str] = None,
        summary_json: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Report:
        """创建测试报告.

        Args:
            scenario_run_id: 场景执行记录 ID
            markdown_path: Markdown 报告路径
            html_path: HTML 报告路径
            summary_json: 报告摘要数据

        Returns:
            Report: 报告实例
        """
        default_summary = {
            "total_steps": 5,
            "passed_steps": 4,
            "failed_steps": 1,
            "duration_sec": 300,
            "result": "partial",
        }

        return Report(
            scenario_run_id=scenario_run_id,
            markdown_path=markdown_path or f"reports/report_{cls._random_id()}.md",
            html_path=html_path or f"reports/report_{cls._random_id()}.html",
            summary_json=json.dumps(summary_json or default_summary),
            **kwargs,
        )


class ScenarioFactory(BaseFactory):
    """场景工厂（组合工厂，用于创建完整场景）."""

    @classmethod
    def create_full_scenario(
        cls,
        name: Optional[str] = None,
        device_serial: Optional[str] = None,
        mode: ExecutorMode = ExecutorMode.MOCK,
    ) -> Dict[str, Any]:
        """创建完整的测试场景（包括配置、执行记录等）.

        Args:
            name: 场景名称
            device_serial: 设备序列号
            mode: 执行器模式

        Returns:
            Dict[str, Any]: 包含所有相关对象的字典
        """
        # 创建配置
        fault_profile = FaultProfileFactory.create(name=f"{name or 'Test'} Fault Profile")
        validation_profile = ValidationProfileFactory.create(name=f"{name or 'Test'} Validation Profile")
        recovery_profile = RecoveryProfileFactory.create(name=f"{name or 'Test'} Recovery Profile")

        # 创建场景模板
        scenario_template = ScenarioTemplateFactory.create(
            name=name or f"Full Scenario {cls._random_id()}",
            fault_profile_id=1,  # 实际使用时需要 flush 后获取真实 ID
            validation_profile_id=2,
            recovery_profile_id=3,
            executor_mode=ExecutorMode.MOCK if mode == ExecutorMode.MOCK else ExecutorMode.REAL,
        )

        # 创建设备
        device = DeviceFactory.create(serial=device_serial)

        # 创建执行记录
        run = ScenarioRunFactory.create(
            scenario_template_id=1,
            device_serial=device_serial or "test_device_001",
        )

        return {
            "fault_profile": fault_profile,
            "validation_profile": validation_profile,
            "recovery_profile": recovery_profile,
            "scenario_template": scenario_template,
            "device": device,
            "run": run,
        }


# 导出所有工厂
__all__ = [
    "BaseFactory",
    "FaultProfileFactory",
    "ValidationProfileFactory",
    "RecoveryProfileFactory",
    "ScenarioTemplateFactory",
    "ScenarioRunFactory",
    "ScenarioStepFactory",
    "DeviceFactory",
    "DevicePoolFactory",
    "DeviceLeaseFactory",
    "ReportFactory",
    "ScenarioFactory",
]
