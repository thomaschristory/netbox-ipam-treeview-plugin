import pytest

from netbox_ipam_treeview.conf import free_preference


@pytest.mark.parametrize(
    ("query", "cookie", "default", "expected"),
    [
        (None, None, True, True),
        (None, None, False, False),
        (None, "0", True, False),
        (None, "1", False, True),
        ("1", "0", False, True),  # the URL wins over the remembered choice
        ("0", "1", True, False),
        ("yes", "1", True, False),  # any other URL value means off, as before
        (None, "garbage", True, True),  # an unreadable cookie falls back to the setting
        (None, "", False, False),
    ],
)
def test_free_preference(query, cookie, default, expected):
    assert free_preference(query, cookie, default) is expected
