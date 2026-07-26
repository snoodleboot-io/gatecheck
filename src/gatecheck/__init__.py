"""gatecheck — a modern pre-commit replacement."""

from importlib.metadata import PackageNotFoundError, version

try:
    # Installed metadata carries the version injected at build time.
    __version__ = version("gatecheck")
except PackageNotFoundError:
    # Editable/source checkout with no built metadata: fall back to the placeholder
    # that CI rewrites at release time.
    from gatecheck.__about__ import __version__

__all__ = ["__version__"]
