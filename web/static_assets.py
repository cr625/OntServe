"""Content versions for static asset URLs.

nginx serves /static/ with a 7-day max-age and Cloudflare keeps that copy at its
edge, so a file changed by a deploy reaches visitors only under a new URL. The
version is a short hash of the file content: an unchanged file keeps its URL
across deploys, a changed one gets a new one.
"""

import hashlib
import os
from functools import lru_cache


@lru_cache(maxsize=256)
def _digest(path: str, mtime_ns: int, size: int) -> str:
    with open(path, 'rb') as handle:
        return hashlib.sha256(handle.read()).hexdigest()[:10]


def asset_version(static_folder: str, filename: str) -> str | None:
    """Short content hash of a static file, or None when the file is absent.

    The cache key carries mtime and size, so an edited file gets a new hash
    without a restart.
    """
    path = os.path.join(static_folder, filename)
    try:
        stat = os.stat(path)
    except OSError:
        return None
    return _digest(path, stat.st_mtime_ns, stat.st_size)
