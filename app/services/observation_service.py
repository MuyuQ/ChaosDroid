"""观测服务模块.

负责观测数据的采集，包括注入前、注入后和恢复后的数据采集。
"""
import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from app.executors.base import BaseDeviceExecutor
from app.observers.collector import ArtifactCollector, ObservationCollector

logger = logging.getLogger(__name__)


class ObservationService:
    """观测服务.

    负责：
    - 采集注入前观测数据
    - 采集注入后观测数据
    - 采集恢复后观测数据
    - 处理采集超时和异常
    """

    def __init__(self, collect_timeout: int = 60):
        """初始化观测服务.

        Args:
            collect_timeout: 收集阶段超时（秒）
        """
        self._collect_timeout = collect_timeout

    async def collect_before_inject(
        self,
        observation_collector: ObservationCollector,
        executor: BaseDeviceExecutor,
    ) -> Dict[str, Any]:
        """采集注入前观测数据.

        Args:
            observation_collector: 观测采集器实例
            executor: 设备执行器

        Returns:
            观测数据字典
        """
        try:
            async with asyncio.timeout(self._collect_timeout):
                observations = await observation_collector.collect_before_inject(executor)
                logger.info("已采集注入前观测数据")
                return observations

        except asyncio.TimeoutError:
            logger.error("采集注入前观测数据超时")
            return {"error": "timeout", "message": "采集超时"}

        except Exception as e:
            logger.exception(f"采集注入前观测数据异常：{str(e)}")
            return {"error": str(e), "message": "采集异常"}

    async def collect_after_inject(
        self,
        observation_collector: ObservationCollector,
        executor: BaseDeviceExecutor,
    ) -> Dict[str, Any]:
        """采集注入后观测数据.

        Args:
            observation_collector: 观测采集器实例
            executor: 设备执行器

        Returns:
            观测数据字典
        """
        try:
            async with asyncio.timeout(self._collect_timeout):
                observations = await observation_collector.collect_after_inject(executor)
                logger.info("已采集注入后观测数据")
                return observations

        except asyncio.TimeoutError:
            logger.error("采集注入后观测数据超时")
            return {"error": "timeout", "message": "采集超时"}

        except Exception as e:
            logger.exception(f"采集注入后观测数据异常：{str(e)}")
            return {"error": str(e), "message": "采集异常"}

    async def collect_after_recovery(
        self,
        observation_collector: ObservationCollector,
        executor: BaseDeviceExecutor,
    ) -> Dict[str, Any]:
        """采集恢复后观测数据.

        Args:
            observation_collector: 观测采集器实例
            executor: 设备执行器

        Returns:
            观测数据字典
        """
        try:
            async with asyncio.timeout(self._collect_timeout):
                observations = await observation_collector.collect_after_recovery(executor)
                logger.info("已采集恢复后观测数据")
                return observations

        except asyncio.TimeoutError:
            logger.error("采集恢复后观测数据超时")
            return {"error": "timeout", "message": "采集超时"}

        except Exception as e:
            logger.exception(f"采集恢复后观测数据异常：{str(e)}")
            return {"error": str(e), "message": "采集异常"}

    async def collect_all(
        self,
        scenario_run_id: int,
        executor: BaseDeviceExecutor,
    ) -> Dict[str, Any]:
        """执行完整的数据收集（用于收集阶段）.

        Args:
            scenario_run_id: 场景执行记录 ID
            executor: 设备执行器

        Returns:
            收集结果
        """
        started_at = datetime.utcnow()

        result = {
            "success": True,
            "started_at": started_at.isoformat(),
            "finished_at": None,
            "artifacts": [],
            "timeout_sec": self._collect_timeout,
        }

        try:
            async with asyncio.timeout(self._collect_timeout):
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
            result["message"] = "收集完成"

        except asyncio.TimeoutError:
            result["success"] = False
            result["error"] = "timeout"
            result["timeout"] = True
            result["message"] = f"收集阶段超时（{self._collect_timeout}秒）"
            logger.error(f"收集阶段超时：timeout={self._collect_timeout}s")

        except Exception as e:
            result["success"] = False
            result["error"] = str(e)
            result["message"] = f"收集阶段异常：{str(e)}"
            logger.exception("收集阶段异常")

        return result


# 全局观测服务实例
_observation_service: Optional[ObservationService] = None


def get_observation_service() -> ObservationService:
    """获取观测服务实例."""
    global _observation_service
    if _observation_service is None:
        _observation_service = ObservationService()
    return _observation_service
