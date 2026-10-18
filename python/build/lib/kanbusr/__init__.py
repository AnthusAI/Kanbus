"""
Compatibility shim for the renamed Python package.

`kanbusr` mirrors `kanbus` to keep imports working while the distribution
name on PyPI is now `kanbusr`.
"""

from kanbus import *  # noqa: F401,F403
from kanbus import __version__  # noqa: F401

__all__ = [name for name in globals() if not name.startswith("_")]
