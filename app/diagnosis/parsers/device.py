"""设备验证日志解析器。

解析 logcat.txt、boot_check.txt、monkey.txt、validation_summary.json 等文件，
提取启动验证和 Monkey 测试相关事件。
"""

import re
from typing import Optional

from app.diagnosis.enums import SourceType, Stage, EventType, Severity
from app.diagnosis.parsers.base import BaseParser
from app.diagnosis.schemas import NormalizedEvent


class DeviceValidationParser(BaseParser):
    """设备验证日志解析器。

    解析设备运行时日志，包括启动验证、Monkey 测试等。
    """

    source_type = SourceType.DEVICE_RUNTIME_LOG
    default_stage = Stage.POST_REBOOT
    default_event_type = EventType.VALIDATION_RESULT
    default_severity = Severity.INFO

    # 时间戳格式: [2026-03-28 15:12:44.310]
    TIMESTAMP_PATTERN = re.compile(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\]')

    # 匹配规则定义: (pattern, normalized_code, stage, severity, event_type, package_extractor)
    PATTERNS = [
        # 启动验证相关
        (
            r'sys\.boot_completed not set within',
            'BOOT_NOT_COMPLETED',
            Stage.POST_REBOOT,
            Severity.ERROR,
            EventType.VALIDATION_RESULT,
            None
        ),
        (
            r'launcher not ready',
            'LAUNCHER_NOT_READY',
            Stage.POST_REBOOT,
            Severity.ERROR,
            EventType.VALIDATION_RESULT,
            None
        ),
        (
            r'boot complete confirmed',
            'BOOT_COMPLETE_OK',
            Stage.POST_REBOOT,
            Severity.INFO,
            EventType.VALIDATION_RESULT,
            None
        ),
        # Monkey 测试相关
        (
            r'CRASH:\s*(\S+)',
            'MONKEY_FATAL_EVENT',
            Stage.POST_VALIDATE,
            Severity.CRITICAL,
            EventType.ERROR_SIGNAL,
            1  # 提取包名的捕获组索引
        ),
        (
            r'ANR in\s+(\S+)',
            'MONKEY_FATAL_EVENT',
            Stage.POST_VALIDATE,
            Severity.CRITICAL,
            EventType.ERROR_SIGNAL,
            1  # 提取包名的捕获组索引
        ),
        # R008: ADB 传输错误和设备离线
        (
            r'ADB_TRANSPORT_ERROR|adb.*transport.*error',
            'ADB_TRANSPORT_ERROR',
            Stage.APPLY_UPDATE,
            Severity.ERROR,
            EventType.ERROR_SIGNAL,
            None
        ),
        (
            r'device offline|DEVICE_OFFLINE',
            'DEVICE_OFFLINE_DURING_UPDATE',
            Stage.APPLY_UPDATE,
            Severity.ERROR,
            EventType.ERROR_SIGNAL,
            None
        ),
        (
            r'connection refused.*adb|adb.*connection refused',
            'ADB_TRANSPORT_ERROR',
            Stage.APPLY_UPDATE,
            Severity.ERROR,
            EventType.ERROR_SIGNAL,
            None
        ),
        (
            r'device disconnected|DEVICE_DISCONNECTED',
            'DEVICE_OFFLINE_DURING_UPDATE',
            Stage.APPLY_UPDATE,
            Severity.ERROR,
            EventType.ERROR_SIGNAL,
            None
        ),
    ]

    def parse(self, content: str, run_id: str) -> list[NormalizedEvent]:
        """解析日志内容，返回标准化事件列表。

        Args:
            content: 日志文件内容
            run_id: 任务ID

        Returns:
            标准化事件列表
        """
        events = []
        lines = content.splitlines()

        for line_no, line in enumerate(lines, start=1):
            line = line.strip()
            if not line:
                continue

            # 尝试提取时间戳
            timestamp = self._extract_timestamp(line)

            # 遍历所有匹配规则
            for pattern_data in self.PATTERNS:
                pattern, normalized_code, stage, severity, event_type, pkg_group = pattern_data

                match = re.search(pattern, line)
                if match:
                    kv_payload = None

                    # 如果有包名提取器，提取包名
                    if pkg_group is not None and pkg_group <= len(match.groups()):
                        package_name = match.group(pkg_group)
                        if package_name:
                            kv_payload = {'package': package_name}

                    event = self.create_event(
                        run_id=run_id,
                        normalized_code=normalized_code,
                        message=line,
                        stage=stage,
                        event_type=event_type,
                        severity=severity,
                        timestamp=timestamp,
                        line_no=line_no,
                        raw_line=line,
                        kv_payload=kv_payload,
                    )
                    events.append(event)
                    break  # 每行只匹配一个规则

        return events

    def _extract_timestamp(self, line: str) -> Optional[str]:
        """从行中提取时间戳。

        Args:
            line: 日志行

        Returns:
            时间戳字符串或None
        """
        match = self.TIMESTAMP_PATTERN.search(line)
        if match:
            return match.group(1)
        return None