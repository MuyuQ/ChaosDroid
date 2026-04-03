"""数据库迁移脚本 - ChaosDroid-TraceLens 集成。

添加内容:
1. event_queue 表
2. scenario_runs 表的诊断相关字段
"""

import asyncio
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config.settings import get_settings


async def run_migration():
    """执行数据库迁移."""
    settings = get_settings()
    # 构建数据库 URL (使用 chaosdroid.db 统一数据库)
    db_url = f"sqlite+aiosqlite:///{settings.database_path}"

    print(f"连接到数据库：{settings.database_path}")
    engine = create_async_engine(db_url, echo=False)

    async with engine.begin() as conn:
        print("开始迁移...")

        # 1. 创建 event_queue 表
        print("创建 event_queue 表...")
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS event_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scenario_run_id INTEGER NOT NULL,
                event_type VARCHAR(50) NOT NULL,
                payload_json JSON NOT NULL,
                status VARCHAR(20) DEFAULT 'pending',
                priority INTEGER DEFAULT 0,
                retry_count INTEGER DEFAULT 0,
                error_message TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                processed_at DATETIME
            )
        """))

        # 创建索引
        print("创建 event_queue 索引...")
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_event_queue_scenario_run_id
            ON event_queue(scenario_run_id)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_event_queue_event_type
            ON event_queue(event_type)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_event_queue_status
            ON event_queue(status)
        """))
        # 组合索引，用于 Worker 轮询
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_event_queue_status_priority
            ON event_queue(status, priority DESC)
        """))

        # 2. 为 scenario_runs 添加诊断相关字段
        print("为 scenario_runs 添加诊断字段...")

        # 检查字段是否已存在，如果不存在则添加
        diagnosis_columns = [
            ("diagnosis_run_id", "VARCHAR(50)"),
            ("diagnosis_category", "VARCHAR(50)"),
            ("diagnosis_root_cause", "TEXT"),
            ("diagnosis_confidence", "FLOAT"),
            ("diagnosis_completed_at", "DATETIME"),
        ]

        for column_name, column_type in diagnosis_columns:
            try:
                await conn.execute(text(f"""
                    ALTER TABLE scenario_runs
                    ADD COLUMN {column_name} {column_type}
                """))
                print(f"  已添加列：{column_name}")
            except Exception as e:
                # 列可能已存在
                if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                    print(f"  列已存在：{column_name}")
                else:
                    raise

        print("迁移完成!")

    await engine.dispose()
    print("数据库连接已关闭")


if __name__ == "__main__":
    asyncio.run(run_migration())
