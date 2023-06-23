# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
"""Implementation of openstack integrator interface.

This only implements the requires side, currently, since the providers
is still using the Reactive Charm framework self.
"""
import base64
import binascii
import configparser
import contextlib
import io
import json
import logging
import random
import string
from typing import Optional

from backports.cached_property import cached_property
from ops.charm import RelationBrokenEvent
from ops.framework import Object
from pydantic import BaseModel, Json, SecretStr, ValidationError, validator

log = logging.getLogger(__name__)


class Data(BaseModel):
    """Databag for information shared over the relation."""

    auth_url: Json[str]
    bs_version: Json[Optional[str]]
    endpoint_tls_ca: Json[Optional[str]]
    floating_network_id: Json[str]
    has_octavia: Json[bool]
    ignore_volume_az: Json[Optional[bool]]
    internal_lb: Json[bool]
    lb_enabled: Json[bool]
    lb_method: Json[str]
    manage_security_groups: Json[bool]
    password: Json[SecretStr]
    project_domain_name: Json[str]
    project_name: Json[str]
    region: Json[str]
    subnet_id: Json[str]
    trust_device_path: Json[Optional[bool]]
    user_domain_name: Json[str]
    username: Json[str]
    version: Json[Optional[int]]

    @validator("endpoint_tls_ca")
    def must_be_b64_cert(cls, s: Json[str]):
        """Validate endpoint_tls_ca is base64 encoded str."""
        try:
            base64.b64decode(s, validate=True)
        except binascii.Error:
            raise ValueError("Couldn't find base64 data")
        return s


class OpenstackRequires(Object):
    """Requires side of openstack relation."""

    def __init__(self, charm, endpoint="openstack"):
        super().__init__(charm, f"relation-{endpoint}")
        self.endpoint = endpoint
        events = charm.on[endpoint]
        self._unit_name = self.model.unit.name.replace("/", "_")
        self.framework.observe(events.relation_joined, self._joined)

    def _joined(self, event):
        to_publish = self.relation.data[self.model.unit]
        to_publish["charm"] = self.model.app.name

    @cached_property
    def relation(self):
        """The relation to the integrator, or None."""
        return self.model.get_relation(self.endpoint)

    @cached_property
    def _raw_data(self):
        if self.relation and self.relation.units:
            return self.relation.data[list(self.relation.units)[0]]
        return None

    @cached_property
    def _data(self) -> Optional[Data]:
        raw = self._raw_data
        return Data(**raw) if raw else None

    def evaluate_relation(self, event) -> Optional[str]:
        """Determine if relation is ready."""
        no_relation = not self.relation or (
            isinstance(event, RelationBrokenEvent) and event.relation is self.relation
        )
        if not self.is_ready:
            if no_relation:
                return f"Missing required {self.endpoint}"
            return f"Waiting for {self.endpoint}"
        return None

    @property
    def is_ready(self):
        """Whether the request for this instance has been completed."""
        try:
            self._data
        except ValidationError as ve:
            log.error(f"{self.endpoint} relation data not yet valid. ({ve}")
            return False
        if self._data is None:
            log.error(f"{self.endpoint} relation data not yet available.")
            return False
        return all(
            field is not None
            for field in [
                self._data.auth_url,
                self._data.username,
                self._data.password,
                self._data.user_domain_name,
                self._data.project_domain_name,
                self._data.project_name,
            ]
        )

    def _request(self, keyvals):
        alphabet = string.ascii_letters + string.digits
        nonce = "".join(random.choice(alphabet) for _ in range(8))
        to_publish = self.relation.data[self.model.unit]
        to_publish.update({k: json.dumps(v) for k, v in keyvals.items()})
        to_publish["requested"] = nonce

    @property
    def cloud_conf(self) -> Optional[bytes]:  # noqa: C901
        """Return cloud.conf from integrator relation."""
        if not self.is_ready:
            return None

        config = configparser.ConfigParser()
        config["Global"] = {
            "auth-url": self._data.auth_url,
            "region": self._data.region,
            "username": self._data.username,
            "password": self._data.password.get_secret_value(),
            "tenant-name": self._data.project_name,
            "domain-name": self._data.user_domain_name,
            "tenant-domain-name": self._data.project_domain_name,
        }
        if self.endpoint_tls_ca:
            config["Global"]["ca-file"] = "/etc/config/endpoint-ca.cert"

        config["LoadBalancer"] = {}
        if not self._data.lb_enabled:
            config["LoadBalancer"]["enabled"] = "false"
        if self._data.has_octavia in (True, None):
            config["LoadBalancer"]["use-octavia"] = "true"
        else:
            config["LoadBalancer"]["use-octavia"] = "false"
            config["LoadBalancer"]["lb-provider"] = "true"
        if v := self._data.subnet_id:
            config["LoadBalancer"]["subnet-id"] = v
        if v := self._data.floating_network_id:
            config["LoadBalancer"]["floating-network-id"] = v
        if v := self._data.lb_method:
            config["LoadBalancer"]["lb-method"] = v
        if v := self._data.internal_lb:
            config["LoadBalancer"]["internal-lb"] = v
        if v := self._data.manage_security_groups:
            config["LoadBalancer"]["manage-security-groups"] = v

        config["BlockStorage"] = {}
        if v := self._data.bs_version:
            config["BlockStorage"]["bs-version"] = v
        if self._data.trust_device_path:
            config["BlockStorage"]["trust-device-path"] = "true"
        if self._data.ignore_volume_az:
            config["BlockStorage"]["ignore-volume-az"] = "true"

        with contextlib.closing(io.StringIO()) as sio:
            config.write(sio)
            output_text = sio.getvalue()

        return base64.b64encode(output_text.encode())

    @property
    def endpoint_tls_ca(self) -> Optional[bytes]:
        """Return cloud.conf from integrator relation."""
        if not self.is_ready:
            return None

        return self._data.endpoint_tls_ca.encode()
