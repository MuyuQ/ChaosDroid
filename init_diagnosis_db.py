"""数据库初始化脚本。"""
import asyncio
from app.diagnosis.models.db import init_db

async def main():
    print("初始化诊断数据库...")
    await init_db()
    print("数据库初始化完成！")

if __name__ == "__main__":
    asyncio.run(main())
