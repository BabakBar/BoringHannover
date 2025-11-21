"""Source registry and autodiscovery for KinoWeek event sources.

This package provides a plugin-based architecture for event sources.
Each source is registered automatically when its module is imported.

Usage:
    from kinoweek.sources import get_all_sources, get_source

    # Get all registered sources
    sources = get_all_sources()

    # Get a specific source by name
    astor = get_source("astor_hannover")

Adding a new source:
    1. Create a new module in the appropriate subdirectory
    2. Import BaseSource and register_source from kinoweek.sources.base
    3. Decorate your source class with @register_source("source_name")
    4. The source will be auto-discovered on import
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from pathlib import Path
from typing import TYPE_CHECKING

from kinoweek.sources.base import (
    BaseSource,
    get_all_sources,
    get_source,
    get_sources_by_type,
    register_source,
)

if TYPE_CHECKING:
    pass

__all__ = [
    "BaseSource",
    "register_source",
    "get_source",
    "get_all_sources",
    "get_sources_by_type",
    "discover_sources",
]

logger = logging.getLogger(__name__)


def discover_sources() -> int:
    """Auto-import all source modules to trigger registration.

    Scans subdirectories (cinema, concerts, theaters, etc.) and imports
    all Python modules found, which triggers the @register_source decorator.

    Returns:
        Number of source modules discovered.
    """
    package_dir = Path(__file__).parent
    discovered = 0

    # Define subdirectories to scan for sources
    source_types = ["cinema", "concerts", "theaters", "festivals", "museums"]

    for subdir in source_types:
        subdir_path = package_dir / subdir
        if not subdir_path.exists():
            continue

        # Import all modules in the subdirectory
        for module_info in pkgutil.iter_modules([str(subdir_path)]):
            if module_info.name.startswith("_"):
                continue  # Skip private modules

            module_name = f"kinoweek.sources.{subdir}.{module_info.name}"
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
