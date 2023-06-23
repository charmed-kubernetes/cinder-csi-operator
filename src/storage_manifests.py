# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
"""Implementation of cinder-csi specific details of the kubernetes manifests."""

import logging
import pickle
from hashlib import md5
from typing import Dict, Optional

from lightkube.codecs import AnyResource, from_dict
from ops.manifests import Addition, ConfigRegistry, ManifestLabel, Manifests

log = logging.getLogger(__file__)
NAMESPACE = "gce-pd-csi-driver"
SECRET_NAME = "cloud-sa"
STORAGE_CLASS_NAME = "csi-cinder-{type}"


class CreateSecret(Addition):
    """Create secret for the deployment.

    a secret named cloud-config in the kube-system namespace
    cloud.conf -- base64 encoded contents of cloud.conf
    endpoint-ca.cert -- base64 encoded ca cert for the auth-url
    """

    CONFIG_TO_SECRET = {"cloud-conf": "cloud.conf", "endpoint-ca-cert": "endpoint-ca.cert"}

    def __call__(self) -> Optional[AnyResource]:
        """Craft the secrets object for the deployment."""
        secret_config = {
            new_k: self.manifests.config.get(k) for k, new_k in self.CONFIG_TO_SECRET.items()
        }
        if any(s is None for s in secret_config.values()):
            log.error("secret data item is None")
            return None

        log.info("Encode secret data for storage.")
        return from_dict(
            dict(
                apiVersion="v1",
                kind="Secret",
                type="Opaque",
                metadata=dict(name="cloud-config", namespace="kube-system"),
                data=secret_config,
            )
        )


class CreateStorageClass(Addition):
    """Create cinder storage class."""

    def __init__(self, manifests: "Manifests", sc_type: str):
        super().__init__(manifests)
        self.type = sc_type

    def __call__(self) -> Optional[AnyResource]:
        """Craft the storage class object."""
        storage_name = STORAGE_CLASS_NAME.format(type=self.type)
        log.info(f"Creating storage class {storage_name}")
        sc = from_dict(
            dict(
                apiVersion="storage.k8s.io/v1",
                kind="StorageClass",
                metadata=dict(name=storage_name),
                provisioner="cinder.csi.openstack.org",
                reclaimPolicy="Delete",
                volumeBindingMode="WaitForFirstConsumer",
            )
        )

        if az := self.manifests.config.get("availability-zone"):
            sc.parameters.availability = az
        return sc


class StorageManifests(Manifests):
    """Deployment Specific details for the cinder-csi-driver."""

    def __init__(self, charm, charm_config, kube_control, integrator):
        super().__init__(
            "cinder-csi-driver",
            charm.model,
            "upstream/cloud_storage",
            [
                CreateSecret(self),
                ManifestLabel(self),
                ConfigRegistry(self),
                CreateStorageClass(self, "default"),  # creates csi-cinder-default
            ],
        )
        self.integrator = integrator
        self.charm_config = charm_config
        self.kube_control = kube_control

    @property
    def config(self) -> Dict:
        """Returns current config available from charm config and joined relations."""
        config: Dict = {}

        if self.kube_control.is_ready:
            config["image-registry"] = self.kube_control.get_registry_location()

        if self.integrator.is_ready:
            config["cloud-conf"] = self.integrator.cloud_conf.decode()
            config["endpoint-ca-cert"] = self.integrator.endpoint_tls_ca.decode()

        config.update(**self.charm_config.available_data)

        for key, value in dict(**config).items():
            if value == "" or value is None:
                del config[key]

        config["release"] = config.pop("storage-release", None)
        return config

    def hash(self) -> int:
        """Calculate a hash of the current configuration."""
        return int(md5(pickle.dumps(self.config)).hexdigest(), 16)

    def evaluate(self) -> Optional[str]:
        """Determine if manifest_config can be applied to manifests."""
        props = CreateSecret.CONFIG_TO_SECRET.keys()
        for prop in props:
            value = self.config.get(prop)
            if not value:
                return f"Storage manifests waiting for definition of {prop}"
        return None
