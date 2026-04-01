"""Tests for scheduling module."""
import pytest
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from chaosdroid.models.base import Base
from chaosdroid.models.device import Device
from chaosdroid.scheduling.enums import DeviceStatus
from chaosdroid.scheduling.device_sync import DeviceSyncService


def test_device_status_enum():
    """Test DeviceStatus enum values."""
    from chaosdroid.scheduling.enums import DeviceStatus

    assert DeviceStatus.IDLE == "idle"
    assert DeviceStatus.RESERVED == "reserved"
    assert DeviceStatus.BUSY == "busy"
    assert DeviceStatus.OFFLINE == "offline"
    assert DeviceStatus.QUARANTINED == "quarantined"
    assert DeviceStatus.RECOVERING == "recovering"


def test_lease_status_enum():
    """Test LeaseStatus enum values."""
    from chaosdroid.scheduling.enums import LeaseStatus

    assert LeaseStatus.ACTIVE == "active"
    assert LeaseStatus.RELEASED == "released"
    assert LeaseStatus.PREEMPTED == "preempted"
    assert LeaseStatus.EXPIRED == "expired"


def test_priority_enum():
    """Test Priority enum values."""
    from chaosdroid.scheduling.enums import Priority

    assert Priority.NORMAL == "normal"
    assert Priority.HIGH == "high"
    assert Priority.EMERGENCY == "emergency"


def test_event_type_enum():
    """Test EventType enum values."""
    from chaosdroid.scheduling.enums import EventType

    assert EventType.DEVICE_OFFLINE == "device_offline"
    assert EventType.HEALTH_FAILED == "health_failed"
    assert EventType.LEASE_CREATED == "lease_created"
    assert EventType.PREEMPTION_TRIGGERED == "preemption_triggered"
    assert EventType.DEVICE_QUARANTINED == "device_quarantined"
    assert EventType.DEVICE_RECOVERED == "device_recovered"
    assert EventType.DEVICE_RECOVERY_FAILED == "device_recovery_failed"


def test_event_severity_enum():
    """Test EventSeverity enum values."""
    from chaosdroid.scheduling.enums import EventSeverity

    assert EventSeverity.INFO == "info"
    assert EventSeverity.WARNING == "warning"
    assert EventSeverity.ERROR == "error"
    assert EventSeverity.CRITICAL == "critical"


def test_run_status_scheduling_values():
    """Test RunStatus includes scheduling-related values."""
    from chaosdroid.models.base import RunStatus

    # Existing values
    assert RunStatus.QUEUED == "queued"
    assert RunStatus.PREPARING == "preparing"
    assert RunStatus.INJECTING == "injecting"
    assert RunStatus.VALIDATING == "validating"
    assert RunStatus.RECOVERING == "recovering"
    assert RunStatus.PASSED == "passed"
    assert RunStatus.FAILED == "failed"
    assert RunStatus.PARTIAL == "partial"

    # New scheduling-related values
    assert RunStatus.ALLOCATING == "allocating"
    assert RunStatus.RESERVED == "reserved"
    assert RunStatus.PREEMPTED == "preempted"


# ==================== DeviceSyncService Tests ====================

@pytest.fixture
def sync_db_engine():
    """创建同步内存数据库引擎."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(sync_db_engine):
    """提供同步数据库会话."""
    SessionLocal = sessionmaker(bind=sync_db_engine, class_=Session)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
async def async_db_engine():
    """创建异步内存数据库引擎."""
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def async_db_session(async_db_engine):
    """提供异步数据库会话."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    async_session_maker = async_sessionmaker(
        async_db_engine, class_=AsyncSession, expire_on_commit=False
    )
    session = async_session_maker()
    yield session
    await session.close()


def test_device_sync_calculate_health_score(db_session):
    """Test health score calculation.

    测试健康评分计算逻辑:
    - 在线状态: +40分
    - 电池电量 > 30%: +20分
    - 正常状态: +10分
    - 无同步失败: +10分
    """
    # 创建设备: battery_level=80, status=idle
    device = Device(
        serial="test-device-001",
        status=DeviceStatus.IDLE.value,
        battery_level=80,
        sync_failure_count=0,
    )
    db_session.add(device)
    db_session.commit()

    # 创建同步服务并计算健康评分
    sync_service = DeviceSyncService(db_session)
    score = sync_service.calculate_health_score(device)

    # 验证分数: 40(在线) + 20(电池>30) + 10(正常状态) + 10(无同步失败) = 80
    assert score >= 60
    assert score == 80


def test_device_sync_calculate_health_score_offline(db_session):
    """Test health score calculation for offline device.

    测试离线设备的健康评分。
    """
    device = Device(
        serial="test-device-002",
        status=DeviceStatus.OFFLINE.value,
        battery_level=80,
        sync_failure_count=0,
    )
    db_session.add(device)
    db_session.commit()

    sync_service = DeviceSyncService(db_session)
    score = sync_service.calculate_health_score(device)

    # 离线状态: 0(离线) + 20(电池>30) + 10(正常状态) + 10(无同步失败) = 40
    assert score == 40


def test_device_sync_calculate_health_score_low_battery(db_session):
    """Test health score calculation for low battery device.

    测试低电量设备的健康评分。
    """
    device = Device(
        serial="test-device-003",
        status=DeviceStatus.IDLE.value,
        battery_level=20,  # 低于30%
        sync_failure_count=0,
    )
    db_session.add(device)
    db_session.commit()

    sync_service = DeviceSyncService(db_session)
    score = sync_service.calculate_health_score(device)

    # 低电量: 40(在线) + 0(电池<30) + 10(正常状态) + 10(无同步失败) = 60
    assert score == 60


