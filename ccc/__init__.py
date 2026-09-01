"""CCC — Code Context Compiler."""
from .version import VERSION

try:
    from importlib.metadata import version as _pkg_version, PackageNotFoundError
    __version__ = _pkg_version("ccc-contextcompiler")
except (ImportError, Exception):
    __version__ = VERSION

__all__ = ["VERSION", "__version__"]
