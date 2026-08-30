# Automated deployment with Ansible

Prefer not to click through Icinga Director or configure hosts by hand?
[`ansible/`](../ansible/README.md) contains ready-to-use playbooks that install
and configure check-opencloud-security - native or Docker - on one or more
Icinga2 hosts, including the `CheckCommand` and `Service` objects described in
[Icinga Director](icinga-director.md) and
[Icinga2 / Nagios](../README.md#icinga2--nagios).

This page is the short version. [`ansible/README.md`](../ansible/README.md) is
the reference, and it is the file kept in step with the roles themselves.

<!-- TOC -->
* [Automated deployment with Ansible](#automated-deployment-with-ansible)
  * [Which role to use](#which-role-to-use)
  * [Quick start](#quick-start)
  * [Configuring the check](#configuring-the-check)
  * [Before you commit a change to the role](#before-you-commit-a-change-to-the-role)
<!-- TOC -->


## Which role to use

| Role | Installs | Use it when |
|:-----|:---------|:------------|
| `opencloud_check_native` | The plugin into a dedicated virtualenv, symlinked into the Nagios plugin directory | The monitoring host has Python and you want the fewest moving parts |
| `opencloud_check_docker` | The image, built on the target host and invoked as `docker run` | You would rather not install Python packages on the monitoring host |

Both roles write the same Icinga2 objects, so a host can be moved from one to
the other without rewriting the service definition.

## Quick start

```shell
cd ansible
cp inventory.example.ini inventory.ini
$EDITOR inventory.ini   # the Icinga2 hosts, and opencloud_check_host per host

# Native (virtualenv) install:
ansible-playbook -i inventory.ini playbooks/deploy_native.yml

# ... or the Docker install:
ansible-galaxy collection install -r requirements.yml
ansible-playbook -i inventory.ini playbooks/deploy_docker.yml
```

The playbooks are idempotent, so re-running one is also how you upgrade: the
plugin version and the Icinga2 objects are both converged every time.

## Configuring the check

Every setting is an `opencloud_check_*` variable, mapping one-to-one onto the
`COS_*` environment variables and CLI flags in the
[options table](../README.md#options). A realistic host entry:

```ini
[icinga_hosts]
monitoring.example.com

[icinga_hosts:vars]
opencloud_check_host=opencloud.example.com
opencloud_check_port=9200
opencloud_check_check_hardening=true
opencloud_check_update_warning=true
opencloud_check_interval=24h
```

`opencloud_check_host` defaults to `inventory_hostname`, which is right when
the monitoring agent runs on the OpenCloud host itself and wrong in most other
cases - set it explicitly.

Leave `opencloud_check_interval` at `24h` or higher. Each run is a real scan
against a real instance rather than a cached lookup, and nothing about an
instance's rating changes from minute to minute.

The full variable table, including the ones specific to each role, is in
[`ansible/README.md`](../ansible/README.md#variable-reference).

## Before you commit a change to the role

`ansible-lint` is only clean when run from inside `ansible/`; from the
repository root it reports dozens of false positives.

```shell
cd ansible
ansible-lint
ansible-playbook -i inventory.ini playbooks/deploy_native.yml --syntax-check
```

---

[Back to the documentation index](README.md) | [Back to the main README](../README.md)
