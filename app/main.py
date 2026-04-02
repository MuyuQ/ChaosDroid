"""
ChaosDroid CLI entry point.
"""
import typer
from rich.console import Console

from app.cli.scenario import scenario_app
from app.cli.run import run_app
from app.cli.device import device_app
from app.cli.report import report_app
from app.cli.pool import pool_app
from app.cli.worker import worker_app
from app.cli.serve import serve_cmd
from app.cli.init import init_cmd

app = typer.Typer(
    name="chaosdroid",
    help="Android fault injection testing and recovery verification platform",
    add_completion=False,
)
console = Console()

# Register subcommands
app.add_typer(scenario_app, name="scenario", help="Scenario template management")
app.add_typer(run_app, name="run", help="Scenario execution management")
app.add_typer(device_app, name="device", help="Device management")
app.add_typer(report_app, name="report", help="Report management")
app.add_typer(pool_app, name="pool", help="Device pool management")
app.add_typer(worker_app, name="worker", help="Background worker management")

# Register direct commands
app.command(name="serve")(serve_cmd)
app.command(name="init")(init_cmd)


if __name__ == "__main__":
    app()