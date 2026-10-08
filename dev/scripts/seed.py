"""Dev-only seed: realistic RFC1918/ULA hierarchy. Run via `make seed` (SEED_SCALE, SEED_RESET env vars)."""

import io
import os
import random

import netaddr
from dcim.models import Region, Site
from django.core.management import call_command
from django.db import transaction
from ipam.choices import PrefixStatusChoices as S
from ipam.models import RIR, VLAN, VRF, Aggregate, Prefix, Role
from tenancy.models import Tenant

rng = random.Random(1918)
SCALE = int(os.environ.get("SEED_SCALE", "1"))
RESET = os.environ.get("SEED_RESET") == "1"

if RESET:
    Prefix.objects.all().delete()
    VLAN.objects.all().delete()
    Aggregate.objects.all().delete()
    VRF.objects.all().delete()
    Site.objects.filter(slug__startswith="seed-").delete()
    Region.objects.filter(slug__startswith="seed-").delete()

if Aggregate.objects.filter(prefix="10.0.0.0/8").exists():
    print("Already seeded (use `make reseed` to wipe and reseed).")
else:
    with transaction.atomic():
        rir, _ = RIR.objects.get_or_create(name="RFC1918", slug="rfc1918", defaults={"is_private": True})
        ula, _ = RIR.objects.get_or_create(name="RFC4193", slug="rfc4193", defaults={"is_private": True})
        for net, r in (("10.0.0.0/8", rir), ("172.16.0.0/12", rir), ("192.168.0.0/16", rir), ("fd00::/8", ula)):
            Aggregate.objects.create(prefix=net, rir=r)

        roles = {}
        for name in ("Users", "Servers", "Voice", "Management", "IoT", "Point-to-point", "DMZ", "Infrastructure"):
            roles[name], _ = Role.objects.get_or_create(name=name, slug=name.lower().replace(" ", "-"))
        tenants = [
            Tenant.objects.get_or_create(name=n, slug=n.lower())[0]
            for n in ("Engineering", "Finance", "Operations", "Retail", "Research")
        ]
        vrfs = {
            "CORP": VRF.objects.create(name="CORP", rd="65000:100"),
            "DMZ": VRF.objects.create(name="DMZ", rd="65000:200"),
            "LAB": VRF.objects.create(name="LAB", rd="65000:300", enforce_unique=False),
        }

        regions = []
        for rname in ("EMEA", "AMER", "APAC", "LATAM", "ANZ"):
            region = Region(name=f"Seed {rname}", slug=f"seed-{rname.lower()}")
            region.save()
            regions.append(region)

        n_sites = 40 * SCALE
        sites = []
        for i in range(n_sites):
            site = Site(name=f"Site {i + 1:03d}", slug=f"seed-site-{i + 1:03d}", region=regions[i % len(regions)])
            site.save()
            sites.append(site)

        prefixes, vlans = [], []

        def status():
            r = rng.random()
            return S.STATUS_RESERVED if r < 0.05 else S.STATUS_DEPRECATED if r < 0.08 else S.STATUS_ACTIVE

        def add(net, *, vrf=None, site=None, st=None, role=None, tenant=None, vlan=None, desc="", **kw):
            p = Prefix(
                prefix=str(net),
                vrf=vrf,
                status=st or status(),
                role=role,
                tenant=tenant,
                vlan=vlan,
                description=desc,
                **kw,
            )
            if site is not None:
                p.scope = site
                p.cache_related_objects()
            prefixes.append(p)
            return p

        # 10.0.0.0/8: one /16 per site (/18 above 250 sites), carved per function; 10.0/16 is left to LAB.
        site_blocks = list(netaddr.IPNetwork("10.0.0.0/8").subnet(16 if n_sites < 250 else 18))
        functions = [("Users", 0), ("Servers", 1), ("Voice", 2), ("Management", 3), ("IoT", 4)]
        for site, block in zip(sites, site_blocks[1:], strict=False):
            tenant = rng.choice(tenants)
            add(block, site=site, st=S.STATUS_CONTAINER, role=roles["Infrastructure"], desc=f"{site.name} supernet")
            subs20 = list(block.subnet(block.prefixlen + 4))
            for fname, idx in functions:
                p20 = subs20[idx]
                add(
                    p20, site=site, st=S.STATUS_CONTAINER, role=roles[fname], tenant=tenant, desc=f"{site.name} {fname}"
                )
                for j, p24 in enumerate(p20.subnet(24)):
                    if rng.random() < 0.35:  # leave free space
                        continue
                    vid = 100 + idx * 100 + j
                    vlan = VLAN(vid=vid, name=f"{fname[:4].upper()}-{vid}", status="active", tenant=tenant)
                    vlans.append(vlan)
                    if fname == "Servers" and rng.random() < 0.5:
                        add(p24, site=site, st=S.STATUS_CONTAINER, role=roles[fname], tenant=tenant, vlan=vlan)
                        for p26 in list(p24.subnet(26))[: rng.randint(1, 4)]:
                            add(p26, site=site, role=roles[fname], tenant=tenant, desc="server segment")
                    elif fname == "Management" and j == 0:
                        add(p24, site=site, st=S.STATUS_CONTAINER, role=roles["Point-to-point"], desc="p2p links")
                        for p30 in list(p24.subnet(30))[:16]:
                            add(p30, site=site, role=roles["Point-to-point"], desc="p2p")
                    else:
                        add(
                            p24,
                            site=site,
                            role=roles[fname],
                            tenant=tenant,
                            vlan=vlan,
                            is_pool=(fname == "Management"),
                            desc=f"{fname} VLAN {vid}",
                        )

        # 172.16.0.0/12: datacenters, heavy /22 > /24 > /27 nesting.
        for d in range(min(6 * SCALE, 16)):
            dc = netaddr.IPNetwork(f"172.{16 + d}.0.0/16")
            site = sites[d]
            add(dc, site=site, st=S.STATUS_CONTAINER, role=roles["Servers"], desc=f"DC{d + 1}")
            for p22 in list(dc.subnet(22))[:48]:
                add(p22, site=site, st=S.STATUS_CONTAINER, role=roles["Servers"])
                for p24 in p22.subnet(24):
                    if rng.random() < 0.2:
                        continue
                    container = rng.random() < 0.5
                    add(
                        p24,
                        site=site,
                        role=roles["Servers"],
                        tenant=rng.choice(tenants),
                        st=S.STATUS_CONTAINER if container else None,
                    )
                    if container:
                        for p27 in list(p24.subnet(27))[: rng.randint(2, 8)]:
                            add(p27, site=site, role=roles["Servers"])

        # 192.168.0.0/16: branch offices, a /24 each split into /26s.
        for b, p24 in enumerate(list(netaddr.IPNetwork("192.168.0.0/16").subnet(24))[: 200 * SCALE]):
            site = sites[b % len(sites)]
            add(p24, site=site, st=S.STATUS_CONTAINER, role=roles["Users"], desc=f"Branch {b + 1}")
            for p26 in list(p24.subnet(26))[: rng.randint(2, 4)]:
                add(p26, site=site, role=roles["Users"])

        # IPv6 ULA: fd00:<region>::/32 > /48 per site > a few /64s.
        for r_i, region in enumerate(regions):
            add(f"fd00:{r_i + 1:x}::/32", st=S.STATUS_CONTAINER, desc=f"{region.name} ULA")
            region_sites = [s for s in sites if s.region_id == region.pk][:8]
            for s_i, site in enumerate(region_sites):
                add(f"fd00:{r_i + 1:x}:{s_i + 1:x}::/48", site=site, st=S.STATUS_CONTAINER)
                for v in range(rng.randint(2, 6)):
                    add(f"fd00:{r_i + 1:x}:{s_i + 1:x}:{v + 1:x}::/64", site=site)

        # VRFs: CORP overlaps the 10.1-10.8 site blocks, DMZ lives in 172.31/16, LAB reuses 10.0/16.
        for k in range(1, 9):
            blk = netaddr.IPNetwork(f"10.{k}.0.0/16")
            add(blk, vrf=vrfs["CORP"], st=S.STATUS_CONTAINER, desc="CORP overlay")
            for p24 in list(blk.subnet(24))[:20]:
                add(p24, vrf=vrfs["CORP"], role=roles["Users"])
        dmz = netaddr.IPNetwork("172.31.0.0/16")
        add(dmz, vrf=vrfs["DMZ"], st=S.STATUS_CONTAINER, role=roles["DMZ"])
        for p24 in list(dmz.subnet(24))[:32]:
            add(p24, vrf=vrfs["DMZ"], role=roles["DMZ"])
            for p28 in list(p24.subnet(28))[: rng.randint(0, 4)]:
                add(p28, vrf=vrfs["DMZ"], role=roles["DMZ"])
        lab = netaddr.IPNetwork("10.0.0.0/16")
        add(lab, vrf=vrfs["LAB"], st=S.STATUS_CONTAINER, desc="Lab")
        for p24 in list(lab.subnet(24))[:64]:
            add(p24, vrf=vrfs["LAB"], role=roles["Infrastructure"])
        add("10.0.1.0/24", vrf=vrfs["LAB"], desc="duplicate on purpose")

        VLAN.objects.bulk_create(vlans, batch_size=2000)
        Prefix.objects.bulk_create(prefixes, batch_size=2000)

    call_command("rebuild_prefixes")
    call_command("reindex", "ipam", "dcim", "tenancy", stdout=io.StringIO())
    print(f"Seeded {Prefix.objects.count()} prefixes, {VLAN.objects.count()} VLANs, {len(sites)} sites.")
