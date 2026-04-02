"""
设备模型单元测试。

测试设备池等设备相关模型的创建和约束。
"""

import pytest
from datetime import datetime, timezone
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app.models import (
    Base,
    Device,
    DeviceLease,
    DevicePool,
    IncidentEvent,
    RunStatus,
    ScenarioRun,
    ScenarioTemplate,
    close_engine,
    create_tables,
    drop_tables,
    get_engine,
    get_session_context,
    init_engine,
)


# ==================== Fixtures ====================


@pytest.fixture
async def db_engine():
    """创建内存数据库引擎。"""
    init_engine(":memory:")
    await create_tables()
    yield get_engine()
    await drop_tables()
    await close_engine()


@pytest.fixture
async def db_session(db_engine):
    """提供数据库会话。"""
    async with get_session_context() as session:
        yield session


@pytest.fixture
def device_pool_data():
    """设备池测试数据。"""
    return {
        "name": "stable-pool",
        "purpose": "stable",
        "reserved_emergency_ratio": 0.2,
        "max_parallel_jobs": 10,
        "tag_selector_json": {"tags": ["stable", "test"]},
        "enabled": True,
    }


# ==================== DevicePool 模型测试 ====================


class TestDevicePoolModel:
    """测试 DevicePool 模型。"""

    async def test_device_pool_model_creation(self, db_session, device_pool_data):
        """测试创建设备池模型。"""
        pool = DevicePool(**device_pool_data)
        db_session.add(pool)
        await db_session.flush()

        assert pool.id is not None
        assert pool.name == "stable-pool"
        assert pool.purpose == "stable"
        assert pool.reserved_emergency_ratio == 0.2
        assert pool.max_parallel_jobs == 10
        assert pool.tag_selector_json == {"tags": ["stable", "test"]}
        assert pool.enabled is True

    async def test_device_pool_default_values(self, db_session):
        """测试设备池默认值。"""
        pool = DevicePool(
            name="default-pool",
            purpose="stress",
        )
        db_session.add(pool)
        await db_session.flush()

        assert pool.reserved_emergency_ratio == 0.2  # 默认预留比例
        assert pool.enabled is True  # 默认启用
        assert pool.max_parallel_jobs is None  # 默认不限制
        assert pool.tag_selector_json is None  # 默认无标签选择器

    async def test_device_pool_unique_name(self, db_session):
        """测试设备池名称唯一约束。"""
        # 创建第一个设备池
        pool1 = DevicePool(
            name="unique-pool",
            purpose="stable",
        )
        db_session.add(pool1)
        await db_session.flush()

        # 尝试创建同名设备池，应该失败
        pool2 = DevicePool(
            name="unique-pool",
            purpose="emergency",
        )
        db_session.add(pool2)

        with pytest.raises(IntegrityError):
            await db_session.flush()

        # 回滚事务以清理错误状态
        await db_session.rollback()

    async def test_device_pool_required_fields(self, db_session):
        """测试设备池必填字段。"""
        # 缺少 name 字段
        pool_no_name = DevicePool(purpose="stable")
        db_session.add(pool_no_name)

        with pytest.raises(IntegrityError):
            await db_session.flush()

        # 回滚事务以清理错误状态
        await db_session.rollback()

    async def test_device_pool_purpose_values(self, db_session):
        """测试设备池用途类型值。"""
        # 测试 stable 类型
        stable_pool = DevicePool(name="stable-test", purpose="stable")
        db_session.add(stable_pool)
        await db_session.flush()
        assert stable_pool.purpose == "stable"

        # 测试 stress 类型
        stress_pool = DevicePool(name="stress-test", purpose="stress")
        db_session.add(stress_pool)
        await db_session.flush()
        assert stress_pool.purpose == "stress"

        # 测试 emergency 类型
        emergency_pool = DevicePool(name="emergency-test", purpose="emergency")
        db_session.add(emergency_pool)
        await db_session.flush()
        assert emergency_pool.purpose == "emergency"

    async def test_device_pool_timestamps(self, db_session, device_pool_data):
        """测试设备池时间戳字段。"""
        from datetime import datetime

        pool = DevicePool(**device_pool_data)
        db_session.add(pool)
        await db_session.flush()

        assert pool.created_at is not None
        assert pool.updated_at is not None
        assert isinstance(pool.created_at, datetime)
        assert isinstance(pool.updated_at, datetime)

    async def test_device_pool_repr(self, db_session, device_pool_data):
        """测试设备池字符串表示。"""
        pool = DevicePool(**device_pool_data)
        db_session.add(pool)
        await db_session.flush()

        repr_str = repr(pool)
        assert "DevicePool" in repr_str
        assert str(pool.id) in repr_str
        assert pool.name in repr_str
        assert pool.purpose in repr_str

    async def test_device_pool_tag_selector_json(self, db_session):
        """测试设备池标签选择器JSON字段。"""
        tag_selector = {
            "tags": ["android", "test"],
            "min_android_version": "12",
            "device_types": ["phone", "tablet"],
        }
        pool = DevicePool(
            name="tagged-pool",
            purpose="stable",
            tag_selector_json=tag_selector,
        )
        db_session.add(pool)
        await db_session.flush()

        assert pool.tag_selector_json is not None
        assert pool.tag_selector_json["tags"] == ["android", "test"]
        assert pool.tag_selector_json["min_android_version"] == "12"
        assert "tablet" in pool.tag_selector_json["device_types"]

    async def test_device_pool_table_structure(self):
        """测试设备池表结构。"""
        # 检查表结构
        inspector = inspect(DevicePool)
        columns = {col.name: col for col in inspector.columns}

        assert "id" in columns
        assert "name" in columns
        assert "purpose" in columns
        assert "reserved_emergency_ratio" in columns
        assert "max_parallel_jobs" in columns
        assert "tag_selector_json" in columns
        assert "enabled" in columns
        assert "created_at" in columns
        assert "updated_at" in columns

        # 检查主键
        pk_columns = [col.name for col in inspector.primary_key]
        assert "id" in pk_columns

        # 检查唯一约束
        name_column = columns["name"]
        assert name_column.unique is True

        # 检查非空约束
        assert columns["name"].nullable is False
        assert columns["purpose"].nullable is False
        assert columns["reserved_emergency_ratio"].nullable is False
        assert columns["enabled"].nullable is False


