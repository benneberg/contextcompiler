"""CCC — Code Context Compiler."""
from .version import VERSION
import importlib.metadata

try:
    __version__ = importlib.metadata.version("ccc_contextcompiler") # Use your actual package name here
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0-dev"
