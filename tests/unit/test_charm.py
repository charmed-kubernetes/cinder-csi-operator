# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

from unittest.mock import Mock

import pytest
from charms.openstack_cloud_controller_operator.v0.cloud_config import (
    MockCloudConfigProvides,
)
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from ops.testing import Harness

from charm import CinderCSIOperatorCharm


@pytest.fixture
def harness():
    harness = Harness(CinderCSIOperatorCharm)
    try:
        yield harness
    finally:
        harness.cleanup()


@pytest.fixture
def lk_client(monkeypatch):
    monkeypatch.setattr(
        "charms.openstack_cloud_controller_operator.v0.lightkube_helpers.Client",
        client := Mock(name="lightkube.Client"),
    )
    return client


def test_cinder_csi(harness, lk_client):
    harness.set_leader(True)
    harness.begin_with_initial_hooks()
    assert isinstance(harness.charm.unit.status, BlockedStatus)

    cc_provides = MockCloudConfigProvides(harness)
    cc_provides.relate()
    assert isinstance(harness.charm.unit.status, WaitingStatus)
    cc_provides.send_hash("hash")
    assert isinstance(harness.charm.unit.status, ActiveStatus)
