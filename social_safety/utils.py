"""Shared helpers for social_safety.

Single source of truth for what counts as a "sensitive" frontend path —
mirrored on the client side in CAMOUFLAGE_PATHS (quick_exit.js). Both
must stay in sync when sections are added/removed.
"""
import re

# Same prefix list as quick_exit.js CAMOUFLAGE_PATHS. Keep them aligned.
_SENSITIVE_PREFIXES = (
    'my',
    'profile',
    'safety',
    'discover',
    'members',
    'groups',
    'governance',
    'gallery',
    'stories',
    'onboarding',
    'messaging',
    'calls',
    'circles',
    'consent',
    'negotiation',
    'vouching',
    'reputation',
)

_SENSITIVE_RE = re.compile(
    r'^/(?:' + '|'.join(_SENSITIVE_PREFIXES) + r')(?:/|$)'
)


def is_sensitive_path(path):
    """Return True for portal/member-only paths.

    Matches the exact same set as the CAMOUFLAGE_PATHS regex in
    quick_exit.js: anything under /my/*, /profile/*, /safety, etc.
    Public pages (/, /shop, /event, /membership, /web/login…) return
    False — those must remain indexable + shareable for acquisition.
    """
    if not path:
        return False
    return bool(_SENSITIVE_RE.match(path))
