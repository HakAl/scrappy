
## Optimization Opportunity: Incremental Fingerprinting

**Problem:** `update_fingerprints()` does a FULL rescan of ALL files every time, even when only 1 file changed.

**Current implementation** (`staleness.py:345-371`):
```python
def update_fingerprints(self) -> None:
    current_files = self.file_scanner.scan_files(self.root_path)  # Scans ALL files

    new_fingerprints: Dict[str, tuple] = {}
    for file_path in current_files:  # Fingerprints ALL files
        new_fingerprints[file_path] = self.file_scanner.get_fingerprint(full_path)

    self._fingerprints = new_fingerprints  # Replaces everything
```

**Proposed optimization - incremental update:**
```python
def update_fingerprints(self, staleness_report: Optional[StalenessReport] = None) -> None:
    if staleness_report is None:
        # No report - do full scan (first run)
        # ... existing full scan logic
        return

    # Incremental update - only process changes
    # Remove deleted files
    for deleted in staleness_report.deleted:
        self._fingerprints.pop(deleted, None)

    # Update added/modified files only
    for file_path in staleness_report.added | staleness_report.modified:
        full_path = self.root_path / file_path
        try:
            self._fingerprints[file_path] = self.file_scanner.get_fingerprint(full_path)
        except (OSError, FileNotFoundError):
            pass

    # Update directory mtimes
    self._dir_mtimes = self.file_scanner.scan_directory_mtimes(self.root_path)
    self._save_fingerprints()
```

**Benefits:**
- Updates become O(changed_files) instead of O(all_files)
- Pass `StalenessReport` from `check_staleness()` to `update_fingerprints()`
- Only fingerprint added/modified files
- Remove deleted files from the map
- Keep existing fingerprints for unchanged files

**Files to modify:**
- `src/scrappy/context/staleness.py` - Add optional `staleness_report` parameter to `update_fingerprints()`
- `src/scrappy/context/codebase_context.py` - Pass staleness_report to `update_fingerprints()` calls
- `src/scrappy/context/semantic_manager.py` - Pass staleness_report to `update_fingerprints()` calls

--


