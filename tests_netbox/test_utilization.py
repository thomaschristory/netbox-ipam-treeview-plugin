from django.test import TestCase
from ipam.models import RIR, VRF, Aggregate, IPAddress, IPRange, Prefix
from netaddr import IPNetwork as N

from netbox_ipam_treeview.tree.nodes import ALL_VRFS
from netbox_ipam_treeview.utilization import bulk_aggregate_utilization, bulk_utilization


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


class AggregateUtilizationTest(TestCase):
    def setUp(self):
        rir = RIR.objects.create(name="R", slug="r", is_private=True)
        self.red = VRF.objects.create(name="RED")
        self.agg = Aggregate.objects.create(prefix="10.0.0.0/8", rir=rir)
        self.agg2 = Aggregate.objects.create(prefix="192.168.0.0/16", rir=rir)
        self.agg6 = Aggregate.objects.create(prefix="fd00::/8", rir=rir)
        for agg in (self.agg, self.agg2, self.agg6):
            agg.refresh_from_db()  # prefix as IPNetwork, as loaded by the tree
        Prefix.objects.create(prefix="10.1.0.0/16", status="container")
        Prefix.objects.create(prefix="10.1.0.0/24")  # nested: counted once
        Prefix.objects.create(prefix="10.1.0.0/16", vrf=self.red)
        Prefix.objects.create(prefix="10.2.0.0/15", vrf=self.red)
        Prefix.objects.create(prefix="192.168.0.0/16")  # equal to the aggregate: counted, like NetBox
        Prefix.objects.create(prefix="192.168.0.0/17", vrf=self.red)
        Prefix.objects.create(prefix="172.16.0.0/12")  # outside every aggregate

    def test_per_vrf_utilization(self):
        result = bulk_aggregate_utilization([(self.agg, None), (self.agg, self.red.pk), (self.agg2, self.red.pk)])
        self.assertAlmostEqual(result[(self.agg.pk, None)], 1 / 256 * 100)
        self.assertAlmostEqual(result[(self.agg.pk, self.red.pk)], 3 / 256 * 100)
        self.assertAlmostEqual(result[(self.agg2.pk, self.red.pk)], 50.0)

    def test_all_vrfs_matches_netbox_get_utilization(self):
        aggregates = (self.agg, self.agg2, self.agg6)
        result = bulk_aggregate_utilization([(a, ALL_VRFS) for a in aggregates])
        for agg in aggregates:
            with self.subTest(aggregate=str(agg.prefix)):
                self.assertAlmostEqual(result[(agg.pk, ALL_VRFS)], agg.get_utilization(), places=6)

    def test_empty(self):
        with self.assertNumQueries(0):
            self.assertEqual(bulk_aggregate_utilization([]), {})

    def test_constant_query_count(self):
        pairs = [(a, v) for a in (self.agg, self.agg2, self.agg6) for v in (None, self.red.pk, ALL_VRFS)]
        with self.assertNumQueries(1):
            bulk_aggregate_utilization(pairs)
