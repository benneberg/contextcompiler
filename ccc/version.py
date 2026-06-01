try:
    from importlib.metadata import version, PackageNotFoundError
    VERSION = version("ccc-contextcompiler")
except (ImportError, Exception):
    VERSION = "0.1.0"