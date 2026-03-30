"""注入器基类和注册机制."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional

# 从 models 模块导入枚举，避免重复定义
from chaosdroid.models.base import FaultType, RiskLevel


@dataclass
class InjectContext:
    """注入上下文"""
    scenario_run_id: int
    device_serial: str
    executor: Any  # BaseDeviceExecutor
    fault_profile: Dict[str, Any]
    artifacts_dir: str
    started_at: datetime = field(default_factory=datetime.utcnow)
    inject_stage: str = "precheck"


@dataclass
class InjectResult:
    """注入结果"""
    success: bool
    fault_type: str
    fault_injected: bool
    fault_observed: bool
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    cleanup_required: bool = True


class BaseInjector(ABC):
    """注入器基类"""

    fault_type: FaultType
    risk_level: RiskLevel = RiskLevel.medium

    @abstractmethod
    async def prepare(self, context: InjectContext) -> bool:
        """
        准备注入环境

        Returns:
            True if preparation succeeded, False otherwise
        """
        pass

    @abstractmethod
    async def inject(self, context: InjectContext) -> InjectResult:
        """
        执行故障注入

        Returns:
            InjectResult with injection status and details
        """
        pass

    @abstractmethod
    async def cleanup(self, context: InjectContext) -> bool:
        """
        清理注入，恢复环境

        Returns:
            True if cleanup succeeded, False otherwise
        """
        pass

    def get_risk_level(self) -> RiskLevel:
        """获取风险等级"""
        return self.risk_level

    def get_description(self) -> str:
        """获取故障类型描述"""
        descriptions = {
            FaultType.storage_pressure: "向目标目录写入占位文件，模拟存储压力",
            FaultType.low_battery: "模拟低电量条件",
            FaultType.network_jitter: "模拟网络波动、超时、恢复",
            FaultType.reboot_timeout: "模拟重启超时，boot_completed未置位",
            FaultType.cpu_io_stress: "在设备上启动压力任务",
            FaultType.monkey_stability: "启动monkey，采集输出统计crash/ANR",
        }
        return descriptions.get(self.fault_type, "未知故障类型")


# 注入器注册表
INJECTOR_REGISTRY: Dict[str, BaseInjector] = {}


def register_injector(injector: BaseInjector):
    """注册注入器"""
    INJECTOR_REGISTRY[injector.fault_type] = injector


def get_injector(fault_type: str) -> Optional[BaseInjector]:
    """获取注入器"""
    return INJECTOR_REGISTRY.get(fault_type)


def list_injectors() -> Dict[str, BaseInjector]:
    """列出所有注册的注入器"""
    return INJECTOR_REGISTRY.copy()