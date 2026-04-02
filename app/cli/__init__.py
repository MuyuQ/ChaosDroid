"""
CLI 模块。

提供 Typer 命令行工具的各个命令模块。
"""
from app.cli.scenario import scenario_app
from app.cli.run import run_app
from app.cli.device import device_app
from app.cli.report import report_app
from app.cli.pool import pool_app
from app.cli.worker import worker_app
from app.cli.serve import serve_cmd
from app.cli.init import init_cmd

__all__ = [
    "scenario_app",
    "run_app",
    "device_app",
    "report_app",
    "pool_app",
    "worker_app",
    "serve_cmd",
    "init_cmd",
]