# ==================== IncidentEvent 模型测试 ====================


class TestIncidentEvent:
    """测试 IncidentEvent 模型。"""

    async def test_incident_event_model_creation(self, db_session):
        """测试创建事件记录。"""
        event = IncidentEvent(
            event_type="device_offline",
            severity="warning",
            payload_json={"device_serial": "test_device_001", "reason": "connection_lost"},
        )
        db_session.add(event)
        await db_session.flush()

        assert event.id is not None
        assert event.event_type == "device_offline"
        assert event.severity == "warning"
        assert event.payload_json["device_serial"] == "test_device_001"

    async def test_incident_event_default_values(self, db_session):
        """测试事件记录默认值。"""
        event = IncidentEvent(event_type="lease_created")
        db_session.add(event)
        await db_session.flush()

        assert event.severity == "info"  # 默认严重程度
        assert event.created_at is not None  # 自动设置创建时间
        assert event.device_id is None  # 可选字段默认为空
        assert event.scenario_run_id is None  # 可选字段默认为空
        assert event.payload_json is None  # 可选字段默认为空

    async def test_incident_event_with_foreign_keys(self, db_session):
        """测试事件记录关联外键。"""
        event = IncidentEvent(
            device_id=1,
            scenario_run_id=1,
            event_type="device_error",
            severity="error",
        )
        db_session.add(event)
        await db_session.flush()

        assert event.device_id == 1
        assert event.scenario_run_id == 1

    async def test_incident_event_repr(self, db_session):
        """测试事件记录的字符串表示。"""
        event = IncidentEvent(
            event_type="test_event",
            severity="critical",
        )
        db_session.add(event)
        await db_session.flush()

        repr_str = repr(event)
        assert "IncidentEvent" in repr_str
        assert event.event_type in repr_str
        assert event.severity in repr_str

    async def test_incident_event_created_at_auto_set(self, db_session):
        """测试事件记录创建时间自动设置。"""
        event = IncidentEvent(event_type="auto_time_test")
        db_session.add(event)
        await db_session.flush()

        # created_at 应自动设置
        assert event.created_at is not None

    async def test_incident_event_all_severities(self, db_session):
        """测试所有严重程度等级。"""
        severities = ["info", "warning", "error", "critical"]

        for severity in severities:
            event = IncidentEvent(
                event_type=f"test_{severity}",
                severity=severity,
            )
            db_session.add(event)

        await db_session.flush()

        # 验证所有事件都已创建
        for severity in severities:
            assert await db_session.get(IncidentEvent, 1) is not None