def test_device_sync_sync_device(db_session):
    """Test device sync updates device info.

    测试设备同步更新设备信息。
    """
    # 创建设备
    device = Device(
        serial="test-device-004",
        status=DeviceStatus.OFFLINE.value,
        battery_level=10,
        sync_failure_count=5,
    )
    db_session.add(device)
    db_session.commit()

    # 创建同步服务
    sync_service = DeviceSyncService(db_session)

    # 同步设备
    synced_device = sync_service.sync_device("test-device-004")

    # 验证同步结果
    assert synced_device is not None
    assert synced_device.last_seen_at is not None
    # 验证last_seen_at是最近的时间
    assert isinstance(synced_device.last_seen_at, datetime)
    # 健康评分已更新 (mock模式下status=idle, battery=80)
    assert synced_device.health_score >= 60
    # 同步失败计数已重置
    assert synced_device.sync_failure_count == 0
    # mock模式下状态更新为idle
    assert synced_device.status == DeviceStatus.IDLE.value


def test_device_sync_sync_new_device(db_session):
    """Test syncing a new device that doesn't exist.

    测试同步不存在的新设备。
    """
    sync_service = DeviceSyncService(db_session)

    # 同步新设备
    synced_device = sync_service.sync_device("new-device-001")

    # 验证新设备已创建
    assert synced_device is not None
    assert synced_device.serial == "new-device-001"
    assert synced_device.status == DeviceStatus.IDLE.value
    assert synced_device.battery_level == 80  # mock模式默认值
    assert synced_device.last_seen_at is not None
    assert synced_device.health_score >= 60


# ==================== LeaseManager Tests ====================

def test_lease_manager_create_lease(db_session):
    """Test LeaseManager can create a lease.

    测试 LeaseManager 能够创建设备租约。
    """
    from chaosdroid.scheduling.lease_manager import LeaseManager
    from chaosdroid.scheduling.enums import LeaseStatus, DeviceStatus
    from chaosdroid.models.scenario import ScenarioRun
    from chaosdroid.models.base import RunStatus

    # 创建设备
    device = Device(
        serial="test-device-lease-001",
        status=DeviceStatus.IDLE.value,
        battery_level=80,
        health_score=90,
    )
    db_session.add(device)
    db_session.flush()

    # 创建场景执行记录
    run = ScenarioRun(
        device_serial="test-device-lease-001",
        status=RunStatus.QUEUED.value,
    )
    db_session.add(run)
    db_session.flush()

    # 创建租约管理器并创建租约
    lease_manager = LeaseManager(db_session)
    lease = lease_manager.create_lease(device, run, preemptible=True)

    # 验证租约已创建
    assert lease.id is not None
    assert lease.device_id == device.id
    assert lease.scenario_run_id == run.id
    assert lease.lease_status == LeaseStatus.ACTIVE.value
    assert lease.preemptible == True
    assert lease.leased_at is not None

    # 验证设备状态已变为 RESERVED
    db_session.refresh(device)
    assert device.status == DeviceStatus.RESERVED.value

    # 验证执行记录已更新
    db_session.refresh(run)
    assert run.device_id == device.id
    assert run.lease_id == lease.id
    assert run.allocated_at is not None


def test_lease_manager_release_lease(db_session):
    """Test LeaseManager can release a lease.

    测试 LeaseManager 能够释放设备租约。
    """
    from chaosdroid.scheduling.lease_manager import LeaseManager
    from chaosdroid.scheduling.enums import LeaseStatus, DeviceStatus
    from chaosdroid.models.scenario import ScenarioRun
    from chaosdroid.models.base import RunStatus

    # 创建设备和执行记录
    device = Device(
        serial="test-device-lease-002",
        status=DeviceStatus.IDLE.value,
        battery_level=80,
    )
    db_session.add(device)
    db_session.flush()

    run = ScenarioRun(
        device_serial="test-device-lease-002",
        status=RunStatus.QUEUED.value,
    )
    db_session.add(run)
    db_session.flush()

    # 创建租约
    lease_manager = LeaseManager(db_session)
    lease = lease_manager.create_lease(device, run)

    # 验证设备状态为 RESERVED
    db_session.refresh(device)
    assert device.status == DeviceStatus.RESERVED.value

    # 释放租约
    result = lease_manager.release_lease(lease)

    # 验证释放成功
    assert result == True

    # 验证租约状态已变为 RELEASED
    db_session.refresh(lease)
    assert lease.lease_status == LeaseStatus.RELEASED.value
    assert lease.released_at is not None

    # 验证设备状态已变为 IDLE
    db_session.refresh(device)
    assert device.status == DeviceStatus.IDLE.value


def test_lease_manager_release_lease_not_active(db_session):
    """Test releasing a non-active lease returns False.

    测试释放非活跃状态的租约返回 False。
    """
    from chaosdroid.scheduling.lease_manager import LeaseManager
    from chaosdroid.scheduling.enums import LeaseStatus, DeviceStatus
    from chaosdroid.models.scenario import ScenarioRun
    from chaosdroid.models.base import RunStatus

    # 创建设备和执行记录
    device = Device(
        serial="test-device-lease-003",
        status=DeviceStatus.IDLE.value,
        battery_level=80,
    )
    db_session.add(device)
    db_session.flush()

    run = ScenarioRun(
        device_serial="test-device-lease-003",
        status=RunStatus.QUEUED.value,
    )
    db_session.add(run)
    db_session.flush()

    # 创建租约
    lease_manager = LeaseManager(db_session)
    lease = lease_manager.create_lease(device, run)

    # 先释放租约
    lease_manager.release_lease(lease)

    # 再次尝试释放已释放的租约
    db_session.refresh(lease)
    result = lease_manager.release_lease(lease)

    # 验证返回 False
    assert result == False


