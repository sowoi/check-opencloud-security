# Icinga Director
[Icinga Director](https://icinga.com/docs/icinga-director/latest/) manages
`CheckCommand`, `Service Template`, and `Service` objects through its web UI
instead of hand-written config files. The steps below work for either the
native install or the [Docker](installation.md#docker) image.

1. **Create the Command**
   - Navigate to *Icinga Director → Commands → Add*.
   - **Command name:** `check_opencloud_security`
   - **Command:**
     - Native install: `/usr/lib/nagios/plugins/check-opencloud-security` (wherever you installed/symlinked it, see [Installation](../README.md#installation)).
     - Docker: `/usr/bin/docker` (see the [Docker CheckCommand](installation.md#using-the-docker-image-instead) example for the required fixed arguments `run`, `--rm`, and the image name).
   - **Command type:** *Plugin Check Command*.

2. **Add the arguments** on the same Command object (*Fields* tab → *Add argument*):

   | Argument     | Value                       | Description                        |
   |:-------------|:----------------------------|:------------------------------------|
   | `--host`     | `$address$` (or a custom Director Data Field, e.g. `$opencloud_host$`) | OpenCloud hostname, IP or URL, required |
   | `--port`     | Data Field `$opencloud_port$`, optional | Port, e.g. `9200` |
   | `--insecure` | Set-if Data Field `$opencloud_insecure$` (boolean), optional | Self-signed instance |
   | `--proxy`    | Data Field `$opencloud_proxy$`, optional | HTTP/HTTPS proxy |
   | `--debug`    | Set-if Data Field `$opencloud_debug$` (boolean), optional | Verbose debug output |

   For each optional argument, tick *Skip this argument on empty value* so
   Director omits the flag entirely when the field isn't set.

3. **Expose the fields to services** by defining matching *Data Fields* under
   the Command (*Fields* tab → *Add data field*), e.g. `opencloud_host`,
   `opencloud_port`, `opencloud_insecure`, `opencloud_debug` - then set their
   *Data Type* (`String` or `Boolean`) and *Var Filter* as needed.

4. **Create a Service Template**
   - *Icinga Director → Service Templates → Add*.
   - **Check command:** `check_opencloud_security`.
   - **Check interval:** `24h` is a good default; see the note under
     [Icinga2 / Nagios](installation.md#icinga2--nagios) before going much lower.
   - Leave the Data Fields empty here so they can be filled in per service/host.

5. **Apply it to a host or host group**
   - *Icinga Director → Services → Add* (or a *Service Apply Rule* for a whole host group).
   - Import the Service Template created above.
   - Fill in `opencloud_host` (or rely on `$address$` if you didn't override it) and any optional fields.
   - Deploy the configuration from *Icinga Director → Deployments*.

Once deployed, Icinga2 invokes the command exactly as described in the
[Icinga2 / Nagios](installation.md#icinga2--nagios) section, whether that resolves
to the native binary or `docker run` under the hood.

To deploy the same objects without the web UI, see
[Automated deployment with Ansible](ansible.md).

---

[Back to the documentation index](README.md) | [Back to the main README](../README.md)
