"""结构化摘要文件解析器。

解析 device_snapshot.json, run_timeline.json, perf_summary.json 等结构化文件。
"""

import json
from typing import Optional

from app.diagnosis.enums import EventType, Severity, SourceType, Stage
from app.diagnosis.parsers.base import BaseParser
from app.diagnosis.schemas import NormalizedEvent


class ArtifactSummaryParser(BaseParser):
    """结构化摘要文件解析器。

    处理以下文件类型：
    - device_snapshot.json: 设备快照信息
    - run_timeline.json: 阶段执行时间线
    - perf_summary.json: 性能摘要
    - monkey.txt: 结构化摘要（JSON格式）
    """

    source_type = SourceType.ARTIFACT_SUMMARY
    default_event_type = EventType.SUMMARY_SIGNAL

    def parse(self, content: str, run_id: str) -> list[NormalizedEvent]:
        """
        解析结构化摘要内容，返回标准化事件列表。

        Args:
            content: 日志文件内容
            run_id: 任务ID

        Returns:
            标准化事件列表
        """
        # 检测是否为JSON格式
        stripped = content.strip()
        if not stripped.startswith("{") and not stripped.startswith("["):
            return []

        try:
            data = json.loads(stripped)
        except json.JSONDecodeError:
            return []

        # 根据JSON结构判断文件类型并解析
        if isinstance(data, dict):
            return self._parse_dict(data, run_id)
        elif isinstance(data, list):
            return self._parse_list(data, run_id)

        return []

    def _parse_dict(self, data: dict, run_id: str) -> list[NormalizedEvent]:
        """解析字典类型的JSON数据。"""
        events: list[NormalizedEvent] = []

        # 检测 device_snapshot.json 格式
        if self._is_device_snapshot(data):
            events.extend(self._parse_device_snapshot(data, run_id))

        # 检测 run_timeline.json 格式
        elif self._is_run_timeline(data):
            events.extend(self._parse_run_timeline(data, run_id))

        # 检测 perf_summary.json 格式
        elif self._is_perf_summary(data):
            events.extend(self._parse_perf_summary(data, run_id))

        return events

    def _parse_list(self, data: list, run_id: str) -> list[NormalizedEvent]:
        """解析列表类型的JSON数据。"""
        events: list[NormalizedEvent] = []

        for i, item in enumerate(data):
            if isinstance(item, dict):
                # 尝试解析为阶段信息
                event = self._try_parse_phase_item(item, run_id, i)
                if event:
                    events.append(event)

        return events

    def _is_device_snapshot(self, data: dict) -> bool:
        """判断是否为 device_snapshot.json 格式。"""
        device_keys = {"device_serial", "build_fingerprint", "battery_level", "device_model"}
        return bool(device_keys & data.keys())

    def _is_run_timeline(self, data: dict) -> bool:
        """判断是否为 run_timeline.json 格式。"""
        return "phases" in data

    def _is_perf_summary(self, data: dict) -> bool:
        """判断是否为 perf_summary.json 格式。"""
        perf_keys = {"total_duration", "phase_durations", "metrics"}
        return bool(perf_keys & data.keys())

    def _parse_device_snapshot(self, data: dict, run_id: str) -> list[NormalizedEvent]:
        """解析 device_snapshot.json 格式数据。"""
        events: list[NormalizedEvent] = []

        # 设备基本信息事件
        device_serial = data.get("device_serial")
        build_fingerprint = data.get("build_fingerprint")
        battery_level = data.get("battery_level")
        device_model = data.get("device_model")
        android_version = data.get("android_version")

        # 创建设备快照事件
        kv_payload = {
            "device_serial": device_serial,
            "build_fingerprint": build_fingerprint,
            "battery_level": battery_level,
            "device_model": device_model,
            "android_version": android_version,
        }
        # 过滤None值
        kv_payload = {k: v for k, v in kv_payload.items() if v is not None}

        event = self.create_event(
            run_id=run_id,
            normalized_code="DEVICE_SNAPSHOT",
            message=f"Device snapshot: {device_serial or 'unknown'}",
            stage=Stage.PRECHECK,
            severity=Severity.INFO,
            kv_payload=kv_payload,
        )
        events.append(event)

        # 检查电池电量警告
        if battery_level is not None:
            if battery_level < 20:
                event = self.create_event(
                    run_id=run_id,
                    normalized_code="LOW_BATTERY_WARNING",
                    message=f"Low battery level: {battery_level}%",
                    stage=Stage.PRECHECK,
                    severity=Severity.WARNING,
                    kv_payload={"battery_level": battery_level},
                )
                events.append(event)

        # 检查其他环境状态
        env_status = data.get("environment_status", {})
        if env_status:
            for key, value in env_status.items():
                if value in ("failed", "error", "critical"):
                    event = self.create_event(
                        run_id=run_id,
                        normalized_code=f"ENV_CHECK_{key.upper()}_{value.upper()}",
                        message=f"Environment check {key}: {value}",
                        stage=Stage.PRECHECK,
                        severity=Severity.ERROR if value == "critical" else Severity.WARNING,
                        kv_payload={"check_name": key, "check_result": value},
                    )
                    events.append(event)

        return events

    def _parse_run_timeline(self, data: dict, run_id: str) -> list[NormalizedEvent]:
        """解析 run_timeline.json 格式数据。"""
        events: list[NormalizedEvent] = []

        phases = data.get("phases", [])
        for phase in phases:
            event = self._parse_phase(phase, run_id)
            if event:
                events.append(event)

        return events

    def _parse_phase(self, phase: dict, run_id: str) -> Optional[NormalizedEvent]:
        """解析单个阶段信息。"""
        name = phase.get("name")
        duration = phase.get("duration")
        status = phase.get("status")

        if not name:
            return None

        # 映射阶段名称到Stage枚举
        stage = self._map_stage_name(name)

        # 映射状态到严重级别
        severity = self._map_status_to_severity(status)

        # 生成normalized_code
        status_code = status.upper() if status else "UNKNOWN"
        normalized_code = f"PHASE_{name.upper()}_{status_code}"

        message = f"Phase {name}"
        if duration is not None:
            message += f" (duration: {duration}s)"
        if status:
            message += f" - {status}"

        kv_payload = {
            "phase_name": name,
            "phase_duration": duration,
            "phase_status": status,
        }
        kv_payload = {k: v for k, v in kv_payload.items() if v is not None}

        return self.create_event(
            run_id=run_id,
            normalized_code=normalized_code,
            message=message,
            stage=stage,
            severity=severity,
            kv_payload=kv_payload,
        )

    def _map_stage_name(self, name: str) -> Stage:
        """将阶段名称映射到Stage枚举。"""
        stage_mapping = {
            "precheck": Stage.PRECHECK,
            "package_prepare": Stage.PACKAGE_PREPARE,
            "apply_update": Stage.APPLY_UPDATE,
            "reboot_wait": Stage.REBOOT_WAIT,
            "post_reboot": Stage.POST_REBOOT,
            "post_validate": Stage.POST_VALIDATE,
        }
        return stage_mapping.get(name.lower(), Stage.PRECHECK)

    def _map_status_to_severity(self, status: Optional[str]) -> Severity:
        """将状态映射到严重级别。"""
        if not status:
            return Severity.INFO

        status_lower = status.lower()
        severity_mapping = {
            "passed": Severity.INFO,
            "success": Severity.INFO,
            "failed": Severity.ERROR,
            "error": Severity.ERROR,
            "warning": Severity.WARNING,
            "skipped": Severity.INFO,
            "running": Severity.INFO,
            "pending": Severity.INFO,
        }
        return severity_mapping.get(status_lower, Severity.INFO)

    def _parse_perf_summary(self, data: dict, run_id: str) -> list[NormalizedEvent]:
        """解析 perf_summary.json 格式数据。"""
        events: list[NormalizedEvent] = []

        total_duration = data.get("total_duration")
        phase_durations = data.get("phase_durations", {})
        metrics = data.get("metrics", {})

        # 创建总体性能摘要事件
        kv_payload = {}
        if total_duration is not None:
            kv_payload["total_duration"] = total_duration

        event = self.create_event(
            run_id=run_id,
            normalized_code="PERF_SUMMARY",
            message=f"Performance summary: total duration {total_duration}s" if total_duration else "Performance summary",
            stage=Stage.POST_VALIDATE,
            severity=Severity.INFO,
            kv_payload=kv_payload if kv_payload else None,
        )
        events.append(event)

        # 为每个阶段创建事件
        for phase_name, duration in phase_durations.items():
            stage = self._map_stage_name(phase_name)
            event = self.create_event(
                run_id=run_id,
                normalized_code=f"PERF_PHASE_{phase_name.upper()}",
                message=f"Phase {phase_name} duration: {duration}s",
                stage=stage,
                severity=Severity.INFO,
                kv_payload={"phase_duration": duration},
            )
            events.append(event)

        # 为性能指标创建事件
        for metric_name, value in metrics.items():
            severity = Severity.INFO
            # 检查是否有性能问题标记
            if isinstance(value, dict):
                actual_value = value.get("value")
                threshold = value.get("threshold")
                exceeded = value.get("exceeded", False)

                if exceeded:
                    severity = Severity.WARNING

                event = self.create_event(
                    run_id=run_id,
                    normalized_code=f"PERF_METRIC_{metric_name.upper()}",
                    message=f"Metric {metric_name}: {actual_value}" + (f" (threshold: {threshold})" if threshold else ""),
                    stage=Stage.POST_VALIDATE,
                    severity=severity,
                    kv_payload={
                        "metric_name": metric_name,
                        "metric_value": actual_value,
                        "threshold": threshold,
                        "exceeded": exceeded,
                    },
                )
            else:
                event = self.create_event(
                    run_id=run_id,
                    normalized_code=f"PERF_METRIC_{metric_name.upper()}",
                    message=f"Metric {metric_name}: {value}",
                    stage=Stage.POST_VALIDATE,
                    severity=severity,
                    kv_payload={"metric_name": metric_name, "metric_value": value},
                )
            events.append(event)

        return events

    def _try_parse_phase_item(self, item: dict, run_id: str, index: int) -> Optional[NormalizedEvent]:
        """尝试解析列表中的阶段项。"""
        # 检查是否包含阶段相关的键
        if "name" in item and ("status" in item or "duration" in item):
            return self._parse_phase(item, run_id)

        return None