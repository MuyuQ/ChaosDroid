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

    # 创建执行记录
    run1 = ScenarioRun(
        device_serial="test-device-lease-007",
        status=RunStatus.QUEUED.value,
    )
    run2 = ScenarioRun(
        device_serial="test-device-lease-008",
        status=RunStatus.QUEUED.value,
    )
    db_session.add_all([run1, run2])
    db_session.flush()

    # 创建租约管理器
    lease_manager = LeaseManager(db_session)

    # 创建可抢占租约
    preemptable_lease = lease_manager.create_lease(device1, run1, preemptible=True)

    # 创建不可抢占租约
    non_preemptable_lease = lease_manager.create_lease(device2, run2, preemptible=False)

    # 获取可抢占租约列表
    preemptable_leases = lease_manager.get_preemptable_leases()

    # 验证只有可抢占的租约
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