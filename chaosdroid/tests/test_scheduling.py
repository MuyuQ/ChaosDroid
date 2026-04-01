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