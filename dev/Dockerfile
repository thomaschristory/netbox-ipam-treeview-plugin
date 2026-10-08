ARG NETBOX_IMAGE=docker.io/netboxcommunity/netbox:v4.7-5.1.1
FROM ${NETBOX_IMAGE}

USER root
COPY pyproject.toml README.md /plugin/
COPY netbox_ipam_treeview /plugin/netbox_ipam_treeview
# Editable install: the source directory is also bind-mounted by compose, so code edits apply on restart.
RUN /usr/local/bin/uv pip install --python /opt/netbox/venv/bin/python -e /plugin
