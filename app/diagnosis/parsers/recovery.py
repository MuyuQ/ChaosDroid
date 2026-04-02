"""Recovery日志解析器。

解析 recovery.log 文件和 last_install.txt 文件，提取标准化事件。
"""

import re
from pathlib import Path
from typing import Optional

from app.diagnosis.enums import EventType, Severity, SourceType, Stage
from app.diagnosis.parsers.base import BaseParser
from app.diagnosis.schemas import NormalizedEvent


class RecoveryParser(BaseParser):
    """Recovery日志解析器。

    解析 recovery.log 文件中的关键事件，包括：
    - 电池电量不足
    - 启动原因黑名单
    - 安装中止
    - 重试尝试
    - 命令信息
    - last_install 键值对

    同时支持解析独立的 last_install.txt 文件。
    """

    source_type = SourceType.RECOVERY_LOG
    default_stage = Stage.PRECHECK
    default_event_type = EventType.STATUS_TRANSITION
    default_severity = Severity.INFO

    def create_event(
        self,
        run_id: str,
        normalized_code: str,
        message: Optional[str] = None,
        stage: Optional[Stage] = None,
        event_type: Optional[EventType] = None,
        severity: Optional[Severity] = None,
        timestamp: Optional[str] = None,
        line_no: Optional[int] = None,
        raw_line: Optional[str] = None,
        kv_payload: Optional[dict] = None,
        source_type_override: Optional[SourceType] = None,
    ) -> NormalizedEvent:
        """创建标准化事件的辅助方法，支持覆盖 source_type。

        Args:
            run_id: 任务ID
            normalized_code: 标准化代码
            message: 消息
            stage: 阶段
            event_type: 事件类型
            severity: 严重级别
            timestamp: 时间戳字符串
            line_no: 行号
            raw_line: 原始行
            kv_payload: 键值数据
            source_type_override: 覆盖的来源类型（用于独立文件）

        Returns:
            NormalizedEvent
        """
        from datetime import datetime

        parsed_timestamp = None
        if timestamp:
            try:
                # 尝试多种时间格式
                for fmt in ["%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"]:
                    try:
                        parsed_timestamp = datetime.strptime(timestamp, fmt)
                        break
                    except ValueError:
                        continue
            except Exception:
                pass

        return NormalizedEvent(
            run_id=run_id,
            source_type=source_type_override or self.source_type,
            timestamp=parsed_timestamp,
            line_no=line_no,
            raw_line=raw_line,
            stage=stage or self.default_stage,
            event_type=event_type or self.default_event_type,
            severity=severity or self.default_severity,
            normalized_code=normalized_code,
            message=message,
            kv_payload=kv_payload,
        )

    # 模式定义：关键词 -> (normalized_code, stage, severity, event_type)
    PATTERNS = {
        r"battery capacity is not enough": (
            "RECOVERY_LOW_BATTERY",
            Stage.PRECHECK,
            Severity.ERROR,
            EventType.ENVIRONMENT_CHECK,
        ),
        r"bootreason is in the blacklist": (
            "RECOVERY_BOOTREASON_BLOCKED",
            Stage.PRECHECK,
            Severity.ERROR,
            EventType.ENVIRONMENT_CHECK,
        ),
        r"installation aborted": (
            "RECOVERY_INSTALL_ABORTED",
            Stage.APPLY_UPDATE,
            Severity.ERROR,
            EventType.ERROR_SIGNAL,
        ),
        r"retry attempt": (
            "RECOVERY_RETRY_ATTEMPT",
            Stage.APPLY_UPDATE,
            Severity.WARNING,
            EventType.STATUS_TRANSITION,
        ),
        r"Command:": (
            "RECOVERY_COMMAND",
            Stage.PRECHECK,
            Severity.INFO,
            EventType.STATUS_TRANSITION,
        ),
        r"start install package": (
            "RECOVERY_INSTALL_START",
            Stage.APPLY_UPDATE,
            Severity.INFO,
            EventType.STATUS_TRANSITION,
        ),
        r"installation skipped": (
            "RECOVERY_INSTALL_SKIPPED",
            Stage.APPLY_UPDATE,
            Severity.WARNING,
            EventType.STATUS_TRANSITION,
        ),
        r"verifying package": (
            "RECOVERY_VERIFYING_PACKAGE",
            Stage.PACKAGE_PREPARE,
            Severity.INFO,
            EventType.PROGRESS_SIGNAL,
        ),
        r"rebooting into recovery for retry": (
            "RECOVERY_REBOOT_FOR_RETRY",
            Stage.APPLY_UPDATE,
            Severity.WARNING,
            EventType.STATUS_TRANSITION,
        ),
        r"maximum size.*exceeded.*allocatable space": (
            "DP_ALLOCATABLE_SPACE_EXCEEDED",  # 统一使用规则引擎期望的代码
            Stage.PACKAGE_PREPARE,
            Severity.ERROR,
            EventType.ERROR_SIGNAL,
        ),
        # R007: 包校验失败模式
        r"package verification failed": (
            "PACKAGE_VERIFY_FAILED",
            Stage.PACKAGE_PREPARE,
            Severity.ERROR,
            EventType.ERROR_SIGNAL,
        ),
        r"signature verification failed": (
            "PACKAGE_VERIFY_FAILED",
            Stage.PACKAGE_PREPARE,
            Severity.ERROR,
            EventType.ERROR_SIGNAL,
        ),
        r"verify failed": (
            "PACKAGE_VERIFY_FAILED",
            Stage.PACKAGE_PREPARE,
            Severity.ERROR,
            EventType.ERROR_SIGNAL,
        ),
        r"failed to verify package": (
            "PACKAGE_VERIFY_FAILED",
            Stage.PACKAGE_PREPARE,
            Severity.ERROR,
            EventType.ERROR_SIGNAL,
        ),
        # R007: 元数据不匹配
        r"metadata mismatch": (
            "PACKAGE_METADATA_MISMATCH",
            Stage.PACKAGE_PREPARE,
            Severity.ERROR,
            EventType.ERROR_SIGNAL,
        ),
        r"package metadata.*mismatch": (
            "PACKAGE_METADATA_MISMATCH",
            Stage.PACKAGE_PREPARE,
            Severity.ERROR,
            EventType.ERROR_SIGNAL,
        ),
    }

    def parse_file(self, file_path: str, run_id: str) -> list[NormalizedEvent]:
        """解析文件，根据文件类型选择适当的解析方法。

        重写基类方法，支持处理独立的 last_install.txt 文件。

        Args:
            file_path: 文件路径
            run_id: 任务ID

        Returns:
            标准化事件列表
        """
        # 判断文件类型
        file_name = Path(file_path).name.lower()

        # 处理独立的 last_install.txt 文件
        if "last_install" in file_name:
            return self.parse_last_install_file(file_path, run_id)

        # 默认使用 recovery.log 解析方法
        content = Path(file_path).read_text(encoding="utf-8", errors="ignore")
        return self.parse(content, run_id)

    def parse_last_install_file(self, file_path: str, run_id: str) -> list[NormalizedEvent]:
        """解析独立的 last_install.txt 文件。

        last_install.txt 文件格式通常为键值对形式：
        ```
        package=/cache/update.zip
        success=0
        error=LOW_BATTERY
        ```

        或简化的行格式：
        ```
        <timestamp> <result> <package_path>
        ```

        Args:
            file_path: last_install.txt 文件路径
            run_id: 任务ID

        Returns:
            标准化事件列表，包含 LAST_INSTALL_SUCCESS 或 LAST_INSTALL_ERROR_* 事件
        """
        events: list[NormalizedEvent] = []

        content = Path(file_path).read_text(encoding="utf-8", errors="ignore")
        lines = content.strip().split("\n")

        # 尝试解析键值对格式
        kv_payload: dict = {}
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 处理键值对格式 (package=..., success=..., error=...)
            if "=" in line:
                key, _, value = line.partition("=")
                kv_payload[key.strip()] = value.strip()

        # 如果成功解析键值对格式
        if kv_payload:
            success = kv_payload.get("success", "0")
            error = kv_payload.get("error", "")

            if success == "0" and error:
                # 安装失败，创建错误事件
                events.append(
                    self.create_event(
                        run_id=run_id,
                        normalized_code=f"LAST_INSTALL_ERROR_{error}",
                        message=f"Installation failed with error: {error}",
                        stage=Stage.APPLY_UPDATE,
                        event_type=EventType.SUMMARY_SIGNAL,
                        severity=Severity.ERROR,
                        kv_payload=kv_payload,
                        source_type_override=SourceType.LAST_INSTALL,
                    )
                )
            elif success == "1":
                # 安装成功
                events.append(
                    self.create_event(
                        run_id=run_id,
                        normalized_code="LAST_INSTALL_SUCCESS",
                        message="Installation completed successfully",
                        stage=Stage.APPLY_UPDATE,
                        event_type=EventType.SUMMARY_SIGNAL,
                        severity=Severity.INFO,
                        kv_payload=kv_payload,
                        source_type_override=SourceType.LAST_INSTALL,
                    )
                )
        else:
            # 尝试解析简化行格式 (<timestamp> <result> <package_path>)
            # 例如: "2026-03-28 12:00:00 0 /cache/update.zip" 表示失败
            # 例如: "2026-03-28 12:00:00 1 /cache/update.zip" 表示成功
            for line_no, line in enumerate(lines, start=1):
                line = line.strip()
                if not line:
                    continue

                # 简化格式解析：时间戳可选
                parts = line.split()
                if len(parts) >= 2:
                    # 尝试识别结果值（通常是最后一个数字）
                    result = None
                    package_path = None

                    # 从后向前解析，最后一个字段通常是包路径
                    for i in range(len(parts) - 1, -1, -1):
                        if parts[i] in ("0", "1"):
                            result = parts[i]
                            # 之后的字段组合为包路径
                            package_path = " ".join(parts[i + 1:]) if i + 1 < len(parts) else ""
                            break

                    if result is not None:
                        kv_payload_simple = {
                            "success": result,
                            "package": package_path,
                        }

                        if result == "0":
                            events.append(
                                self.create_event(
                                    run_id=run_id,
                                    normalized_code="LAST_INSTALL_FAILED",
                                    message=f"Installation failed: {package_path}",
                                    stage=Stage.APPLY_UPDATE,
                                    event_type=EventType.SUMMARY_SIGNAL,
                                    severity=Severity.ERROR,
                                    line_no=line_no,
                                    raw_line=line,
                                    kv_payload=kv_payload_simple,
                                    source_type_override=SourceType.LAST_INSTALL,
                                )
                            )
                        elif result == "1":
                            events.append(
                                self.create_event(
                                    run_id=run_id,
                                    normalized_code="LAST_INSTALL_SUCCESS",
                                    message=f"Installation succeeded: {package_path}",
                                    stage=Stage.APPLY_UPDATE,
                                    event_type=EventType.SUMMARY_SIGNAL,
                                    severity=Severity.INFO,
                                    line_no=line_no,
                                    raw_line=line,
                                    kv_payload=kv_payload_simple,
                                    source_type_override=SourceType.LAST_INSTALL,
                                )
                            )

        return events

    def parse(self, content: str, run_id: str) -> list[NormalizedEvent]:
        """解析recovery日志内容，返回标准化事件列表。

        Args:
            content: 日志文件内容
            run_id: 任务ID

        Returns:
            标准化事件列表
        """
        events: list[NormalizedEvent] = []
        lines = content.split("\n")

        # 解析 last_install 部分
        last_install_events = self._parse_last_install(content, run_id)
        events.extend(last_install_events)

        # 逐行解析关键模式
        for line_no, line in enumerate(lines, start=1):
            line = line.strip()
            if not line:
                continue

            matched_event = self._match_line(line, run_id, line_no)
            if matched_event:
                events.append(matched_event)

        return events

    def _match_line(
        self, line: str, run_id: str, line_no: int
    ) -> Optional[NormalizedEvent]:
        """匹配单行日志，提取事件。

        Args:
            line: 日志行
            run_id: 任务ID
            line_no: 行号

        Returns:
            匹配到的 NormalizedEvent，未匹配则返回 None
        """
        for pattern, (code, stage, severity, event_type) in self.PATTERNS.items():
            if re.search(pattern, line, re.IGNORECASE):
                return self.create_event(
                    run_id=run_id,
                    normalized_code=code,
                    message=line,
                    stage=stage,
                    event_type=event_type,
                    severity=severity,
                    line_no=line_no,
                    raw_line=line,
                )
        return None

    def _parse_last_install(self, content: str, run_id: str) -> list[NormalizedEvent]:
        """解析 last_install 部分。

        last_install 通常嵌入在 recovery.log 末尾，格式如下：
        last_install:
          package=/cache/update.zip
          success=0
          error=LOW_BATTERY

        Args:
            content: 日志文件内容
            run_id: 任务ID

        Returns:
            标准化事件列表
        """
        events: list[NormalizedEvent] = []

        # 查找 last_install 块
        last_install_match = re.search(
            r"last_install:\s*\n((?:\s+\S+=.*\n?)+)", content, re.MULTILINE
        )
        if not last_install_match:
            return events

        kv_block = last_install_match.group(1)
        kv_payload: dict = {}

        # 解析键值对
        for line in kv_block.strip().split("\n"):
            line = line.strip()
            if "=" in line:
                key, _, value = line.partition("=")
                kv_payload[key.strip()] = value.strip()

        if not kv_payload:
            return events

        # 创建 last_install 汇总事件
        success = kv_payload.get("success", "0")
        error = kv_payload.get("error", "")

        if success == "0" and error:
            # 安装失败，创建错误事件
            events.append(
                self.create_event(
                    run_id=run_id,
                    normalized_code=f"LAST_INSTALL_ERROR_{error}",
                    message=f"Installation failed with error: {error}",
                    stage=Stage.APPLY_UPDATE,
                    event_type=EventType.SUMMARY_SIGNAL,
                    severity=Severity.ERROR,
                    kv_payload=kv_payload,
                )
            )
        elif success == "1":
            # 安装成功
            events.append(
                self.create_event(
                    run_id=run_id,
                    normalized_code="LAST_INSTALL_SUCCESS",
                    message="Installation completed successfully",
                    stage=Stage.APPLY_UPDATE,
                    event_type=EventType.SUMMARY_SIGNAL,
                    severity=Severity.INFO,
                    kv_payload=kv_payload,
                )
            )

        return events