def test_lease_manager_preempt_lease(db_session):
    """Test LeaseManager can preempt a lease.

    测试 LeaseManager 能够抢占租约。
    """
    from chaosdroid.scheduling.lease_manager import LeaseManager
    from chaosdroid.scheduling.enums import LeaseStatus, DeviceStatus
    from chaosdroid.models.scenario import ScenarioRun
    from chaosdroid.models.base import RunStatus

    # 创建设备
    device = Device(
        serial="test-device-lease-004",
        status=DeviceStatus.IDLE.value,
        battery_level=80,
    )
    db_session.add(device)
    db_session.flush()

    # 创建第一个场景执行记录
    old_run = ScenarioRun(
        device_serial="test-device-lease-004",
        status=RunStatus.QUEUED.value,
    )
    db_session.add(old_run)
    db_session.flush()

    # 创建租约管理器并创建第一个租约
    lease_manager = LeaseManager(db_session)
    old_lease = lease_manager.create_lease(device, old_run, preemptible=True)

    # 创建第二个场景执行记录（用于抢占）
    new_run = ScenarioRun(
        device_serial="test-device-lease-004",
        status=RunStatus.QUEUED.value,
    )
    db_session.add(new_run)
    db_session.flush()

    # 抢占租约
    new_lease = lease_manager.preempt_lease(old_lease, new_run)

    # 验证旧租约状态为 PREEMPTED
    db_session.refresh(old_lease)
    assert old_lease.lease_status == LeaseStatus.PREEMPTED.value
    assert old_lease.released_at is not None

    # 验证新租约状态为 ACTIVE
    assert new_lease.id is not None
    assert new_lease.lease_status == LeaseStatus.ACTIVE.value
    assert new_lease.device_id == device.id
    assert new_lease.scenario_run_id == new_run.id

    # 验证旧执行记录状态为 PREEMPTED
    db_session.refresh(old_run)
    assert old_run.status == RunStatus.PREEMPTED.value
    assert old_run.preempted_at is not None
    assert old_run.preempted_by_run_id == new_run.id

    # 验证新执行记录已更新
    db_session.refresh(new_run)
    assert new_run.device_id == device.id
    assert new_run.lease_id == new_lease.id
    assert new_run.allocated_at is not None


def test_lease_manager_get_active_lease(db_session):
    """Test LeaseManager can get active lease for a device.

    测试 LeaseManager 能够获取设备的活跃租约。
    """
    from chaosdroid.scheduling.lease_manager import LeaseManager
    from chaosdroid.scheduling.enums import LeaseStatus, DeviceStatus
    from chaosdroid.models.scenario import ScenarioRun
    from chaosdroid.models.base import RunStatus

    # 创建设备
    device = Device(
        serial="test-device-lease-005",
        status=DeviceStatus.IDLE.value,
        battery_level=80,
    )
    db_session.add(device)
    db_session.flush()

    run = ScenarioRun(
        device_serial="test-device-lease-005",
        status=RunStatus.QUEUED.value,
    )
    db_session.add(run)
    db_session.flush()

    # 创建租约
    lease_manager = LeaseManager(db_session)
    lease = lease_manager.create_lease(device, run)

    # 获取活跃租约
    active_lease = lease_manager.get_active_lease(device.id)

    # 验证获取到正确的租约
    assert active_lease is not None
    assert active_lease.id == lease.id
    assert active_lease.device_id == device.id
    assert active_lease.lease_status == LeaseStatus.ACTIVE.value

    # 释放租约后再次查询
    lease_manager.release_lease(lease)
    active_lease = lease_manager.get_active_lease(device.id)
    assert active_lease is None


def test_lease_manager_get_run_lease(db_session):
    """Test LeaseManager can get lease for a scenario run.

    测试 LeaseManager 能够获取场景执行的租约。
    """
    from chaosdroid.scheduling.lease_manager import LeaseManager
    from chaosdroid.scheduling.enums import LeaseStatus, DeviceStatus
    from chaosdroid.models.scenario import ScenarioRun
    from chaosdroid.models.base import RunStatus

    # 创建设备和执行记录
    device = Device(
        serial="test-device-lease-006",
        status=DeviceStatus.IDLE.value,
        battery_level=80,
    )
    db_session.add(device)
    db_session.flush()

    run = ScenarioRun(
        device_serial="test-device-lease-006",
        status=RunStatus.QUEUED.value,
    )
    db_session.add(run)
    db_session.flush()

    # 创建租约
    lease_manager = LeaseManager(db_session)
    lease = lease_manager.create_lease(device, run)

    # 获取执行记录的租约
    run_lease = lease_manager.get_run_lease(run.id)

    # 验证获取到正确的租约
    assert run_lease is not None
    assert run_lease.id == lease.id
    assert run_lease.scenario_run_id == run.id


