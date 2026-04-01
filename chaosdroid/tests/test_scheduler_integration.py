"""Integration tests for the scheduling system."""
import pytest
import os
import tempfile

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def db_session():
    """Set up in-memory database for integration tests."""
    # 使用临时文件数据库避免内存数据库的问题
    db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = db_file.name
    db_file.close()

    os.environ["CHAOSDROID_DATABASE_PATH"] = db_path

    from chaosdroid.models import Base, init_engine, get_session_factory

    init_engine(db_path)
    engine = create_engine(f"sqlite:///{db_path}")

    # 创建所有表
    Base.metadata.create_all(engine)

    Session = sessionmaker(bind=engine)
    session = Session()

    yield session

    session.close()
    engine.dispose()

    # 清理临时文件
    try:
        os.unlink(db_path)
    except OSError:
        pass


def test_full_scheduling_flow(db_session):
    """Test complete flow: submit -> schedule -> allocate -> release."""
    from chaosdroid.models.device import Device
    from chaosdroid.models.device_pool import DevicePool
    from chaosdroid.models.scenario import ScenarioTemplate, ScenarioRun
    from chaosdroid.models.device_lease import DeviceLease
    from chaosdroid.scheduling import Scheduler, PoolManager, LeaseManager

    session = db_session

    # 1. Create pool and devices
    pool = DevicePool(name="stable_pool", purpose="stable")
    session.add(pool)
    session.flush()

    for i in range(3):
        device = Device(
            serial=f"DEV{i:03d}",
            status="idle",
            health_score=80,
            pool_id=pool.id,
        )
        session.add(device)
    session.flush()

    # 2. Create template and runs
    template = ScenarioTemplate(name="test_scenario", device_pool_id=pool.id)
    session.add(template)
    session.flush()

    runs = []
    for i in range(5):  # More runs than devices
        run = ScenarioRun(
            device_serial="auto",
            status="queued",
            priority="normal",
            interruptible=True,
            scenario_template_id=template.id,
            device_pool_id=pool.id,
        )
        session.add(run)
        runs.append(run)
    session.flush()

    # 3. Schedule
    scheduler = Scheduler(session)
    allocated = scheduler.schedule_once()

    assert allocated == 3  # Only 3 devices available

    # 4. Verify allocation
    session.flush()
    for run in runs[:3]:
        session.refresh(run)
        assert run.status == "reserved"
        assert run.device_id is not None
        assert run.lease_id is not None

    # Remaining runs should still be queued
    for run in runs[3:]:
        session.refresh(run)
        assert run.status == "queued"


def test_emergency_preemption_flow(db_session):
    """Test emergency task preempts normal task."""
    from chaosdroid.models.device import Device
    from chaosdroid.models.device_pool import DevicePool
    from chaosdroid.models.scenario import ScenarioTemplate, ScenarioRun
    from chaosdroid.models.device_lease import DeviceLease
    from chaosdroid.scheduling import Scheduler, LeaseManager

    session = db_session

    # Create pool
    pool = DevicePool(name="emergency_pool", purpose="stable")
    session.add(pool)
    session.flush()

    # Create one device
    device = Device(serial="DEV001", status="idle", health_score=80, pool_id=pool.id)
    session.add(device)
    session.flush()

    # Create template
    template = ScenarioTemplate(name="preemption_test", device_pool_id=pool.id)
    session.add(template)
    session.flush()

    # Create and allocate normal run
    normal_run = ScenarioRun(
        device_serial="auto",
        status="queued",
        priority="normal",
        interruptible=True,
        scenario_template_id=template.id,
        device_pool_id=pool.id,
    )
    session.add(normal_run)
    session.flush()

    scheduler = Scheduler(session)
    scheduler.schedule_once()

    session.refresh(normal_run)
    assert normal_run.status == "reserved"
    assert normal_run.device_id == device.id

    # Create lease manually for the allocated device
    lease_manager = LeaseManager(session)
    session.refresh(device)
    session.refresh(normal_run)

    # Get the existing lease created by scheduler
    existing_lease = session.query(DeviceLease).filter(
        DeviceLease.scenario_run_id == normal_run.id
    ).first()
    assert existing_lease is not None

    # Mark device as busy (simulate run starting)
    device.status = "busy"
    normal_run.status = "injecting"
    session.flush()

    # Submit emergency run
    emergency_run = ScenarioRun(
        device_serial="auto",
        status="queued",
        priority="emergency",
        interruptible=False,
        scenario_template_id=template.id,
        device_pool_id=pool.id,
    )
    session.add(emergency_run)
    session.flush()

    # Schedule again - emergency should preempt
    scheduler.schedule_once()

    # Verify emergency run got the device
    session.refresh(emergency_run)
    assert emergency_run.status == "reserved"

    # Verify normal run was preempted
    session.refresh(normal_run)
    assert normal_run.status == "preempted"
    assert normal_run.preempted_by_run_id == emergency_run.id


def test_pool_capacity_management(db_session):
    """Test pool capacity calculation with reserved emergency ratio."""
    from chaosdroid.models.device import Device
    from chaosdroid.models.device_pool import DevicePool
    from chaosdroid.scheduling import PoolManager

    session = db_session

    # Create pool with 20% reserved for emergency
    pool = DevicePool(
        name="capacity_pool",
        purpose="stable",
        reserved_emergency_ratio=0.2,
    )
    session.add(pool)
    session.flush()

    # Add 5 idle devices
    for i in range(5):
        device = Device(
            serial=f"CAP{i:03d}",
            status="idle",
            health_score=90,
            pool_id=pool.id,
        )
        session.add(device)
    session.flush()

    pool_manager = PoolManager(session)

    # Available capacity should be: 5 idle - (5 total * 0.2 reserved) = 5 - 1 = 4
    capacity = pool_manager.get_available_capacity(pool)
    assert capacity == 4


def test_device_health_selection(db_session):
    """Test scheduler selects highest health device."""
    from chaosdroid.models.device import Device
    from chaosdroid.models.device_pool import DevicePool
    from chaosdroid.models.scenario import ScenarioTemplate, ScenarioRun
    from chaosdroid.scheduling import PoolManager

    session = db_session

    # Create pool
    pool = DevicePool(name="health_pool", purpose="stable")
    session.add(pool)
    session.flush()

    # Create devices with different health scores
    devices = [
        Device(serial="LOW001", status="idle", health_score=50, pool_id=pool.id),
        Device(serial="HIGH001", status="idle", health_score=95, pool_id=pool.id),
        Device(serial="MED001", status="idle", health_score=70, pool_id=pool.id),
    ]
    for d in devices:
        session.add(d)
    session.flush()

    pool_manager = PoolManager(session)
    candidates = pool_manager.get_candidate_devices(pool_id=pool.id, min_health=40)

    # Should get 3 candidates
    assert len(candidates) == 3

    # Best device should be HIGH001 (highest health)
    best = pool_manager.select_best_device(candidates)
    assert best.serial == "HIGH001"
    assert best.health_score == 95


def test_lease_release_flow(db_session):
    """Test releasing lease returns device to idle."""
    from chaosdroid.models.device import Device
    from chaosdroid.models.device_pool import DevicePool
    from chaosdroid.models.scenario import ScenarioTemplate, ScenarioRun
    from chaosdroid.models.device_lease import DeviceLease
    from chaosdroid.scheduling import LeaseManager

    session = db_session

    # Setup
    pool = DevicePool(name="release_pool", purpose="stable")
    session.add(pool)
    session.flush()

    device = Device(serial="REL001", status="reserved", health_score=80, pool_id=pool.id)
    session.add(device)
    session.flush()

    template = ScenarioTemplate(name="release_test", device_pool_id=pool.id)
    session.add(template)
    session.flush()

    run = ScenarioRun(
        device_serial="REL001",
        status="reserved",
        priority="normal",
        interruptible=True,
        scenario_template_id=template.id,
        device_pool_id=pool.id,
        device_id=device.id,
    )
    session.add(run)
    session.flush()

    # Create active lease
    lease = DeviceLease(
        device_id=device.id,
        scenario_run_id=run.id,
        lease_status="active",
        preemptible=True,
    )
    session.add(lease)
    session.flush()

    # Release the lease
    lease_manager = LeaseManager(session)
    result = lease_manager.release_lease(lease)

    assert result == True

    # Verify device is now idle
    session.refresh(device)
    assert device.status == "idle"

    # Verify lease is released
    session.refresh(lease)
    assert lease.lease_status == "released"
    assert lease.released_at is not None


def test_concurrent_pool_operations(db_session):
    """Test multiple pool operations in sequence."""
    from chaosdroid.models.device_pool import DevicePool
    from chaosdroid.scheduling import PoolManager

    session = db_session

    pool_manager = PoolManager(session)

    # Create multiple pools
    pool1 = pool_manager.create_pool(
        name="stable_test",
        purpose="stable",
        reserved_emergency_ratio=0.3,
    )

    pool2 = pool_manager.create_pool(
        name="stress_test",
        purpose="stress",
        reserved_emergency_ratio=0.1,
    )

    session.flush()

    # List pools
    pools = pool_manager.list_pools(enabled_only=True)
    assert len(pools) == 2

    # Update pool
    updated = pool_manager.update_pool(pool1.id, reserved_emergency_ratio=0.25)
    session.refresh(pool1)
    assert pool1.reserved_emergency_ratio == 0.25

    # Delete pool
    deleted = pool_manager.delete_pool(pool2.id)
    assert deleted == True

    # Verify deletion
    remaining = pool_manager.list_pools(enabled_only=True)
    assert len(remaining) == 1
    assert remaining[0].name == "stable_test"