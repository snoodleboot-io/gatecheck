"""gatecheck — a modern pre-commit replacement."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("gatecheck")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
