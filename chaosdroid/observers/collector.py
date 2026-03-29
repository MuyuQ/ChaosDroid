"""执行产物观测采集."""
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

from chaosdroid.config.settings import get_settings
from chaosdroid.models.base import ArtifactType


class ArtifactCollector:
    """产物采集器"""

    def __init__(self, scenario_run_id: int, step_id: Optional[int] = None):
        self.scenario_run_id = scenario_run_id
        self.step_id = step_id
        self.settings = get_settings()
        self.artifacts_dir = self.settings.get_artifacts_dir() / str(scenario_run_id)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    def get_artifact_path(self, artifact_type: str, suffix: str = "") -> Path:
        """获取产物路径"""
        filename = f"{artifact_type}{suffix}"
        if self.step_id:
            filename = f"step_{self.step_id}_{filename}"
        return self.artifacts_dir / filename

    async def save_stdout(self, stdout: str) -> Path:
        """保存标准输出"""
        path = self.get_artifact_path("stdout", ".log")
        path.write_text(stdout, encoding="utf-8")
        return path

    async def save_stderr(self, stderr: str) -> Path:
        """保存标准错误"""
        path = self.get_artifact_path("stderr", ".log")
        path.write_text(stderr, encoding="utf-8")
        return path

    async def save_summary(self, summary: Dict[str, Any]) -> Path:
        """保存步骤摘要"""
        path = self.get_artifact_path("summary", ".json")
        summary["saved_at"] = datetime.utcnow().isoformat()
        path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    async def save_logcat(self, logcat: str) -> Path:
        """保存logcat日志"""
        path = self.get_artifact_path("logcat", ".log")
        path.write_text(logcat, encoding="utf-8")
        return path

    async def save_getprop(self, properties: Dict[str, str]) -> Path:
        """保存设备属性"""
        path = self.get_artifact_path("getprop", ".json")
        path.write_text(json.dumps(properties, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    async def save_battery_info(self, battery_info: Dict[str, Any]) -> Path:
        """保存电池信息"""
        path = self.get_artifact_path("battery", ".json")
        path.write_text(json.dumps(battery_info, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    async def save_monkey_output(self, monkey_output: str) -> Path:
        """保存Monkey输出"""
        path = self.get_artifact_path("monkey", ".log")
        path.write_text(monkey_output, encoding="utf-8")
        return path

    async def save_snapshot(self, snapshot_name: str, snapshot: Dict[str, Any]) -> Path:
        """保存状态快照"""
        path = self.get_artifact_path(f"snapshot_{snapshot_name}", ".json")
        snapshot["snapshot_name"] = snapshot_name
        snapshot["captured_at"] = datetime.utcnow().isoformat()
        path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def get_artifact_info(self, path: Path, artifact_type: str) -> Dict[str, Any]:
        """获取产物信息"""
        size = path.stat().st_size if path.exists() else 0
        return {
            "artifact_type": artifact_type,
            "path": str(path),
            "size": size,
            "created_at": datetime.utcnow().isoformat()
        }

    async def collect_step_artifacts(
        self,
        stdout: Optional[str] = None,
        stderr: Optional[str] = None,
        summary: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """收集步骤产物"""
        artifacts = []

        if stdout:
            path = await self.save_stdout(stdout)
            artifacts.append(self.get_artifact_info(path, ArtifactType.STDOUT))

        if stderr:
            path = await self.save_stderr(stderr)
            artifacts.append(self.get_artifact_info(path, ArtifactType.STDERR))

        if summary:
            path = await self.save_summary(summary)
            artifacts.append(self.get_artifact_info(path, ArtifactType.SUMMARY))

        return artifacts

    async def collect_device_state(self, executor) -> Dict[str, Any]:
        """采集设备状态"""
        state = {
            "online": await executor.is_online(),
            "properties": await executor.get_properties() if await executor.is_online() else {},
            "storage": {},
            "battery": {}
        }

        if state["online"]:
            storage_info = await executor.get_storage_info()
            state["storage"] = {
                "total_mb": storage_info.total // (1024 * 1024),
                "available_mb": storage_info.available // (1024 * 1024),
                "used_mb": storage_info.used // (1024 * 1024)
            }

            battery_info = await executor.get_battery_info()
            state["battery"] = {
                "level": battery_info.level,
                "status": battery_info.status,
                "temperature": battery_info.temperature
            }

        return state


class ObservationCollector:
    """观测采集器"""

    def __init__(self, scenario_run_id: int):
        self.scenario_run_id = scenario_run_id
        self.collector = ArtifactCollector(scenario_run_id)

    async def collect_before_inject(self, executor) -> Dict[str, Any]:
        """注入前观测"""
        state = await self.collector.collect_device_state(executor)
        await self.collector.save_snapshot("before_inject", state)
        return state

    async def collect_after_inject(self, executor) -> Dict[str, Any]:
        """注入后观测"""
        state = await self.collector.collect_device_state(executor)
        await self.collector.save_snapshot("after_inject", state)

        # 采集logcat
        if await executor.is_online():
            logcat = await executor.get_logcat(1000)
            await self.collector.save_logcat(logcat)

        return state

    async def collect_after_recovery(self, executor) -> Dict[str, Any]:
        """恢复后观测"""
        state = await self.collector.collect_device_state(executor)
        await self.collector.save_snapshot("after_recovery", state)
        return state

    async def collect_full_observation(self, executor) -> Dict[str, Any]:
        """完整观测采集"""
        observations = {
            "before": await self.collect_before_inject(executor),
            "after_inject": {},
            "after_recovery": {}
        }

        observations["after_inject"] = await self.collect_after_inject(executor)
        observations["after_recovery"] = await self.collect_after_recovery(executor)

        return observations