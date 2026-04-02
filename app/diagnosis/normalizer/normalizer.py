"""事件标准化器。"""

from app.diagnosis.enums import Stage, Severity
from app.diagnosis.schemas import NormalizedEvent


class EventNormalizer:
    """事件标准化器。"""

    def normalize(self, events: list[NormalizedEvent]) -> list[NormalizedEvent]:
        """
        对事件进行二次标准化。

        Args:
            events: 原始事件列表

        Returns:
            标准化后的事件列表
        """
        return [self._adjust_severity(self._adjust_stage(event)) for event in events]

    def _adjust_stage(self, event: NormalizedEvent) -> NormalizedEvent:
        """
        根据事件代码调整阶段。

        使用 model_copy 创建新对象，保持函数式风格。

        Args:
            event: 原始事件

        Returns:
            调整阶段后的事件副本（如需调整），否则返回原事件
        """
        code = event.normalized_code
        new_stage: Stage | None = None

        # 根据normalized_code确定新阶段
        if code.startswith("UE_STATUS_DOWNLOADING") or code.startswith("UE_STATUS_VERIFYING"):
            new_stage = Stage.APPLY_UPDATE
        elif code.startswith("UE_STATUS_FINALIZING"):
            new_stage = Stage.APPLY_UPDATE
        elif code.startswith("UE_STATUS_UPDATED_NEED_REBOOT"):
            new_stage = Stage.REBOOT_WAIT
        elif code == "BOOT_NOT_COMPLETED" or code == "LAUNCHER_NOT_READY":
            new_stage = Stage.POST_REBOOT
        elif code == "MONKEY_FATAL_EVENT":
            new_stage = Stage.POST_VALIDATE
        elif code in ("RECOVERY_LOW_BATTERY", "RECOVERY_BOOTREASON_BLOCKED"):
            new_stage = Stage.PRECHECK
        elif code == "RECOVERY_INSTALL_ABORTED":
            new_stage = Stage.APPLY_UPDATE
        elif code == "DP_ALLOCATABLE_SPACE_EXCEEDED":
            new_stage = Stage.PACKAGE_PREPARE

        # 使用 model_copy 创建新对象
        if new_stage is not None:
            return event.model_copy(update={"stage": new_stage})
        return event

    def _adjust_severity(self, event: NormalizedEvent) -> NormalizedEvent:
        """
        根据事件代码调整严重级别。

        使用 model_copy 创建新对象，保持函数式风格。

        Args:
            event: 原始事件

        Returns:
            调整严重级别后的事件副本（如需调整），否则返回原事件
        """
        code = event.normalized_code
        new_severity: Severity | None = None

        # 根据normalized_code确定新严重级别
        if code in ("RECOVERY_LOW_BATTERY", "RECOVERY_BOOTREASON_BLOCKED"):
            new_severity = Severity.ERROR
        elif code == "RECOVERY_INSTALL_ABORTED":
            new_severity = Severity.ERROR
        elif code == "DP_ALLOCATABLE_SPACE_EXCEEDED":
            new_severity = Severity.ERROR
        elif code in ("BOOT_NOT_COMPLETED", "LAUNCHER_NOT_READY"):
            new_severity = Severity.ERROR
        elif code == "MONKEY_FATAL_EVENT":
            new_severity = Severity.CRITICAL

        # 使用 model_copy 创建新对象
        if new_severity is not None:
            return event.model_copy(update={"severity": new_severity})
        return event