from django.apps import apps
from django.test import SimpleTestCase
from netbox.plugins import PluginConfig

import netbox_ipam_treeview


class PackageTest(SimpleTestCase):
    def test_config_is_the_installed_plugin_config(self):
        self.assertTrue(issubclass(netbox_ipam_treeview.config, PluginConfig))
        self.assertIsInstance(apps.get_app_config("netbox_ipam_treeview"), netbox_ipam_treeview.config)