def test_lease_manager_get_preemptable_leases(db_session):
    """Test LeaseManager can get preemptable leases.

    测试 LeaseManager 能够获取可抢占的租约列表。
    """
    from chaosdroid.scheduling.lease_manager import LeaseManager
    from chaosdroid.scheduling.enums import LeaseStatus, DeviceStatus
    from chaosdroid.models.scenario import ScenarioRun
    from chaosdroid.models.base import RunStatus

    # 创建设备
    device1 = Device(
        serial="test-device-lease-007",
        status=DeviceStatus.IDLE.value,
        battery_level=80,
    )
    device2 = Device(
        serial="test-device-lease-008",
        status=DeviceStatus.IDLE.value,
        battery_level=80,
    )
    db_session.add_all([device1, device2])
    db_session.flush()

    # 创建执行记录（run1 可中断，run2 不可中断）
    run1 = ScenarioRun(
        device_serial="test-device-lease-007",
        status=RunStatus.QUEUED.value,
        interruptible=True,
    )
    run2 = ScenarioRun(
        device_serial="test-device-lease-008",
        status=RunStatus.QUEUED.value,
        interruptible=False,
    )
    db_session.add_all([run1, run2])
    db_session.flush()

    # 创建租约管理器
    lease_manager = LeaseManager(db_session)

    # 创建可抢占租约（device1, run1）
    preemptable_lease = lease_manager.create_lease(device1, run1, preemptible=True)

    # 创建不可抢占租约（device2, run2）
    non_preemptable_lease = lease_manager.create_lease(device2, run2, preemptible=False)

    # 获取可抢占租约列表
    preemptable_leases = lease_manager.get_preemptable_leases()

    # 验证只有可抢占且可中断的租约
    assert len(preemptable_leases) >= 1
    assert preemptable_lease.id in [l.id for l in preemptable_leases]
    assert non_preemptable_lease.id not in [l.id for l in preemptable_leases]


# ==================== QuarantineService Tests ====================




@pytest.fixture
def test_device(db_session):
    """创建测试设备。"""
    device = Device(
        serial="test_device_001",
        model="Test Model",
        status=DeviceStatus.IDLE.value,
    )
    db_session.add(device)
    db_session.commit()
    return device


@pytest.fixture
def quarantined_device(db_session):
    """创建已隔离的测试设备。"""
    device = Device(
        serial="quarantined_device_001",
        model="Test Model",
        status=DeviceStatus.QUARANTINED.value,
        quarantine_reason="Test quarantine",
        sync_failure_count=5,
    )
    db_session.add(device)
    db_session.commit()
    return device


def test_quarantine_service_quarantine_device(db_session, test_device):
    """测试设备隔离。"""
    from chaosdroid.models.event import IncidentEvent
    from chaosdroid.scheduling.quarantine import QuarantineService
    from chaosdroid.scheduling.enums import EventType, EventSeverity

    service = QuarantineService(db_session)

    # 验证初始状态
    assert test_device.status == DeviceStatus.IDLE.value
    assert test_device.quarantine_reason is None

    # 隔离设备
    result = service.quarantine_device(
        test_device,
        "Health check failed",
        EventSeverity.WARNING,
    )

    # 验证隔离成功
    assert result is True
    assert test_device.status == DeviceStatus.QUARANTINED.value
    assert test_device.quarantine_reason == "Health check failed"

    # 验证事件已创建
    events = db_session.query(IncidentEvent).filter(
        IncidentEvent.device_id == test_device.id,
        IncidentEvent.event_type == EventType.DEVICE_QUARANTINED.value,
    ).all()
    assert len(events) == 1
    assert events[0].severity == EventSeverity.WARNING.value


def test_quarantine_service_quarantine_already_quarantined(db_session, quarantined_device):
    """测试隔离已隔离的设备。"""
    from chaosdroid.scheduling.quarantine import QuarantineService

    service = QuarantineService(db_session)

    # 尝试隔离已隔离的设备
    result = service.quarantine_device(
        quarantined_device,
        "New reason",
    )

    # 应返回False，状态不变
    assert result is False
    assert quarantined_device.quarantine_reason == "Test quarantine"


def test_quarantine_service_recover_device(db_session, quarantined_device):
    """测试设备恢复。"""
    from chaosdroid.models.event import IncidentEvent
    from chaosdroid.scheduling.quarantine import QuarantineService
    from chaosdroid.scheduling.enums import EventType, EventSeverity

    service = QuarantineService(db_session)

    # 验证初始状态
    assert quarantined_device.status == DeviceStatus.QUARANTINED.value
    assert quarantined_device.quarantine_reason is not None
    assert quarantined_device.sync_failure_count > 0

    # 恢复设备
    result = service.recover_device(quarantined_device, "Manual recovery")

    # 验证恢复成功
    assert result is True
    assert quarantined_device.status == DeviceStatus.IDLE.value
    assert quarantined_device.quarantine_reason is None
    assert quarantined_device.sync_failure_count == 0

    # 验证事件已创建
    events = db_session.query(IncidentEvent).filter(
        IncidentEvent.device_id == quarantined_device.id,
        IncidentEvent.event_type == EventType.DEVICE_RECOVERED.value,
    ).all()
    assert len(events) == 1
    assert events[0].severity == EventSeverity.INFO.value


def test_quarantine_service_recover_non_quarantined(db_session, test_device):
    """测试恢复未隔离的设备。"""
    from chaosdroid.scheduling.quarantine import QuarantineService

    service = QuarantineService(db_session)

    # 尝试恢复未隔离的设备
    result = service.recover_device(test_device)

    # 应返回False，状态不变
    assert result is False
    assert test_device.status == DeviceStatus.IDLE.value


