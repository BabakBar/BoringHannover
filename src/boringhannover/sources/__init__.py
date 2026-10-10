"""Source registry: importing this package registers every source module."""

from __future__ import annotations

import importlib
import logging
import pkgutil
from pathlib import Path

from boringhannover.sources.base import (
    BaseSource,
    get_all_sources,
    register_source,
)


__all__ = [
    "BaseSource",
    "discover_sources",
    "get_all_sources",
    "register_source",
]

logger = logging.getLogger(__name__)


def discover_sources() -> int:
    """Auto-import all source modules to trigger registration.

    Scans subdirectories (cinema, concerts, festivals, sports) and imports
    all Python modules found, which triggers the @register_source decorator.

    Returns:
        Number of source modules discovered.
    """
    package_dir = Path(__file__).parent
    discovered = 0

    # Define subdirectories to scan for sources
    source_types = [
        "cinema",
        "concerts",
        "festivals",
        "sports",
    ]

    for subdir in source_types:
        subdir_path = package_dir / subdir
        if not subdir_path.exists():
            continue

        # Import all modules in the subdirectory
        for module_info in pkgutil.iter_modules([str(subdir_path)]):
            if module_info.name.startswith("_"):
                continue  # Skip private modules

            module_name = f"boringhannover.sources.{subdir}.{module_info.name}"
            try:
                importlib.import_module(module_name)
                discovered += 1
                logger.debug("Discovered source module: %s", module_name)
            except ImportError as exc:
                logger.warning("Failed to import source %s: %s", module_name, exc)

    logger.debug("Discovered %d source modules", discovered)
    return discovered


# Auto-discover sources on package import
discover_sources()
