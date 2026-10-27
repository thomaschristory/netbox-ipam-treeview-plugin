# Installation

## Requirements

- NetBox 4.7.2 or later 4.7.x release.
- Python 3.12 to 3.14 (whatever NetBox itself uses).

The package has no runtime dependency of its own beyond NetBox.

### Compatibility

NetBox refuses to load the plugin outside the `min_version` / `max_version` range of the release.

| Plugin release | Min NetBox | Max NetBox | Tested in CI |
|---|---|---|---|
| next release | 4.7.2 | 4.7.99 | 4.7.2 |
| 0.1.1 | 4.7.0 | 4.7.99 | 4.7.2 |
| 0.1.0 | 4.7.0 | 4.7.99 | 4.7.2 |

4.7.2 is the minimum because NetBox 4.7.0 and 4.7.1 recorded plaintext API tokens created through background bulk
requests in job results. Upgrade NetBox first if you run one of them.

## Bare metal

Install the package into NetBox's virtual environment:

```shell
source /opt/netbox/venv/bin/activate
pip install netbox-ipam-treeview-plugin
```

To keep it across NetBox upgrades, add it to `/opt/netbox/local_requirements.txt`:

```text
netbox-ipam-treeview-plugin
```

Enable it in `configuration.py`:

```python
PLUGINS = ["netbox_ipam_treeview"]
```

The plugin ships static files (JavaScript and CSS), so collect them, then restart NetBox:

```shell
python /opt/netbox/netbox/manage.py collectstatic --no-input
sudo systemctl restart netbox
```

There is no migration to run. NetBox's own `upgrade.sh` runs `migrate` and `collectstatic` anyway.

## netbox-docker

netbox-docker images do not include plugins; build a custom image on top of the upstream one. The venv inside the image has no `pip`, only `uv`:

```dockerfile
FROM netboxcommunity/netbox:v4.7.2
COPY ./plugin_requirements.txt /opt/netbox/
RUN /usr/local/bin/uv pip install -r /opt/netbox/plugin_requirements.txt
RUN DEBUG="true" SECRET_KEY="dummydummydummydummydummydummydummydummydummydummy" \
    /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py collectstatic --no-input
```

with `plugin_requirements.txt` containing:

```text
netbox-ipam-treeview-plugin
```

Put `PLUGINS` (and `PLUGINS_CONFIG`, if any) in a file such as `/etc/netbox/config/plugins.py`; netbox-docker loads every `*.py` file in `/etc/netbox/config/`.

## Checking the install

After the restart:

- The navigation has an *IPAM Tree* menu with a *Prefix Tree* entry (or, with `menu_location = "ipam"`, the entry is
  right below *IPAM → Prefixes*).
- `/plugins/ipam-tree/` shows the tree.
- Prefix, Aggregate and VRF pages have a *Tree* tab.

If the page renders without styling or the carets do nothing, the static files were not collected.
