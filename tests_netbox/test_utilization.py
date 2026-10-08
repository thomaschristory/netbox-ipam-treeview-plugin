from django.test import TestCase
from ipam.models import VRF, IPAddress, IPRange, Prefix
from netaddr import IPNetwork as N

from netbox_ipam_treeview.utilization import bulk_utilization


class BulkUtilizationTest(TestCase):
    def test_matches_netbox_get_utilization(self):
        red = VRF.objects.create(name="RED")
        prefixes = [
            Prefix.objects.create(prefix="10.0.0.0/16", status="container"),
            Prefix.objects.create(prefix="10.0.1.0/24"),
            Prefix.objects.create(prefix="10.0.2.0/24", is_pool=True),
            Prefix.objects.create(prefix="10.0.3.0/24", mark_utilized=True),
            Prefix.objects.create(prefix="10.0.4.0/30"),
            Prefix.objects.create(prefix="10.0.0.0/16", vrf=red, status="container"),
            Prefix.objects.create(prefix="10.0.1.0/24", vrf=red),
            Prefix.objects.create(prefix="fd00::/64"),
        ]
        for addr in ("10.0.1.1/24", "10.0.1.2/24", "10.0.1.2/24", "10.0.1.200/24", "10.0.2.9/24", "10.0.4.1/30"):
            IPAddress.objects.create(address=addr)
        IPAddress.objects.create(address="10.0.1.7/24", vrf=red)
        IPAddress.objects.create(address="fd00::5/64")
        IPRange.objects.create(start_address=N("10.0.1.192/24"), end_address=N("10.0.1.223/24"), mark_utilized=True)
        IPRange.objects.create(start_address=N("10.0.1.100/24"), end_address=N("10.0.1.110/24"))  # not utilized

        result = bulk_utilization(prefixes)
        for p in prefixes:
            p.refresh_from_db()
            with self.subTest(prefix=str(p.prefix), vrf=p.vrf_id):
                self.assertAlmostEqual(result[p.pk], p.get_utilization(), places=6)

    def test_constant_query_count(self):
        prefixes = [Prefix.objects.create(prefix=f"10.9.{i}.0/24") for i in range(20)]
        prefixes.append(Prefix.objects.create(prefix="10.9.0.0/16", status="container"))
        with self.assertNumQueries(3):  # one query each for container children, IPs and utilized ranges
            bulk_utilization(prefixes)
