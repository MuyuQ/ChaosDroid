"""
服务层模块。

提供业务逻辑和执行服务。
"""

# 现有服务
from .report_generator import ReportGenerator, ReportData
from .execution_service import ExecutionService, get_execution_service
from .recovery_service import RecoveryService, RecoveryResult, RecoveryStep, RecoveryStepResult

# 场景模板服务
from .scenario_service import (
    ScenarioFilters,
    clone_scenario,
    create_scenario,
    delete_scenario,
    get_scenario,
    get_scenario_with_runs,
    list_scenarios,
    update_scenario,
)

# 场景执行服务
from .run_service import (
    RunFilters,
    cancel_run,
    create_run,
    create_step,
    get_run,
    get_run_statistics,
    get_run_steps,
    get_run_with_template,
    list_runs,
    record_step_result,
    update_run_status,
    update_run_summary,
)

# 配置文件服务
from .profile_service import (
    ProfileFilters,
    ProfileType,
    create_fault_profile,
    create_recovery_profile,
    create_validation_profile,
    delete_fault_profile,
    delete_recovery_profile,
    delete_validation_profile,
    get_fault_profile,
    get_profile,
    get_recovery_profile,
    get_validation_profile,
    list_fault_profiles,
    list_profiles,
    list_recovery_profiles,
    list_validation_profiles,
    update_fault_profile,
    update_recovery_profile,
    update_validation_profile,
)

# 执行产物服务
from .artifact_service import (
    create_artifact_path,
    delete_artifact,
    delete_run_artifacts,
    ensure_artifact_directory,
    get_artifact,
    get_artifact_path,
    get_artifact_statistics,
    get_artifact_with_content,
    get_artifacts_by_type,
    list_artifacts,
    save_artifact,
)

# 报告服务
from .report_service import (
    create_report,
    create_report_paths,
    delete_report,
    ensure_report_directory,
    get_report,
    get_report_by_run,
    get_report_content,
    get_report_statistics,
    get_report_summary,
    get_report_with_run,
    list_reports,
    update_report,
)

__all__ = [
    # 报告生成
    "ReportGenerator",
    "ReportData",
    # 执行服务
    "ExecutionService",
    "get_execution_service",
    # 恢复服务
    "RecoveryService",
    "RecoveryResult",
    "RecoveryStep",
    "RecoveryStepResult",
    # 场景模板服务
    "ScenarioFilters",
    "create_scenario",
    "get_scenario",
    "list_scenarios",
    "update_scenario",
    "delete_scenario",
    "clone_scenario",
    "get_scenario_with_runs",
    # 场景执行服务
    "RunFilters",
    "create_run",
    "get_run",
    "get_run_with_template",
    "list_runs",
    "get_run_steps",
    "cancel_run",
    "record_step_result",
    "create_step",
    "update_run_status",
    "update_run_summary",
    "get_run_statistics",
    # 配置文件服务
    "ProfileFilters",
    "ProfileType",
    "create_fault_profile",
    "get_fault_profile",
    "list_fault_profiles",
    "update_fault_profile",
    "delete_fault_profile",
    "create_validation_profile",
    "get_validation_profile",
    "list_validation_profiles",
    "update_validation_profile",
    "delete_validation_profile",
    "create_recovery_profile",
    "get_recovery_profile",
    "list_recovery_profiles",
    "update_recovery_profile",
    "delete_recovery_profile",
    "list_profiles",
    "get_profile",
    # 执行产物服务
    "save_artifact",
    "get_artifact",
    "list_artifacts",
    "get_artifact_path",
    "get_artifact_with_content",
    "delete_artifact",
    "delete_run_artifacts",
    "get_artifacts_by_type",
    "get_artifact_statistics",
    "ensure_artifact_directory",
    "create_artifact_path",
    # 报告服务
    "create_report",
    "get_report",
    "get_report_by_run",
    "get_report_with_run",
    "list_reports",
    "update_report",
    "delete_report",
    "get_report_content",
    "get_report_summary",
    "ensure_report_directory",
    "create_report_paths",
    "get_report_statistics",
]