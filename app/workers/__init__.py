"""Workers 模块。

后台工作者进程，负责异步处理任务。
"""

from app.workers.diagnosis_worker import DiagnosisWorker

__all__ = ["DiagnosisWorker"]
