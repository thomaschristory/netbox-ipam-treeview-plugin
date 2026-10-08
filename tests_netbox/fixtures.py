from django.contrib.auth import get_user_model
from ipam.models import RIR, VRF, Aggregate, Prefix


def make_tree():
    """Global: agg 10/8 > 10.1/16 > 10.1.1/24 > 10.1.1.0/26 ; orphan 192.0.2.0/24 ; VRF RED: 10.1/16 > 10.1.9/24."""
    rir = RIR.objects.create(name="R", slug="r", is_private=True)
    agg = Aggregate.objects.create(prefix="10.0.0.0/8", rir=rir)
    red = VRF.objects.create(name="RED")
    p16 = Prefix.objects.create(prefix="10.1.0.0/16", status="container")
    p24 = Prefix.objects.create(prefix="10.1.1.0/24")
    p26 = Prefix.objects.create(prefix="10.1.1.0/26")
    orphan = Prefix.objects.create(prefix="192.0.2.0/24")
    r16 = Prefix.objects.create(prefix="10.1.0.0/16", vrf=red, status="container")
    r24 = Prefix.objects.create(prefix="10.1.9.0/24", vrf=red)
    for p in (p16, p24, p26, orphan, r16, r24):
        p.refresh_from_db()
    return dict(agg=agg, red=red, p16=p16, p24=p24, p26=p26, orphan=orphan, r16=r16, r24=r24)


def superuser():
    return get_user_model().objects.create_user("admin-t", is_superuser=True)