def test_quarantine_service_get_quarantined(db_session):
    """测试获取隔离设备列表。"""
    from chaosdroid.scheduling.quarantine import QuarantineService

    service = QuarantineService(db_session)

    # 创建混合状态的设备
    idle_device = Device(
        serial="idle_device",
        status=DeviceStatus.IDLE.value,
    )
    quarantined_device1 = Device(
        serial="quarantined_1",
        status=DeviceStatus.QUARANTINED.value,
        quarantine_reason="Reason 1",
    )
    quarantined_device2 = Device(
        serial="quarantined_2",
        status=DeviceStatus.QUARANTINED.value,
        quarantine_reason="Reason 2",
    )
    busy_device = Device(
        serial="busy_device",
        status=DeviceStatus.BUSY.value,
    )

    db_session.add_all([idle_device, quarantined_device1, quarantined_device2, busy_device])
    db_session.commit()

    # 获取隔离设备列表
    quarantined = service.get_quarantined_devices()

    # 验证只返回隔离设备
    assert len(quarantined) == 2
    serials = [d.serial for d in quarantined]
    assert "quarantined_1" in serials
    assert "quarantined_2" in serials
    assert "idle_device" not in serials
    assert "busy_device" not in serials


def test_quarantine_service_check_and_quarantine(db_session):
    """测试自动检查和隔离异常设备。"""
    from chaosdroid.scheduling.quarantine import QuarantineService

    service = QuarantineService(db_session)

    # 创建不同同步失败次数的设备
    normal_device = Device(
        serial="normal_device",
        status=DeviceStatus.IDLE.value,
        sync_failure_count=1,
    )
    failing_device1 = Device(
        serial="failing_device_1",
        status=DeviceStatus.IDLE.value,
        sync_failure_count=3,
    )
    failing_device2 = Device(
        serial="failing_device_2",
        status=DeviceStatus.IDLE.value,
        sync_failure_count=5,
    )
    already_quarantined = Device(
        serial="already_quarantined",
        status=DeviceStatus.QUARANTINED.value,
        sync_failure_count=10,
        quarantine_reason="Already quarantined",
    )

    db_session.add_all([normal_device, failing_device1, failing_device2, already_quarantined])
    db_session.commit()

    # 检查并隔离
    count = service.check_and_quarantine(max_sync_failures=3)

    # 验证隔离数量（已隔离的设备不应再次隔离）
    assert count == 2

    # 验证设备状态
    db_session.refresh(normal_device)
    db_session.refresh(failing_device1)
    db_session.refresh(failing_device2)
    db_session.refresh(already_quarantined)

    assert normal_device.status == DeviceStatus.IDLE.value
    assert failing_device1.status == DeviceStatus.QUARANTINED.value
    assert failing_device2.status == DeviceStatus.QUARANTINED.value
    assert already_quarantined.status == DeviceStatus.QUARANTINED.value


# ==================== PoolManager Tests ====================

def test_pool_manager_get_candidate_devices(db_session):
    """Test PoolManager can get candidate devices.

    测试 PoolManager 能够获取候选设备列表。
    """
    from chaosdroid.scheduling.pool_manager import PoolManager
    from chaosdroid.models.device_pool import DevicePool
    import json

    # 创建设备池
    pool = DevicePool(
        name="test-pool-001",
        purpose="stable",
        reserved_emergency_ratio=0.2,
        enabled=True,
    )
    db_session.add(pool)
    db_session.flush()

    # 创建设备：一些空闲，一些忙碌
    idle_device1 = Device(
        serial="idle-device-001",
        status=DeviceStatus.IDLE.value,
        health_score=80,
        pool_id=pool.id,
        tags_json=json.dumps(["android", "stable"]),
    )
    idle_device2 = Device(
        serial="idle-device-002",
        status=DeviceStatus.IDLE.value,
        health_score=60,
        pool_id=pool.id,
        tags_json=json.dumps(["android"]),
    )
    busy_device = Device(
        serial="busy-device-001",
        status=DeviceStatus.BUSY.value,
        health_score=90,
        pool_id=pool.id,
    )
    offline_device = Device(
        serial="offline-device-001",
        status=DeviceStatus.OFFLINE.value,
        health_score=50,
        pool_id=pool.id,
    )
    low_health_device = Device(
        serial="low-health-device-001",
        status=DeviceStatus.IDLE.value,
        health_score=30,  # 低于默认阈值40
        pool_id=pool.id,
    )
    db_session.add_all([idle_device1, idle_device2, busy_device, offline_device, low_health_device])
    db_session.commit()

    # 创建 PoolManager
    pool_manager = PoolManager(db_session)

    # 获取候选设备
    candidates = pool_manager.get_candidate_devices(pool_id=pool.id)

    # 验证只有空闲且健康分满足要求的设备
    assert len(candidates) == 2
    candidate_serials = [d.serial for d in candidates]
    assert "idle-device-001" in candidate_serials
    assert "idle-device-002" in candidate_serials
    assert "busy-device-001" not in candidate_serials
    assert "offline-device-001" not in candidate_serials
    assert "low-health-device-001" not in candidate_serials

    # 测试标签过滤
    tagged_candidates = pool_manager.get_candidate_devices(
        pool_id=pool.id,
        required_tags=["stable"],
    )
    assert len(tagged_candidates) == 1
    assert tagged_candidates[0].serial == "idle-device-001"

    # 测试健康分阈值
    high_health_candidates = pool_manager.get_candidate_devices(
        pool_id=pool.id,
        min_health=70,
    )
    assert len(high_health_candidates) == 1
    assert high_health_candidates[0].serial == "idle-device-001"


