"""Filesystem path-confinement helpers.

A single, well-understood barrier against path-traversal / path-injection:
resolve both the intended base directory and the candidate target with
``os.path.realpath`` (which collapses ``..`` and follows symlinks), then assert
the resolved target is the base itself or lives *inside* it.

Use ``safe_join`` wherever a user/request-controlled value is combined into a
filesystem path. It preserves every legitimate name (plain basenames, nested
relative names that stay inside the base) and only rejects values that would
escape the base (``..`` climbs, absolute paths, symlink escapes).
"""

import os


def is_within(base_dir: str, target: str) -> bool:
    """True iff ``target`` (already-resolved-or-not) stays inside ``base_dir``.

    Both arguments are passed through ``os.path.realpath`` so the comparison is
    on canonical paths (handles ``..``, symlinks, and trailing-slash quirks).
    """
    base = os.path.realpath(base_dir)
    resolved = os.path.realpath(target)
    return resolved == base or resolved.startswith(base + os.sep)


def safe_join(base_dir: str, *user_parts: str) -> str:
    """Join ``user_parts`` onto ``base_dir`` and confine the result to it.

    Returns the resolved absolute path on success. Raises ``ValueError`` if the
    joined path escapes ``base_dir`` (via ``..``, an absolute component, or a
    symlink pointing outside).

    This is the sanitizer barrier: any value flowing through here is guaranteed
    to resolve inside ``base_dir`` before it is opened / written / removed.
    """
    base = os.path.realpath(base_dir)
    target = os.path.realpath(os.path.join(base, *user_parts))
    if target != base and not target.startswith(base + os.sep):
        raise ValueError("unsafe path: escapes the allowed base directory")
    return target
