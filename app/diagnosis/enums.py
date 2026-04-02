"""标准枚举定义模块。"""

from enum import Enum


class Stage(str, Enum):
    """诊断阶段枚举。"""

    PRECHECK = "precheck"
    PACKAGE_PREPARE = "package_prepare"
    APPLY_UPDATE = "apply_update"
    REBOOT_WAIT = "reboot_wait"
    POST_REBOOT = "post_reboot"
    POST_VALIDATE = "post_validate"


class SourceType(str, Enum):
    """日志来源枚举。"""

    RECOVERY_LOG = "recovery_log"
    LAST_INSTALL = "last_install"
    UPDATE_ENGINE_LOG = "update_engine_log"
    DEVICE_RUNTIME_LOG = "device_runtime_log"
    ARTIFACT_SUMMARY = "artifact_summary"


class EventType(str, Enum):
    """事件类型枚举。"""

    STATUS_TRANSITION = "status_transition"
    ERROR_SIGNAL = "error_signal"
    PROGRESS_SIGNAL = "progress_signal"
    VALIDATION_RESULT = "validation_result"
    ENVIRONMENT_CHECK = "environment_check"
    SUMMARY_SIGNAL = "summary_signal"


class Severity(str, Enum):
    """严重级别枚举。"""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class RunStatus(str, Enum):
    """任务状态枚举。"""

    PENDING = "pending"
    IMPORTED = "imported"
    PARSED = "parsed"
    DIAGNOSED = "diagnosed"
    FAILED = "failed"
    PASSED = "passed"


class ResultStatus(str, Enum):
    """诊断结果状态枚举。"""

    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    TRANSIENT_FAILURE = "transient_failure"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class Category(str, Enum):
    """故障分类枚举。"""

    SUCCESS = "success"
    DEVICE_ENV_ISSUE = "device_env_issue"
    PACKAGE_ISSUE = "package_issue"
    DYNAMIC_PARTITION_SPACE = "dynamic_partition_space"
    BOOT_FAILURE = "boot_failure"
    STABILITY_FAILURE = "stability_failure"
    RETRYABLE_INSTALL_ERROR = "retryable_install_error"
    TRANSPORT_OR_DEVICE_ENV_ISSUE = "transport_or_device_env_issue"
    UNKNOWN = "unknown"  # 规则匹配失败时的默认值