"""解析器基础抽象类。"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from app.diagnosis.enums import SourceType, Stage, EventType, Severity
from app.diagnosis.schemas import NormalizedEvent


class BaseParser(ABC):
    """解析器抽象基类。"""

    source_type: SourceType
    default_stage: Stage = Stage.PRECHECK
    default_event_type: EventType = EventType.STATUS_TRANSITION
    default_severity: Severity = Severity.INFO

    @abstractmethod
    def parse(self, content: str, run_id: str) -> list[NormalizedEvent]:
        """
        解析日志内容，返回标准化事件列表。

        Args:
            content: 日志文件内容
            run_id: 任务ID

        Returns:
            标准化事件列表
        """
        pass

    def parse_file(self, file_path: str, run_id: str) -> list[NormalizedEvent]:
        """
        解析文件。

        Args:
            file_path: 文件路径
            run_id: 任务ID

        Returns:
            标准化事件列表
        """
        content = Path(file_path).read_text(encoding="utf-8", errors="ignore")
        return self.parse(content, run_id)

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
    ) -> NormalizedEvent:
        """
        创建标准化事件的辅助方法。

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
            source_type=self.source_type,
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