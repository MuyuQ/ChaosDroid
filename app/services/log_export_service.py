"""日志导出服务。

用于导出设备日志和 Android 系统日志目录，供 TraceLens 诊断系统使用。
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.executors.real_executor import RealDeviceExecutor
from app.executors.mock_executor import MockDeviceExecutor
from app.models.scenario import ScenarioRun

logger = logging.getLogger(__name__)


class LogExportService:
    """日志导出服务。

    负责从设备导出完整日志快照，包括:
    - logcat 日志
    - 设备属性快照
    - Android 系统日志目录（需要 root 权限）
      - /data/log/       Android 系统日志分块文件
      - /tombstones/     应用崩溃转储文件
      - /data/anr/       ANR trace 文件
    """

    BASE_DIR = Path("artifacts/diagnosis")

    # Android 系统日志目录列表
    ANDROID_LOG_DIRS = [
        "/data/log/",       # Android 系统日志（b0000 等分块日志）
        "/tombstones/",     # 应用崩溃转储文件
        "/data/anr/",       # ANR (应用无响应) trace 文件
    ]

    def __init__(self, session: AsyncSession):
        """初始化日志导出服务。

        Args:
            session: 异步数据库会话
        """
        self.session = session

    async def export_full_snapshot(self, scenario_run_id: int) -> Optional[Path]:
        """导出完整设备快照。

        Args:
            scenario_run_id: 场景执行记录 ID

        Returns:
            Path: 导出目录路径，如果失败则返回 None
        """
        try:
            # 获取执行记录
            run = await self._get_scenario_run(scenario_run_id)
            if not run:
                logger.error(f"未找到场景执行记录：scenario_run_id={scenario_run_id}")
                return None

            device_serial = run.device_serial
            if not device_serial:
                logger.error(f"执行记录没有设备序列号：scenario_run_id={scenario_run_id}")
                return None

            # 创建导出目录
            export_dir = self.BASE_DIR / str(scenario_run_id)
            export_dir.mkdir(parents=True, exist_ok=True)

            # 获取设备执行器
            executor = RealDeviceExecutor(device_serial)

            # 检查设备是否在线
            if not await executor.is_online():
                logger.warning(f"设备离线，使用已收集的 artifacts: device_serial={device_serial}")
                return await self._use_existing_artifacts(scenario_run_id, export_dir)

            # ===== 1. 标准日志（必选，无需 root）=====
            await self._export_logcat(executor, export_dir / "logcat.log")
            await self._export_device_snapshot(executor, export_dir / "snapshot.json")

            # ===== 2. Android 系统日志目录（需要 root 权限）=====
            if await self._check_root_access(executor):
                android_logs_dir = export_dir / "android_logs"
                android_logs_dir.mkdir(exist_ok=True)

                for log_dir in self.ANDROID_LOG_DIRS:
                    await self._pull_android_log_dir(executor, log_dir, android_logs_dir)
            else:
                logger.warning(f"设备无 root 权限，跳过 Android 系统日志目录导出：device_serial={device_serial}")

            logger.info(f"成功导出设备日志：scenario_run_id={scenario_run_id}, path={export_dir}")
            return export_dir

        except Exception as e:
            logger.exception(f"导出设备日志失败：scenario_run_id={scenario_run_id}, error={e}")
            # 降级处理：尝试使用已收集的 artifacts
            export_dir = self.BASE_DIR / str(scenario_run_id)
            export_dir.mkdir(parents=True, exist_ok=True)
            return await self._use_existing_artifacts(scenario_run_id, export_dir)

    async def _use_existing_artifacts(
        self,
        scenario_run_id: int,
        export_dir: Path,
    ) -> Optional[Path]:
        """使用已收集的 artifacts（降级处理）。

        当设备离线或无法访问时，使用 ObservationCollector 已收集的日志快照。

        Args:
            scenario_run_id: 场景执行记录 ID
            export_dir: 导出目录

        Returns:
            Path: 导出目录路径
        """
        logger.info(f"使用已收集的 artifacts: scenario_run_id={scenario_run_id}")

        # 从数据库获取关联的 artifacts
        from app.models.artifact import Artifact

        from sqlalchemy import select

        stmt = select(Artifact).where(
            Artifact.run_id == scenario_run_id
        )
        result = await self.session.execute(stmt)
        artifacts = list(result.scalars().all())

        if not artifacts:
            logger.warning(f"未找到已收集的 artifacts: scenario_run_id={scenario_run_id}")
            return export_dir

        # 复制 artifact 文件到导出目录
        for artifact in artifacts:
            if artifact.file_path and Path(artifact.file_path).exists():
                src_path = Path(artifact.file_path)
                dst_path = export_dir / src_path.name

                try:
                    # 如果目标已存在，跳过
                    if dst_path.exists():
                        continue

                    # 复制文件
                    import shutil
                    shutil.copy2(src_path, dst_path)
                    logger.debug(f"已复制 artifact: {src_path} → {dst_path}")
                except Exception as e:
                    logger.warning(f"复制 artifact 失败：{src_path}, error={e}")

        return export_dir

    async def _pull_android_log_dir(
        self,
        executor: RealDeviceExecutor,
        device_dir: str,
        local_dir: Path,
    ) -> None:
        """从设备拉取 Android 系统日志目录。

        Args:
            executor: 设备执行器
            device_dir: 设备上的日志目录
            local_dir: 本地目标目录
        """
        dir_name = Path(device_dir).name  # e.g., "log", "tombstones", "anr"
        target_subdir = local_dir / dir_name

        try:
            # 检查目录是否存在
            check_cmd = f"test -d {device_dir} && echo 'exists' || echo 'not_exists'"
            result = await executor.execute_shell(check_cmd)

            if result.success and "exists" in result.stdout:
                target_subdir.mkdir(exist_ok=True)

                # 使用 adb pull 拉取整个目录
                success = await executor.pull_directory(
                    device_path=device_dir,
                    local_path=str(target_subdir),
                )

                if success:
                    logger.info(f"成功拉取日志目录：{device_dir} → {target_subdir}")
                else:
                    logger.warning(f"拉取日志目录失败：{device_dir}")
            else:
                logger.warning(f"日志目录不存在：{device_dir}")

        except Exception as e:
            logger.warning(f"拉取日志目录失败：{device_dir}, error={e}")

    async def _check_root_access(self, executor: RealDeviceExecutor) -> bool:
        """检查设备是否有 root 权限。

        Args:
            executor: 设备执行器

        Returns:
            bool: 是否有 root 权限
        """
        try:
            result = await executor.execute_shell("su -c 'echo rooted' 2>/dev/null")
            return result.success and "rooted" in result.stdout
        except Exception as e:
            logger.debug(f"检查 root 权限失败：error={e}")
            return False

    async def _export_logcat(
        self,
        executor: RealDeviceExecutor,
        output_path: Path,
    ) -> None:
        """导出 logcat 日志。

        Args:
            executor: 设备执行器
            output_path: 输出文件路径
        """
        try:
            logcat = await executor.get_logcat(lines=10000)
            output_path.write_text(logcat, encoding="utf-8")
            logger.debug(f"已导出 logcat 日志：{output_path}")
        except Exception as e:
            logger.warning(f"导出 logcat 失败：error={e}")

    async def _export_device_snapshot(
        self,
        executor: RealDeviceExecutor,
        output_path: Path,
    ) -> None:
        """导出设备状态快照。

        Args:
            executor: 设备执行器
            output_path: 输出文件路径
        """
        import json

        try:
            properties = await executor.get_properties()
            battery_info = await executor.get_battery_info()
            storage_info = await executor.get_storage_info()

            snapshot = {
                "timestamp": datetime.utcnow().isoformat(),
                "properties": properties,
                "battery": {
                    "level": battery_info.level,
                    "status": battery_info.status,
                    "temperature": battery_info.temperature,
                    "health": battery_info.health,
                },
                "storage": {
                    "total": storage_info.total,
                    "available": storage_info.available,
                    "used": storage_info.used,
                    "path": storage_info.path,
                },
            }

            output_path.write_text(
                json.dumps(snapshot, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            logger.debug(f"已导出设备快照：{output_path}")

        except Exception as e:
            logger.warning(f"导出设备快照失败：error={e}")

    async def _get_scenario_run(self, scenario_run_id: int) -> Optional[ScenarioRun]:
        """获取场景执行记录。

        Args:
            scenario_run_id: 场景执行记录 ID

        Returns:
            ScenarioRun: 场景执行记录或 None
        """
        from sqlalchemy import select

        stmt = select(ScenarioRun).where(ScenarioRun.id == scenario_run_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
