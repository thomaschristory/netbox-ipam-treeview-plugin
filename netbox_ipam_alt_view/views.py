from django.conf import settings
from django.contrib.auth.mixins import AccessMixin
from django.http import HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from ipam.filtersets import PrefixFilterSet
from ipam.forms import PrefixFilterForm
from ipam.models import Prefix

from .columns import COLUMNS, USER_CONFIG_PATH, resolve_columns
from .conf import get_setting
from .tree.builder import NodeNotFound, TreeBuilder

# Query parameters that belong to the tree itself, not to the prefix filterset.
OWN_PARAMS = {"free", "key", "level", "keys"}


def _free(request):
    raw = request.GET.get("free")
    return get_setting("show_free_space") if raw is None else raw == "1"


def _level(request):
    try:
        return max(0, min(int(request.GET.get("level", 0)), 128))
    except ValueError:
        return 0


def table_context(request, builder, nodes, **extra):
    """Context shared by the tree page, fragment responses and detail tabs."""
    columns = resolve_columns(request.user)
    return {
        "nodes": nodes,
        "columns": columns,
        "column_headers": [(c, COLUMNS[c]) for c in columns],
        "all_columns": COLUMNS,
        "tree_perms": {a: request.user.has_perm(f"ipam.{a}_prefix") for a in ("add", "change", "delete")},
        "free": builder.show_free_space,
        "filtered": False,
        "truncated": builder.truncated,
        "limit": builder.limit,
        # Fragments are fetched from the tree page; links in them should return there, not to the fragment URL.
        "return_url": request.headers.get("X-Tree-Page") or request.get_full_path(),
        **extra,
    }


class TreeAccessMixin(AccessMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated and settings.LOGIN_REQUIRED:
            return self.handle_no_permission()
        if not request.user.has_perm("ipam.view_prefix"):
            return HttpResponseForbidden() if request.user.is_authenticated else self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)

    def builder(self, request):
        return TreeBuilder(request.user, show_free_space=_free(request))

    def rows(self, request, builder, nodes):
        response = render(request, "netbox_ipam_alt_view/inc/rows.html", table_context(request, builder, nodes))
        if builder.truncated:
            response["X-Tree-Truncated"] = "1"
        return response

    def not_found(self, request):
        return render(request, "netbox_ipam_alt_view/inc/rows.html", {"error": True}, status=404)


class TreeView(TreeAccessMixin, View):
    def get(self, request):
        builder = self.builder(request)
        filter_params = {k for k, v in request.GET.lists() if k not in OWN_PARAMS and any(v)}
        filterset = PrefixFilterSet(request.GET, queryset=builder.prefixes)
        filtered = bool(filter_params) and filterset.is_valid()
        nodes = builder.filtered(filterset.qs) if filtered else builder.roots()
        context = table_context(
            request,
            builder,
            nodes,
            filtered=filtered,
            filter_form=PrefixFilterForm(request.GET, label_suffix=""),
            model=Prefix,
            list_querystring=request.GET.urlencode(),
            storage_key="ipam-tree:page",
            root_key="__root__",
        )
        return render(request, "netbox_ipam_alt_view/tree.html", context)


class NodeChildrenView(TreeAccessMixin, View):
    def get(self, request):
        builder = self.builder(request)
        try:
            nodes = builder.children(request.GET.get("key", ""), _level(request))
        except NodeNotFound:
            return self.not_found(request)
        return self.rows(request, builder, nodes)


class NodeSubtreeView(TreeAccessMixin, View):
    def get(self, request):
        builder = self.builder(request)
        key = request.GET.get("key", "")
        try:
            nodes = builder.full_tree() if key == "__root__" else builder.subtree(key, _level(request))
        except NodeNotFound:
            return self.not_found(request)
        return self.rows(request, builder, nodes)


class ExpandView(TreeAccessMixin, View):
    def get(self, request):
        builder = self.builder(request)
        keys = {k for k in request.GET.get("keys", "").split(",") if k}
        return self.rows(request, builder, builder.expand(keys))


class ColumnsView(TreeAccessMixin, View):
    def post(self, request):
        columns = [c for c in request.POST.getlist("columns") if c in COLUMNS]
        request.user.config.set(USER_CONFIG_PATH, columns or None, commit=True)
        next_url = request.POST.get("next", "")
        if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
            next_url = reverse("plugins:netbox_ipam_alt_view:tree")
        return HttpResponseRedirect(next_url)