def test_pool_manager_select_best_device(db_session):
    """Test PoolManager selects device with highest health score.

    测试 PoolManager 选择健康分最高的设备。
    """
    from chaosdroid.scheduling.pool_manager import PoolManager

    # 创建测试设备（不存入数据库，仅测试排序逻辑）
    device1 = Device(
        serial="device-001",
        status=DeviceStatus.IDLE.value,
        health_score=90,
        last_seen_at=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
    )
    device2 = Device(
        serial="device-002",
        status=DeviceStatus.IDLE.value,
        health_score=80,
        last_seen_at=datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc),  # 更早 = 空闲更久
    )
    device3 = Device(
        serial="device-003",
        status=DeviceStatus.IDLE.value,
        health_score=80,
        last_seen_at=datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc),  # 更晚
    )

    # 创建 PoolManager
    pool_manager = PoolManager(db_session)

    # 测试选择最佳设备：健康分最高的
    candidates = [device1, device2, device3]
    best = pool_manager.select_best_device(candidates)
    assert best.serial == "device-001"  # 健康分最高

    # 测试相同健康分时选择空闲时间最长的
    candidates2 = [device2, device3]
    best2 = pool_manager.select_best_device(candidates2)
    assert best2.serial == "device-002"  # 健康分相同，但空闲更久

    # 测试空列表
    best3 = pool_manager.select_best_device([])
    assert best3 is None


def test_pool_manager_get_available_capacity(db_session):
    """Test PoolManager calculates available capacity correctly.

    测试 PoolManager 正确计算可用容量。
    """
    from chaosdroid.scheduling.pool_manager import PoolManager
    from chaosdroid.models.device_pool import DevicePool

    # 创建设备池（预留比例 0.2）
    pool = DevicePool(
        name="capacity-test-pool",
        purpose="stress",
        reserved_emergency_ratio=0.2,
        enabled=True,
    )
    db_session.add(pool)
    db_session.flush()

    # 创建设备：3个空闲，2个忙碌
    for i in range(3):
        device = Device(
            serial=f"capacity-idle-{i}",
            status=DeviceStatus.IDLE.value,
            health_score=80,
            pool_id=pool.id,
        )
        db_session.add(device)

    for i in range(2):
        device = Device(
            serial=f"capacity-busy-{i}",
            status=DeviceStatus.BUSY.value,
            health_score=80,
            pool_id=pool.id,
        )
        db_session.add(device)

    db_session.commit()

    # 创建 PoolManager
    pool_manager = PoolManager(db_session)

    # 计算可用容量
    # 总设备数 = 5，预留比例 = 0.2，预留设备 = 1
    # 空闲设备数 = 3，可用容量 = 3 - 1 = 2
    capacity = pool_manager.get_available_capacity(pool)
    assert capacity == 2


def test_pool_manager_create_and_get_pool(db_session):
    """Test PoolManager can create and retrieve pools.

    测试 PoolManager 能够创建和查询设备池。
    """
    from chaosdroid.scheduling.pool_manager import PoolManager
    from chaosdroid.scheduling.enums import DevicePoolPurpose

    # 创建 PoolManager
    pool_manager = PoolManager(db_session)

    # 创建设备池
    pool = pool_manager.create_pool(
        name="create-test-pool",
        purpose=DevicePoolPurpose.STABLE.value,
        reserved_emergency_ratio=0.15,
        max_parallel_jobs=10,
        enabled=True,
    )
    db_session.commit()

    # 验证设备池已创建
    assert pool.id is not None
    assert pool.name == "create-test-pool"
    assert pool.purpose == "stable"
    assert pool.reserved_emergency_ratio == 0.15
    assert pool.max_parallel_jobs == 10
    assert pool.enabled == True

    # 通过ID获取设备池
    retrieved_pool = pool_manager.get_pool(pool.id)
    assert retrieved_pool is not None
    assert retrieved_pool.name == "create-test-pool"

    # 通过名称获取设备池
    retrieved_pool2 = pool_manager.get_pool_by_name("create-test-pool")
    assert retrieved_pool2 is not None
    assert retrieved_pool2.id == pool.id


def test_pool_manager_list_pools(db_session):
    """Test PoolManager can list pools.

    测试 PoolManager 能够列出设备池。
    """
    from chaosdroid.scheduling.pool_manager import PoolManager
    from chaosdroid.scheduling.enums import DevicePoolPurpose

    # 创建 PoolManager
    pool_manager = PoolManager(db_session)

    # 创建多个设备池
    pool1 = pool_manager.create_pool(
        name="list-pool-1",
        purpose=DevicePoolPurpose.STABLE.value,
        enabled=True,
    )
    pool2 = pool_manager.create_pool(
        name="list-pool-2",
        purpose=DevicePoolPurpose.STRESS.value,
        enabled=True,
    )
    pool3 = pool_manager.create_pool(
        name="list-pool-3",
        purpose=DevicePoolPurpose.EMERGENCY.value,
        enabled=False,  # 禁用
    )
    db_session.commit()

    # 列出启用的设备池
    enabled_pools = pool_manager.list_pools(enabled_only=True)
    assert len(enabled_pools) == 2
    pool_names = [p.name for p in enabled_pools]
    assert "list-pool-1" in pool_names
    assert "list-pool-2" in pool_names
    assert "list-pool-3" not in pool_names

    # 列出所有设备池
    all_pools = pool_manager.list_pools(enabled_only=False)
    assert len(all_pools) >= 3


