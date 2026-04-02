"""Update Engine日志解析器。"""

import re
from typing import Optional

from app.diagnosis.enums import EventType, Severity, SourceType, Stage
from app.diagnosis.parsers.base import BaseParser
from app.diagnosis.schemas import NormalizedEvent


class UpdateEngineParser(BaseParser):
    """解析update_engine.log文件。"""

    source_type = SourceType.UPDATE_ENGINE_LOG

    # 时间戳正则: [2026-03-28 12:00:01.120]
    TIMESTAMP_PATTERN = re.compile(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\]")

    # 状态映射: (状态值, normalized_code, stage, severity, event_type)
    STATUS_MAPPING = {
        "CHECKING_FOR_UPDATE": (
            "UE_STATUS_CHECKING",
            Stage.PRECHECK,
            Severity.INFO,
            EventType.STATUS_TRANSITION,
        ),
        "UPDATE_AVAILABLE": (
            "UE_STATUS_AVAILABLE",
            Stage.PACKAGE_PREPARE,
            Severity.INFO,
            EventType.STATUS_TRANSITION,
        ),
        "DOWNLOADING": (
            "UE_STATUS_DOWNLOADING",
            Stage.APPLY_UPDATE,
            Severity.INFO,
            EventType.PROGRESS_SIGNAL,
        ),
        "VERIFYING": (
            "UE_STATUS_VERIFYING",
            Stage.APPLY_UPDATE,
            Severity.INFO,
            EventType.STATUS_TRANSITION,
        ),
        "FINALIZING": (
            "UE_STATUS_FINALIZING",
            Stage.APPLY_UPDATE,
            Severity.INFO,
            EventType.STATUS_TRANSITION,
        ),
        "UPDATED_NEED_REBOOT": (
            "UE_STATUS_UPDATED_NEED_REBOOT",
            Stage.REBOOT_WAIT,
            Severity.INFO,
            EventType.STATUS_TRANSITION,
        ),
    }

    # 错误模式映射: (模式, normalized_code, stage, severity, event_type)
    ERROR_PATTERNS = [
        (
            r"exceeded half of allocatable space",
            "DP_ALLOCATABLE_SPACE_EXCEEDED",
            Stage.PACKAGE_PREPARE,
            Severity.ERROR,
            EventType.ERROR_SIGNAL,
        ),
    ]

    # 成功启动模式
    BOOT_SUCCESS_PATTERN = re.compile(r"booted into new slot")

    def parse(self, content: str, run_id: str) -> list[NormalizedEvent]:
        """
        解析update_engine.log内容，返回标准化事件列表。

        Args:
            content: 日志文件内容
            run_id: 任务ID

        Returns:
            标准化事件列表
        """
        events: list[NormalizedEvent] = []
        lines = content.strip().split("\n")

        for line_no, line in enumerate(lines, start=1):
            line = line.strip()
            if not line:
                continue

            event = self._parse_line(line, run_id, line_no)
            if event:
                events.append(event)

        return events

    def _parse_line(
        self, line: str, run_id: str, line_no: int
    ) -> Optional[NormalizedEvent]:
        """
        解析单行日志。

        Args:
            line: 日志行
            run_id: 任务ID
            line_no: 行号

        Returns:
            NormalizedEvent或None
        """
        # 提取时间戳
        timestamp = self._extract_timestamp(line)

        # 尝试匹配状态行
        event = self._parse_status_line(line, run_id, line_no, timestamp)
        if event:
            return event

        # 尝试匹配错误模式
        event = self._parse_error_line(line, run_id, line_no, timestamp)
        if event:
            return event

        # 尝试匹配启动成功
        event = self._parse_boot_success(line, run_id, line_no, timestamp)
        if event:
            return event

        return None

    def _extract_timestamp(self, line: str) -> Optional[str]:
        """从日志行提取时间戳。"""
        match = self.TIMESTAMP_PATTERN.search(line)
        if match:
            return match.group(1)
        return None

    def _parse_status_line(
        self, line: str, run_id: str, line_no: int, timestamp: Optional[str]
    ) -> Optional[NormalizedEvent]:
        """解析状态行。"""
        # 匹配 status=XXX 模式
        status_match = re.search(r"status=(\w+)", line)
        if not status_match:
            return None

        status = status_match.group(1)
        if status not in self.STATUS_MAPPING:
            return None

        normalized_code, stage, severity, event_type = self.STATUS_MAPPING[status]

        # 提取额外的键值对作为 payload
        kv_payload = self._extract_kv_payload(line, exclude_keys=["status"])

        return self.create_event(
            run_id=run_id,
            normalized_code=normalized_code,
            message=f"Update engine status: {status}",
            stage=stage,
            event_type=event_type,
            severity=severity,
            timestamp=timestamp,
            line_no=line_no,
            raw_line=line,
            kv_payload=kv_payload if kv_payload else None,
        )

    def _parse_error_line(
        self, line: str, run_id: str, line_no: int, timestamp: Optional[str]
    ) -> Optional[NormalizedEvent]:
        """解析错误行。"""
        for pattern, code, stage, severity, event_type in self.ERROR_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                return self.create_event(
                    run_id=run_id,
                    normalized_code=code,
                    message=line,
                    stage=stage,
                    event_type=event_type,
                    severity=severity,
                    timestamp=timestamp,
                    line_no=line_no,
                    raw_line=line,
                )
        return None

    def _parse_boot_success(
        self, line: str, run_id: str, line_no: int, timestamp: Optional[str]
    ) -> Optional[NormalizedEvent]:
        """解析启动成功行。"""
        if self.BOOT_SUCCESS_PATTERN.search(line):
            return self.create_event(
                run_id=run_id,
                normalized_code="UE_BOOT_SUCCESS",
                message="Booted into new slot successfully",
                stage=Stage.POST_REBOOT,
                event_type=EventType.VALIDATION_RESULT,
                severity=Severity.INFO,
                timestamp=timestamp,
                line_no=line_no,
                raw_line=line,
            )
        return None

    def _extract_kv_payload(self, line: str, exclude_keys: list[str] = None) -> dict:
        """
        从日志行提取键值对。

        Args:
            line: 日志行
            exclude_keys: 要排除的键列表

        Returns:
            键值对字典
        """
        if exclude_keys is None:
            exclude_keys = []

        payload = {}
        # 匹配 key=value 模式 (值可以是数字或字符串)
        kv_pattern = re.compile(r"(\w+)=(\S+)")
        for match in kv_pattern.finditer(line):
            key = match.group(1)
            value = match.group(2)
            if key not in exclude_keys:
                # 尝试转换为数值
                try:
                    if "." in value:
                        payload[key] = float(value)
                    else:
                        payload[key] = int(value)
                except ValueError:
                    payload[key] = value

        return payload