# ==================== DeviceLease 模型测试 ====================


class TestDeviceLeaseModel:
    """测试 DeviceLease 模型。"""

    @pytest.fixture
    async def device(self, db_session):
        """创建设备实例。"""
        device = Device(
            serial="test_device_001",
            model="Test Model",
            status="online",
        )
        db_session.add(device)
        await db_session.flush()
        return device

    @pytest.fixture
    async def scenario_template(self, db_session):
        """创建场景模板实例。"""
        template = ScenarioTemplate(
            name="测试场景",
            description="测试场景描述",
        )
        db_session.add(template)
        await db_session.flush()
        return template

    @pytest.fixture
    async def scenario_run(self, db_session, scenario_template):
        """创建场景执行记录实例。"""
        run = ScenarioRun(
            scenario_template_id=scenario_template.id,
            device_serial="test_device_001",
            status=RunStatus.QUEUED.value,
        )
        db_session.add(run)
        await db_session.flush()
        return run

    async def test_device_lease_model_creation(self, db_session, device):
        """测试创建设备租约。"""
        lease = DeviceLease(
            device_id=device.id,
        )
        db_session.add(lease)
        await db_session.flush()

        assert lease.id is not None
        assert lease.device_id == device.id
        assert lease.lease_status == "active"
        assert lease.leased_at is not None
        assert isinstance(lease.leased_at, datetime)

    async def test_device_lease_default_values(self, db_session, device):
        """测试设备租约默认值。"""
        lease = DeviceLease(
            device_id=device.id,
        )
        db_session.add(lease)
        await db_session.flush()

        assert lease.lease_status == "active"  # 默认状态为 active
        assert lease.preemptible is False  # 默认不可抢占
        assert lease.scenario_run_id is None  # 默认无关联执行记录
        assert lease.expires_at is None  # 默认无过期时间
        assert lease.released_at is None  # 默认无释放时间

    async def test_device_lease_with_scenario_run(self, db_session, device, scenario_run):
        """测试设备租约关联场景执行记录。"""
        lease = DeviceLease(
            device_id=device.id,
            scenario_run_id=scenario_run.id,
        )
        db_session.add(lease)
        await db_session.flush()

        assert lease.scenario_run_id == scenario_run.id

    async def test_device_lease_with_expires_at(self, db_session, device):
        """测试设备租约设置过期时间。"""
        expires_at = datetime.now(timezone.utc)
        lease = DeviceLease(
            device_id=device.id,
            expires_at=expires_at,
        )
        db_session.add(lease)
        await db_session.flush()

        assert lease.expires_at is not None
        assert isinstance(lease.expires_at, datetime)

    async def test_device_lease_preemptible_flag(self, db_session, device):
        """测试设备租约可抢占标志。"""
        lease = DeviceLease(
            device_id=device.id,
            preemptible=True,
        )
        db_session.add(lease)
        await db_session.flush()

        assert lease.preemptible is True

    async def test_device_lease_status_values(self, db_session, device):
        """测试设备租约状态值。"""
        for status in ["active", "released", "preempted", "expired"]:
            lease = DeviceLease(
                device_id=device.id,
                lease_status=status,
            )
            db_session.add(lease)
            await db_session.flush()

            assert lease.lease_status == status

    async def test_device_lease_timestamps(self, db_session, device):
        """测试设备租约时间戳字段。"""
        lease = DeviceLease(
            device_id=device.id,
        )
        db_session.add(lease)
        await db_session.flush()

        assert lease.created_at is not None
        assert lease.updated_at is not None
        assert isinstance(lease.created_at, datetime)
        assert isinstance(lease.updated_at, datetime)

    async def test_device_lease_repr(self, db_session, device):
        """测试设备租约字符串表示。"""
        lease = DeviceLease(
            device_id=device.id,
        )
        db_session.add(lease)
        await db_session.flush()

        repr_str = repr(lease)
        assert "DeviceLease" in repr_str
        assert str(lease.id) in repr_str
        assert str(lease.device_id) in repr_str
        assert lease.lease_status in repr_str
