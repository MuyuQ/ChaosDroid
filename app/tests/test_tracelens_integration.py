"""ChaosDroid-TraceLens 集成测试。"""

import asyncio
import pytest
from sqlalchemy import select

from app.models.database import init_engine, create_tables, get_session_context
from app.models.scenario import ScenarioRun, ScenarioTemplate
from app.models.event_queue import EventQueue
from app.services.event_dispatcher import EventDispatcher
from app.diagnosis.services.trigger import DiagnosisTrigger


@pytest.fixture
async def db_session():
    """初始化测试数据库."""
    init_engine(":memory:")
    await create_tables()
    async with get_session_context() as session:
        yield session


@pytest.mark.asyncio
async def test_event_dispatcher_publish(db_session):
    """测试事件发布器。"""
    dispatcher = EventDispatcher(db_session)

    # 发布事件
    event = await dispatcher.publish_run_completed(scenario_run_id=1)

    assert event.scenario_run_id == 1
    assert event.event_type == "run_completed"
    assert event.status == "pending"


@pytest.mark.asyncio
async def test_event_queue_model(db_session):
    """测试 EventQueue 模型。"""
    # 创建测试事件
    event = EventQueue(
        scenario_run_id=1,
        event_type="run_completed",
        payload_json={"test": "data"},
        status="pending",
        priority=10,
    )
    db_session.add(event)
    await db_session.commit()

    # 查询验证
    result = await db_session.execute(
        select(EventQueue).where(EventQueue.id == event.id)
    )
    saved_event = result.scalar_one()

    assert saved_event is not None
    assert saved_event.event_type == "run_completed"
    assert saved_event.payload_json == {"test": "data"}


@pytest.mark.asyncio
async def test_diagnosis_trigger_poll(db_session):
    """测试诊断触发器轮询。"""
    # 清理之前的测试数据
    from sqlalchemy import delete
    await db_session.execute(delete(EventQueue))
    await db_session.commit()

    # 创建测试事件
    event = EventQueue(
        scenario_run_id=1,
        event_type="run_completed",
        payload_json={"scenario_run_id": 1},
        status="pending",
    )
    db_session.add(event)
    await db_session.commit()

    # 测试轮询
    trigger = DiagnosisTrigger(db_session)
    pending_events = await trigger._fetch_pending_tasks(batch_size=10)

    assert len(pending_events) == 1
    assert pending_events[0].event_type == "run_completed"


@pytest.mark.asyncio
async def test_scenario_run_diagnosis_fields(db_session):
    """测试 ScenarioRun 诊断字段。"""
    # 创建场景模板
    template = ScenarioTemplate(name="Test Scenario")
    db_session.add(template)
    await db_session.commit()

    # 创建执行记录
    run = ScenarioRun(
        scenario_template_id=template.id,
        device_serial="TEST_DEVICE",
        diagnosis_run_id="diag_001",
        diagnosis_category="network_error",
        diagnosis_root_cause="WiFi 断开导致服务不可用",
        diagnosis_confidence=0.85,
    )
    db_session.add(run)
    await db_session.commit()

    # 验证字段
    result = await db_session.execute(
        select(ScenarioRun).where(ScenarioRun.id == run.id)
    )
    saved_run = result.scalar_one()

    assert saved_run.diagnosis_run_id == "diag_001"
    assert saved_run.diagnosis_category == "network_error"
    assert saved_run.diagnosis_root_cause == "WiFi 断开导致服务不可用"
    assert abs(saved_run.diagnosis_confidence - 0.85) < 0.001


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
