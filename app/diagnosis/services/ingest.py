"""证据导入服务。"""

import hashlib
import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.diagnosis.config import settings, config
from app.diagnosis.enums import SourceType, RunStatus
from app.diagnosis.exceptions import ValidationError, NotFoundError
from app.diagnosis.models import DiagnosticRun, RawArtifact, get_session


class IngestService:
    """证据导入服务。"""

    def __init__(self, session: Optional[Session] = None):
        """初始化服务。"""
        self.session = session or get_session()
        self.artifacts_base = Path(settings.artifacts_base_path)

    def ingest_path(
        self,
        path: str,
        metadata: Optional[dict] = None,
    ) -> str:
        """
        导入日志。

        Args:
            path: 日志路径（目录或单文件）
            metadata: 额外元数据（device_serial, test_type等）

        Returns:
            run_id: 任务ID
        """
        source_path = Path(path)

        # 检查路径是否存在
        if not source_path.exists():
            raise ValidationError(f"路径不存在: {path}", {"path": path})

        # 如果是目录，尝试读取 metadata.json
        auto_metadata = {}
        if source_path.is_dir():
            auto_metadata = self._load_metadata_from_dir(source_path)

        # 合并元数据（传入的 metadata 优先）
        final_metadata = {**auto_metadata, **(metadata or {})}

        # 生成run_id
        run_id = self._generate_run_id()

        # 创建任务记录
        run = DiagnosticRun(
            run_id=run_id,
            device_serial=final_metadata.get("device_serial"),
            test_type=final_metadata.get("test_type"),
            build_fingerprint=final_metadata.get("build_fingerprint"),
            import_path=str(source_path),
            status=RunStatus.IMPORTED,
            started_at=datetime.utcnow(),
        )
        self.session.add(run)

        # 创建存储目录
        target_dir = self.artifacts_base / run_id
        target_dir.mkdir(parents=True, exist_ok=True)

        # 导入文件
        if source_path.is_file():
            self._import_file(source_path, target_dir, run_id)
        elif source_path.is_dir():
            self._import_directory(source_path, target_dir, run_id)

        self.session.commit()
        return run_id

    def _generate_run_id(self) -> str:
        """生成唯一任务ID。"""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        unique_id = uuid.uuid4().hex[:8]
        return f"run_{timestamp}_{unique_id}"

    def _load_metadata_from_dir(self, source_dir: Path) -> dict:
        """从目录中读取 metadata.json 文件。"""
        metadata_file = source_dir / "metadata.json"
        if metadata_file.exists():
            try:
                with open(metadata_file, encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {}

    def _import_file(self, source_file: Path, target_dir: Path, run_id: str) -> None:
        """导入单个文件。"""
        source_type = self._identify_source_type(source_file.name)

        # 复制文件
        target_file = target_dir / source_file.name
        shutil.copy2(source_file, target_file)

        # 计算SHA256
        sha256 = self._compute_sha256(target_file)

        # 创建记录
        artifact = RawArtifact(
            run_id=run_id,
            source_type=source_type,
            file_name=source_file.name,
            file_path=str(target_file),
            sha256=sha256,
            size=source_file.stat().st_size,
        )
        self.session.add(artifact)

    def _import_directory(self, source_dir: Path, target_dir: Path, run_id: str) -> None:
        """导入目录。"""
        for file_path in source_dir.iterdir():
            if file_path.is_file():
                self._import_file(file_path, target_dir, run_id)

    def _identify_source_type(self, file_name: str) -> SourceType:
        """根据文件名识别来源类型。"""
        patterns = config.file_type_patterns

        for source_type, patterns_list in patterns.items():
            for pattern in patterns_list:
                if file_name.lower() == pattern.lower() or file_name.lower().startswith(pattern.lower().split(".")[0]):
                    return SourceType(source_type)

        # 默认返回设备运行日志
        return SourceType.DEVICE_RUNTIME_LOG

    def _compute_sha256(self, file_path: Path) -> str:
        """计算文件SHA256。"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()

    def get_run(self, run_id: str) -> DiagnosticRun:
        """获取任务信息。

        Args:
            run_id: 任务ID

        Returns:
            任务记录

        Raises:
            NotFoundError: 任务不存在
        """
        run = self.session.query(DiagnosticRun).filter(DiagnosticRun.run_id == run_id).first()
        if not run:
            raise NotFoundError(f"任务不存在: {run_id}", {"run_id": run_id})
        return run

    def get_artifacts(self, run_id: str) -> list[RawArtifact]:
        """获取任务的证据文件列表。"""
        return self.session.query(RawArtifact).filter(RawArtifact.run_id == run_id).all()

    def list_runs(self, limit: int = 100, offset: int = 0) -> list[DiagnosticRun]:
        """获取任务列表。"""
        return (
            self.session.query(DiagnosticRun)
            .order_by(DiagnosticRun.started_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )