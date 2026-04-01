"""Tests for scheduling module."""
import pytest


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