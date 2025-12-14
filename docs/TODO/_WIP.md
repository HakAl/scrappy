

---
NEXT UP
---

# 2. Dependency Check on Startup

```python
# Add to startup after migration
def check_dependencies() -> List[str]:
    """Check for required external tools."""
    missing = []
    if not shutil.which("git"):
        missing.append("git")
    if not shutil.which("rg"):
        logger.info("ripgrep (rg) not found - using slower grep")
    return missing
```

---

# 3. Fix Progress Bar

Blocked by migration - the IndexingProgress message system is being removed.
Progress will be simpler with prompt_toolkit (direct updates via Rich Progress with patch_stdout).
