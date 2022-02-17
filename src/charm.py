#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
"""Deploy and manage the Cinder CSI plugin for K8s on OpenStack."""

import logging
from pathlib import Path

from charms.openstack_cloud_controller_operator.v0.cloud_config import (
    CloudConfigRequires,
)
from charms.openstack_cloud_controller_operator.v0.lightkube_helpers import (
    LightKubeHelpers,
)
from lightkube.resources.storage_v1 import StorageClass
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus

logger = logging.getLogger(__name__)


class CinderCSIOperatorCharm(CharmBase):
    """Deploy and manage the Cinder CSI plugin for K8s on OpenStack."""

    manifests = Path("upstream/manifests")
    version = Path("upstream/version").read_text()

    def __init__(self, *args):
        super().__init__(*args)
        self.cloud_config = CloudConfigRequires(self)
        self.lk_helpers = LightKubeHelpers(self)
        self.framework.observe(self.on.install, self._install_or_upgrade)
        self.framework.observe(self.on.upgrade_charm, self._install_or_upgrade)
        self.framework.observe(self.on.cloud_config_relation_created, self._install_or_upgrade)
        self.framework.observe(self.cloud_config.on.ready, self._install_or_upgrade)
        self.framework.observe(self.on.leader_elected, self._set_version)
        self.framework.observe(self.on.stop, self._cleanup)

    def _install_or_upgrade(self, event):
        if not self.cloud_config.relations:
            self.unit.status = BlockedStatus("Missing cloud-config relation")
            return
        if not self.cloud_config.is_ready():
            self.unit.status = WaitingStatus("Waiting for cloud-config")
            return
        self.unit.status = MaintenanceStatus("Deploying Cinder CSI")
        for manifest in self.manifests.glob("**/*.yaml"):
            if "secret" in manifest.name:
                # The upstream secret contains dummy data, so skip it.
                continue
            self.lk_helpers.apply_manifest(manifest)
        self.lk_helpers.apply_resource(
            StorageClass,
            name="cinder",
            provisioner="cinder.csi.openstack.org",
            annotations={"juju.io/workload-storage": "true"},
        )
        self.unit.status = ActiveStatus()
        self._set_version()

    def _set_version(self, event=None):
        if self.unit.is_leader():
            self.unit.set_workload_version(self.version)

    def _cleanup(self, event):
        self.unit.status = MaintenanceStatus("Cleaning up Cinder CSI")
        for manifest in self.manifests.glob("**/*.yaml"):
            self.helpers.delete_manifest(manifest, ignore_unauthorized=True)
        self.lk_helpers.delete_resource(StorageClass, name="cinder")
        self.unit.status = WaitingStatus("Shutting down")


if __name__ == "__main__":
    main(CinderCSIOperatorCharm)
