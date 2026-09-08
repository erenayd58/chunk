"""Finding the chunking methods: import the plugin directory, collect what it declares.

Adding a method used to mean editing a central tuple -- write the module, then
remember to import it and list it in ``registry._BUILTIN``. The tuple was the
single point of truth and also the single thing everybody forgot. This module
replaces it with the directory itself: every ``.py`` under
``amsc/chunking/plugins/`` is imported, and every
:class:`~amsc.chunking.method.ChunkMethod` it declares is registered.

Two ways to declare, both found here:

* the :func:`amsc.chunking.contract.chunker` decorator, which leaves the method
  on the function as ``chunk_method`` -- what a new plugin should use;
* a module-level ``ChunkMethod`` value, which is what the four shipped methods
  write, because a wrapper around a frozen engine is a partition the decorator
  has nothing to add to.

Nothing is scanned for by name and no plugin is guessed at: a module is a
plugin because it sits in the plugin package, and a method exists because a
module said so. A file whose name starts with ``_`` is skipped, so a plugin
directory can hold a helper.

**This module must not import the registry.** Discovery returns methods; the
registry registers them. That is what keeps the cycle out (registry ->
discovery -> plugin -> contract -> method) and lets a plugin import the
contract types freely.
"""

from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType
from typing import Iterator, Sequence

from .method import ChunkMethod

#: The directory a plugin is dropped into. One package, no configuration: a
#: file here is a method, and the path is what ``docs/adding-a-chunker.md``
#: tells an author.
PLUGIN_PACKAGE = "amsc.chunking.plugins"

__all__ = ["PLUGIN_PACKAGE", "plugin_module_names", "import_plugins", "declared_in",
           "discover", "in_display_order"]


def plugin_module_names(package: str = PLUGIN_PACKAGE) -> list[str]:
    """The importable module names in the plugin package, in a stable order.

    Sorted rather than left to the finder: the registry's display order comes
    from :attr:`ChunkMethod.order`, and nothing should depend on the order a
    filesystem happened to list a directory in.
    """
    container = importlib.import_module(package)
    return sorted(
        f"{package}.{info.name}"
        for info in pkgutil.iter_modules(container.__path__)
        if not info.name.startswith("_")
    )


def import_plugins(package: str = PLUGIN_PACKAGE) -> list[ModuleType]:
    """Import every plugin module. An import error names the file and stops.

    Deliberately not swallowed: a plugin that cannot be imported is a bug in
    the plugin, and a registry that silently lists three of four methods is
    worse than one that refuses to load.
    """
    modules: list[ModuleType] = []
    for name in plugin_module_names(package):
        try:
            modules.append(importlib.import_module(name))
        except Exception as error:  # noqa: BLE001 -- re-raised with the file named
            raise ImportError(
                f"the chunking plugin {name!r} could not be imported: {error}"
            ) from error
    return modules


def declared_in(module: ModuleType) -> Iterator[ChunkMethod]:
    """Every method one plugin module declares, deduplicated by identity.

    A module that imports another plugin's method (to name a baseline, say)
    does not thereby declare it twice: the same object is yielded once, and
    :func:`discover` skips one already registered as itself.
    """
    seen: list[int] = []
    for value in vars(module).values():
        method = value if isinstance(value, ChunkMethod) else getattr(value, "chunk_method", None)
        if isinstance(method, ChunkMethod) and id(method) not in seen:
            seen.append(id(method))
            yield method


def discover(package: str = PLUGIN_PACKAGE) -> list[ChunkMethod]:
    """Every method the plugin directory declares, in the order they register.

    Duplicate keys are reported here, naming both modules, rather than
    surfacing as the registry's less specific "already registered".
    """
    found: dict[str, tuple[str, ChunkMethod]] = {}
    ordered: list[ChunkMethod] = []
    for module in import_plugins(package):
        for method in declared_in(module):
            previous = found.get(method.key)
            if previous is not None:
                if previous[1] is method:       # re-exported, not re-declared
                    continue
                raise ValueError(
                    f"two chunking plugins declare the key {method.key!r}: "
                    f"{previous[0]} and {module.__name__}"
                )
            found[method.key] = (module.__name__, method)
            ordered.append(method)
    return ordered


def in_display_order(found: Sequence[ChunkMethod]) -> list[ChunkMethod]:
    """Methods sorted the way every screen lists them: by ``order``, then key."""
    return sorted(found, key=lambda method: (method.order, method.key))
