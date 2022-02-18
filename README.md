# cinder-csi-operator

## Description

This Charmed Operator deploys and manages the Cinder CSI plugin component for
K8s on OpenStack.

## Usage

After deploying, this charm needs to be related to the OpenStack Cloud Controller
Operator to be notified when the `cloud-config` secret is available.

```
juju relation cinder-csi-operator openstack-cloud-controller-operator
```

## OCI Images

The base image for this operator can be provided with `--resource operator-base=ubuntu:focal`.

## Contributing

Please see the [Juju SDK docs](https://juju.is/docs/sdk) for guidelines on
enhancements to this charm following best practice guidelines, and
[CONTRIBUTING.md](https://github.com/canonical/cinder-csi-operator/blob/main/CONTRIBUTING.md)
for developer guidance.
