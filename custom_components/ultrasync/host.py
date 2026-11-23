"""Helpers for the panel host setting.

The host can carry a user name and password for basic authentication, as a
URL (http://user:password@panel) or without a scheme (user:password@panel).
The requests library sends them in both forms. The entry title and the
reconfigure form are not treated as secrets, so they must not show them.
"""
from urllib.parse import urlparse


def _netloc(host: str) -> str:
    """Return the network location of the host, with any user information."""
    host = host.strip()
    return urlparse(host if "://" in host else f"//{host}").netloc


def host_title(host: str) -> str:
    """Return the host without its user name and password."""
    try:
        return _netloc(host).rpartition("@")[2] or host
    except ValueError:
        # Not a valid host; it can not be shown safely
        return "UltraSync"


def host_has_credentials(host: str) -> bool:
    """Return true if the host carries a user name or password."""
    try:
        return "@" in _netloc(host)
    except ValueError:
        return False