def test_pool_manager_update_pool(db_session):
    """Test PoolManager can update pools.

    测试 PoolManager 能够更新设备池。
    """
    from chaosdroid.scheduling.pool_manager import PoolManager
    from chaosdroid.scheduling.enums import DevicePoolPurpose

    # 创建 PoolManager
    pool_manager = PoolManager(db_session)

    # 创建设备池
    pool = pool_manager.create_pool(
        name="update-test-pool",
        purpose=DevicePoolPurpose.STABLE.value,
        reserved_emergency_ratio=0.2,
        enabled=True,
    )
    db_session.commit()

    # 更新设备池
    updated_pool = pool_manager.update_pool(
        pool_id=pool.id,
        reserved_emergency_ratio=0.3,
        enabled=False,
    )
    db_session.commit()

    # 验证更新成功
    assert updated_pool is not None
    assert updated_pool.reserved_emergency_ratio == 0.3
    assert updated_pool.enabled == False


def test_pool_manager_delete_pool(db_session):
    """Test PoolManager can delete pools.

    测试 PoolManager 能够删除设备池。
    """
    from chaosdroid.scheduling.pool_manager import PoolManager
    from chaosdroid.scheduling.enums import DevicePoolPurpose

    # 创建 PoolManager
    pool_manager = PoolManager(db_session)

    # 创建设备池
    pool = pool_manager.create_pool(
        name="delete-test-pool",
        purpose=DevicePoolPurpose.STABLE.value,
    )
    db_session.commit()
    pool_id = pool.id

    # 删除设备池
    result = pool_manager.delete_pool(pool_id)
    db_session.commit()

    # 验证删除成功
    assert result == True

    # 验证设备池已不存在
    retrieved_pool = pool_manager.get_pool(pool_id)
    assert retrieved_pool is None

    # 删除不存在的设备池
    result2 = pool_manager.delete_pool(pool_id)
    assert result2 == False


def test_pool_manager_invalid_purpose(db_session):
    """Test PoolManager rejects invalid purpose value.

    测试 PoolManager 拒绝无效的 purpose 值。
    """
    from chaosdroid.scheduling.pool_manager import PoolManager

    # 创建 PoolManager
    pool_manager = PoolManager(db_session)

    # 尝试创建无效 purpose 的设备池
    with pytest.raises(ValueError) as exc_info:
        pool_manager.create_pool(
            name="invalid-purpose-pool",
            purpose="invalid_purpose",
        )

    assert "无效的purpose值" in str(exc_info.value)


# ==================== Scheduler Tests ====================


async def test_scheduler_schedule_once(async_db_session):
    """Test Scheduler can allocate devices to queued runs.

    测试 Scheduler 能够为排队中的任务分配设备。
    """
    from chaosdroid.scheduling.scheduler import Scheduler
    from chaosdroid.scheduling.enums import DeviceStatus, Priority
    from chaosdroid.models.scenario import ScenarioRun
    from chaosdroid.models.base import RunStatus

    # 创建3个设备
    devices = [
        Device(
            serial=f"test-device-{i}",
            status=DeviceStatus.IDLE.value,
            battery_level=80,
            health_score=90,
        )
        for i in range(3)
    ]
    async_db_session.add_all(devices)
    await async_db_session.flush()

    # 创建5个排队任务（比设备多）
    runs = [
        ScenarioRun(
            device_serial=f"test-device-{i % 3}",
            status=RunStatus.QUEUED.value,
            priority=Priority.NORMAL.value,
            interruptible=True,
        )
        for i in range(5)
    ]
    async_db_session.add_all(runs)
    await async_db_session.flush()

    # 创建调度器并执行一次调度
    scheduler = Scheduler(async_db_session)
    allocated_count = await scheduler.schedule_once()

    # 验证只有3个任务被分配（因为只有3个设备）
    assert allocated_count == 3

    # 验证已分配任务状态为 RESERVED
    await async_db_session.refresh(runs[0])
    await async_db_session.refresh(runs[1])
    await async_db_session.refresh(runs[2])
    assert runs[0].status == RunStatus.RESERVED.value
    assert runs[1].status == RunStatus.RESERVED.value
    assert runs[2].status == RunStatus.RESERVED.value

    # 验证未分配任务仍为 QUEUED
    await async_db_session.refresh(runs[3])
    await async_db_session.refresh(runs[4])
    assert runs[3].status == RunStatus.QUEUED.value
    assert runs[4].status == RunStatus.QUEUED.value


