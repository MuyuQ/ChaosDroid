"""解析服务。"""

import logging
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.diagnosis.enums import SourceType
from app.diagnosis.exceptions import ParseError, NotFoundError
from app.diagnosis.models import DiagnosticRun, RawArtifact, NormalizedEventDB, get_session
from app.diagnosis.normalizer import EventNormalizer
from app.diagnosis.parsers import (
    RecoveryParser,
    UpdateEngineParser,
    DeviceValidationParser,
    ArtifactSummaryParser,
)
from app.diagnosis.schemas import NormalizedEvent


class ParseService:
    """解析服务。"""

    # 解析器映射
    PARSER_MAPPING = {
        SourceType.RECOVERY_LOG: RecoveryParser,
        SourceType.LAST_INSTALL: RecoveryParser,  # last_install 由 RecoveryParser 处理
        SourceType.UPDATE_ENGINE_LOG: UpdateEngineParser,
        SourceType.DEVICE_RUNTIME_LOG: DeviceValidationParser,
        SourceType.ARTIFACT_SUMMARY: ArtifactSummaryParser,
    }

    def __init__(self, session: Optional[Session] = None):
        """初始化服务。"""
        self.session = session or get_session()
        self.normalizer = EventNormalizer()
        self._parsers = {}

    def get_parser(self, source_type: SourceType):
        """获取解析器实例。"""
        if source_type not in self._parsers:
            parser_class = self.PARSER_MAPPING.get(source_type)
            if parser_class:
                self._parsers[source_type] = parser_class()
        return self._parsers.get(source_type)

    def parse_run(self, run_id: str) -> list[NormalizedEvent]:
        """
        解析指定任务的所有证据文件。

        Args:
            run_id: 任务ID

        Returns:
            标准化事件列表

        Raises:
            NotFoundError: 任务不存在
            ParseError: 解析失败
        """
        # 获取任务
        run = self.session.query(DiagnosticRun).filter(DiagnosticRun.run_id == run_id).first()
        if not run:
            raise NotFoundError(f"任务不存在: {run_id}", {"run_id": run_id})

        # 获取证据文件
        artifacts = self.session.query(RawArtifact).filter(RawArtifact.run_id == run_id).all()

        all_events: list[NormalizedEvent] = []

        for artifact in artifacts:
            events = self._parse_artifact(artifact)
            all_events.extend(events)

        # 标准化事件
        all_events = self.normalizer.normalize(all_events)

        # 保存到数据库
        self._save_events(all_events)

        # 更新任务状态
        from app.diagnosis.enums import RunStatus
        run.status = RunStatus.PARSED
        self.session.commit()

        return all_events

    def _parse_artifact(self, artifact: RawArtifact) -> list[NormalizedEvent]:
        """解析单个证据文件。

        Raises:
            ParseError: 解析失败时抛出
        """
        parser = self.get_parser(artifact.source_type)
        if not parser:
            return []

        file_path = Path(artifact.file_path)
        if not file_path.exists():
            return []

        try:
            events = parser.parse_file(str(file_path), artifact.run_id)
            return events
        except Exception as e:
            # 记录警告但继续处理其他文件
            logger.warning(f"解析文件失败 {artifact.file_name}: {e}")
            # 对于严重解析错误，可选择抛出 ParseError
            # 这里采用宽松策略，允许部分解析失败
            return []

    def _save_events(self, events: list[NormalizedEvent]) -> None:
        """保存事件到数据库。"""
        for event in events:
            db_event = NormalizedEventDB(
                run_id=event.run_id,
                source_type=event.source_type,
                timestamp=event.timestamp,
                line_no=event.line_no,
                raw_line=event.raw_line,
                stage=event.stage,
                event_type=event.event_type,
                severity=event.severity,
                normalized_code=event.normalized_code,
                message=event.message,
                kv_payload=event.kv_payload,
            )
            self.session.add(db_event)

    def get_events(self, run_id: str) -> list[NormalizedEvent]:
        """获取任务的事件列表。"""
        db_events = self.session.query(NormalizedEventDB).filter(NormalizedEventDB.run_id == run_id).all()

        events = []
        for db_event in db_events:
            events.append(NormalizedEvent(
                id=db_event.id,
                run_id=db_event.run_id,
                source_type=db_event.source_type,
                timestamp=db_event.timestamp,
                line_no=db_event.line_no,
                raw_line=db_event.raw_line,
                stage=db_event.stage,
                event_type=db_event.event_type,
                severity=db_event.severity,
                normalized_code=db_event.normalized_code,
                message=db_event.message,
                kv_payload=db_event.kv_payload,
            ))
        return events