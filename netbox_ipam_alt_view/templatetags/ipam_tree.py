"""Fast object links for large trees: each view's URL pattern is reversed once, then formatted per object.

Django's reverse() costs ~0.1 ms; an expanded tree renders tens of thousands of links.
"""

from functools import lru_cache

from django import template
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()

_SENTINEL = 2147483647


@lru_cache(maxsize=256)
def _pattern(viewname):
    return reverse(viewname, kwargs={"pk": _SENTINEL}).replace(str(_SENTINEL), "{pk}")


@register.simple_tag
def obj_url(obj, action=""):
    """URL of NetBox's standard object view, e.g. ipam:prefix or ipam:prefix_edit."""
    meta = obj._meta
    viewname = f"{meta.app_label}:{meta.model_name}" + (f"_{action}" if action else "")
    return _pattern(viewname).format(pk=obj.pk)


@register.filter
def obj_link(obj):
    """Like NetBox's `linkify|placeholder` for objects with standard detail views."""
    if obj is None:
        return mark_safe('<span class="text-muted">&mdash;</span>')
    return format_html('<a href="{}">{}</a>', obj_url(obj), str(obj))


@register.filter
def util_bar(utilization):
    """Compact equivalent of NetBox's utilization_graph inclusion tag (same classes and thresholds)."""
    if utilization is None:
        return ""
    value = float(utilization)
    if value >= 100:
        bar_class = "bg-secondary"
    elif value >= 90:
        bar_class = "bg-danger"
    elif value >= 75:
        bar_class = "bg-warning"
    else:
        bar_class = "bg-success"
    label = f"{value:.1f}%"
    inside, outside = (label, "") if value >= 35 else ("", format_html('<span class="progress-label">{}</span>', label))
    return format_html(
        '<div class="progress"><div role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="{}" '
        'aria-label="Utilization: {}" class="progress-bar {}" style="width: {}%">{}</div>{}</div>',
        value,
        label,
        bar_class,
        value,
        inside,
        outside,
    )