async def test_scheduler_priority_ordering(async_db_session):
    """Test Scheduler processes runs in priority order.

    测试 Scheduler 按优先级顺序处理任务。
    """
    from chaosdroid.scheduling.scheduler import Scheduler
    from chaosdroid.scheduling.enums import DeviceStatus, Priority
    from chaosdroid.models.scenario import ScenarioRun
    from chaosdroid.models.base import RunStatus

    # 创建1个设备
    device = Device(
        serial="test-device-priority",
        status=DeviceStatus.IDLE.value,
        battery_level=80,
        health_score=90,
    )
    async_db_session.add(device)
    await async_db_session.flush()

    # 创建3个不同优先级的任务：normal, high, emergency
    normal_run = ScenarioRun(
        device_serial="test-device-priority",
        status=RunStatus.QUEUED.value,
        priority=Priority.NORMAL.value,
        interruptible=True,
    )
    high_run = ScenarioRun(
        device_serial="test-device-priority",
        status=RunStatus.QUEUED.value,
        priority=Priority.HIGH.value,
        interruptible=True,
    )
    emergency_run = ScenarioRun(
        device_serial="test-device-priority",
        status=RunStatus.QUEUED.value,
        priority=Priority.EMERGENCY.value,
        interruptible=False,
    )
    async_db_session.add_all([normal_run, high_run, emergency_run])
    await async_db_session.flush()

    # 创建调度器并执行调度
    scheduler = Scheduler(async_db_session)
    allocated_count = await scheduler.schedule_once()

    # 验证只有1个任务被分配（只有1个设备）
    assert allocated_count == 1

    # 验证emergency任务被分配（优先级最高）
    await async_db_session.refresh(emergency_run)
    await async_db_session.refresh(high_run)
    await async_db_session.refresh(normal_run)

    # emergency 应被分配
    assert emergency_run.status == RunStatus.RESERVED.value
    assert emergency_run.device_id == device.id

    # high 和 normal 应仍为 queued
    assert high_run.status == RunStatus.QUEUED.value
    assert normal_run.status == RunStatus.QUEUED.value


async def test_scheduler_emergency_preemption(async_db_session):
    """Test Scheduler can preempt running tasks for emergency.

    测试 Scheduler 能够为紧急任务抢占正在运行的任务。
    """
    from chaosdroid.scheduling.scheduler import Scheduler
    from chaosdroid.scheduling.enums import DeviceStatus, Priority, LeaseStatus
    from chaosdroid.scheduling.lease_manager import LeaseManager
    from chaosdroid.models.scenario import ScenarioRun
    from chaosdroid.models.device_lease import DeviceLease
    from chaosdroid.models.base import RunStatus

    # 创建1个设备
    device = Device(
        serial="test-device-preempt",
        status=DeviceStatus.IDLE.value,
        battery_level=80,
        health_score=90,
    )
    async_db_session.add(device)
    await async_db_session.flush()

    # 创建一个可抢占的任务（normal优先级，interruptible=True）
    normal_run = ScenarioRun(
        device_serial="test-device-preempt",
        status=RunStatus.QUEUED.value,
        priority=Priority.NORMAL.value,
        interruptible=True,  # 可被抢占
    )
    async_db_session.add(normal_run)
    await async_db_session.flush()

    # 手动分配设备给normal任务（模拟已有运行任务）
    lease_manager = LeaseManager(async_db_session)
    lease = await lease_manager.create_lease(device, normal_run, preemptible=True)

    # 验证设备已被分配
    await async_db_session.refresh(device)
    assert device.status == DeviceStatus.RESERVED.value
    await async_db_session.refresh(normal_run)
    assert normal_run.status == RunStatus.RESERVED.value

    # 创建紧急任务
    emergency_run = ScenarioRun(
        device_serial="test-device-preempt",
        status=RunStatus.QUEUED.value,
        priority=Priority.EMERGENCY.value,
        interruptible=False,
    )
    async_db_session.add(emergency_run)
    await async_db_session.flush()

    # 执行调度（应该抢占normal任务）
    scheduler = Scheduler(async_db_session)
    allocated_count = await scheduler.schedule_once()

    # 验证emergency任务被分配
    assert allocated_count == 1

    # 验证emergency任务状态
    await async_db_session.refresh(emergency_run)
    assert emergency_run.status == RunStatus.RESERVED.value
    assert emergency_run.device_id == device.id

    # 验证normal任务被抢占
    await async_db_session.refresh(normal_run)
    assert normal_run.status == RunStatus.PREEMPTED.value
    assert normal_run.preempted_by_run_id == emergency_run.id

    # 验证旧租约被抢占
    await async_db_session.refresh(lease)
    assert lease.lease_status == LeaseStatus.PREEMPTED.value


async def test_scheduler_get_scheduling_stats(async_db_session):
    """Test Scheduler can get scheduling statistics.

    测试 Scheduler 能够获取调度统计信息。
    """
    from chaosdroid.scheduling.scheduler import Scheduler
    from chaosdroid.scheduling.enums import DeviceStatus, Priority
    from chaosdroid.models.scenario import ScenarioRun
    from chaosdroid.models.base import RunStatus

    # 创建设备
    devices = [
        Device(
            serial=f"stats-device-{i}",
            status=DeviceStatus.IDLE.value,
            battery_level=80,
            health_score=90,
        )
        for i in range(2)
    ]
    async_db_session.add_all(devices)
    await async_db_session.flush()

    # 创建不同状态的任务
    queued_run = ScenarioRun(
        device_serial="stats-device-0",
        status=RunStatus.QUEUED.value,
        priority=Priority.NORMAL.value,
    )
    reserved_run = ScenarioRun(
        device_serial="stats-device-1",
        status=RunStatus.RESERVED.value,
        priority=Priority.HIGH.value,
    )
    preempted_run = ScenarioRun(
        device_serial="stats-device-0",
        status=RunStatus.PREEMPTED.value,
        priority=Priority.NORMAL.value,
    )
    async_db_session.add_all([queued_run, reserved_run, preempted_run])
    await async_db_session.flush()

    # 获取统计信息
    scheduler = Scheduler(async_db_session)
    stats = await scheduler.get_scheduling_stats()

    # 验证统计信息
    assert stats["queued_runs"] == 1
    assert stats["reserved_runs"] == 1
    assert stats["preempted_runs"] == 1
    assert stats["idle_devices"] == 2  # 两个IDLE设备