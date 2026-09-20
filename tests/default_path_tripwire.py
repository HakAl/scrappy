"""Tripwire that rejects reads and writes of the default user config path.

The API-key service reaches storage lazily: the first read runs
``ApiKeyConfigService.load()``, which migrates env vars and saves when anything
migrated. A test that merely asserts the default config file was not CREATED
therefore proves nothing -- ``JSONPersistence.load()`` returns None for a
missing file, and the suite clears the provider env vars, so nothing is saved.

This arms the persistence boundary instead. ``paths.USER_CONFIG_FILE`` is
repointed at a sentinel under the per-test ``tmp_path`` and both
``JSONPersistence.load`` and ``JSONPersistence.save`` are wrapped, so any call
that resolves to the sentinel fails loudly whether it reads or writes. Paths
are compared RESOLVED, because a platform may expose the same location through
a symlinked prefix and the unresolved strings would then differ.
"""

import contextlib
from pathlib import Path

from scrappy.infrastructure import paths
from scrappy.infrastructure.persistence.json_persistence import JSONPersistence

TRIPWIRE_MESSAGE = "default-path config access"


@contextlib.contextmanager
def armed_default_path_tripwire(tmp_path: Path, monkeypatch):
    """Repoint the default config path at a sentinel and reject any access.

    Args:
        tmp_path: Per-test directory owning the sentinel.
        monkeypatch: Fixture used so every patch unwinds with the test.

    Yields:
        The sentinel path. It is never created; touching it at all fails.
    """
    sentinel = tmp_path / "default-profile" / "config.json"
    monkeypatch.setattr(paths, "USER_CONFIG_FILE", sentinel)

    resolved_sentinel = sentinel.resolve()
    real_load = JSONPersistence.load
    real_save = JSONPersistence.save

    def reject_if_default_path(persistence: JSONPersistence) -> None:
        if Path(persistence.file_path).resolve() == resolved_sentinel:
            raise AssertionError(TRIPWIRE_MESSAGE)

    def guarded_load(self, *args, **kwargs):
        reject_if_default_path(self)
        return real_load(self, *args, **kwargs)

    def guarded_save(self, *args, **kwargs):
        reject_if_default_path(self)
        return real_save(self, *args, **kwargs)

    monkeypatch.setattr(JSONPersistence, "load", guarded_load)
    monkeypatch.setattr(JSONPersistence, "save", guarded_save)

    yield sentinel
