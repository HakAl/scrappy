# Releasing scrappy-ai

This guide describes maintainer actions for a reviewed release. It does not establish publishing access or authorize a release by itself.

1. **Confirm existing owner-held access.** Route A uses an existing PyPI project-scoped API token for `scrappy-ai` from a maintainer's local shell. Never commit, echo, or paste the token. Route B uses an already configured PyPI Trusted Publisher plus a matching publishing workflow and environment that can mint an OIDC token. This repository currently has no publishing workflow, so Route B is unavailable as-is. Adding one is a separate owner decision. Confirm GitHub tag push rights on the reviewed commit. No new credentials or TestPyPI account are assumed; a TestPyPI dry run is optional only if the owner already has access.

2. **Isolate release tooling.** First select an installed Python >=3.11 and confirm its version: use `python3` on macOS/Linux, or `py -3` or `python` on Windows, whichever exists. Create a fresh virtual environment with that interpreter, used only for release tooling. Install `build` and `twine` there and record their versions. They are not included in the project's development extras.

   ```bash
   # macOS/Linux: confirm Python >=3.11 before creating the environment
   python3 --version
   python3 -m venv /absolute/path/to/new-release-tools
   /absolute/path/to/new-release-tools/bin/python -m pip install build twine
   /absolute/path/to/new-release-tools/bin/python -m pip show build twine
   ```

   On Windows, first confirm Python >=3.11 with `py -3 --version` (or `python --version` if that is the installed command), then create the environment with `py -3 -m venv C:\absolute\path\to\new-release-tools` (or the confirmed interpreter's absolute path with `-m venv`). Use the environment's `Scripts\python.exe` in place of `bin/python`.

3. **Select the version from a proven baseline.** Read the latest release from [PyPI JSON](https://pypi.org/pypi/scrappy-ai/json); never reuse a published version. Use the previous release tag when available. Published 1.3.0 has no release tag and no recorded artifact provenance binding it to a commit. Commit `8ac6b95` is only a candidate baseline. Establish provenance by downloading the published sdist into a new empty directory, verifying its SHA-256 against PyPI, and comparing its source tree with the candidate commit, or explicitly record the baseline as unresolved. Do not infer release contents from commit dates alone. Compare the proven baseline with the proposed release commit, including top-level exports, public constructors, dependency floors, and `requires-python`. Breaking changes or support drops require a major version; features a minor version; fixes alone a patch. Keep version selection unresolved until the comparison supports it.

4. **Review the release changes.** Add the changelog release section using towncrier fragments or a manual entry, and update the package version in a reviewed PR before tagging. Include the compatibility comparison and any unresolved provenance in the review record.

5. **Build exact artifacts.** Start from a clean checkout of the exact reviewed main SHA. Create a fresh, empty output directory outside any previous build output; a clean Git tree does not exclude stale artifacts. Set `RELEASE_OUT` to that directory and `RELEASE_PYTHON` to the isolated tooling environment's Python. Replace all example paths with absolute paths for this release.

   ```bash
   git rev-parse HEAD
   git status --porcelain
   mkdir /absolute/path/to/new-empty-release-output
   RELEASE_OUT=/absolute/path/to/new-empty-release-output
   RELEASE_PYTHON=/absolute/path/to/new-release-tools/bin/python
   "$RELEASE_PYTHON" -m build --outdir "$RELEASE_OUT"
   ```

   Record the exact wheel and sdist paths as `WHEEL` and `SDIST`, and their SHA-256 hashes. Use those two exact paths for every subsequent check and upload; do not use `dist/*` or other artifact globs.

   ```bash
   WHEEL=/absolute/path/to/new-empty-release-output/scrappy_ai-X.Y.Z-py3-none-any.whl
   SDIST=/absolute/path/to/new-empty-release-output/scrappy_ai-X.Y.Z.tar.gz
   shasum -a 256 "$WHEEL" "$SDIST"
   "$RELEASE_PYTHON" -m twine check "$WHEEL" "$SDIST"
   ```

   Inspect the wheel's METADATA and confirm `Version`, `Requires-Python`, and `Requires-Dist` match the reviewed `pyproject.toml`. Record the tools, reviewed SHA, paths, hashes, and check output.

6. **Smoke test the wheel.** In another fresh virtual environment, install from the exact `WHEEL` path. Confirm `scrappy version` prints the new version. With isolated configuration and no provider keys, start `scrappy` and quit the first-run Terms of Use notice with `q`; confirm exit status 0. This does not verify live provider chat or agent execution.

7. **Gate publication, then tag the reviewed commit.** Before any tag or upload, require green main CI on the exact reviewed release SHA (green PR CI is insufficient) and confirm the artifacts were built from that SHA. If either condition fails, stop: no tag, no upload. Once both conditions hold, create an annotated `vX.Y.Z` tag on that gated SHA, push it, and create GitHub release notes from the changelog section. Confirm that the tag resolves to the gated SHA.

8. **Upload using the confirmed route.** For Route A, use the existing token through the maintainer's secure local credential mechanism and upload exactly the checked files:

   ```bash
   "$RELEASE_PYTHON" -m twine upload "$WHEEL" "$SDIST"
   ```

   If upload times out, is interrupted, or has an uncertain result, query `https://pypi.org/pypi/scrappy-ai/X.Y.Z/json` and compare filenames and SHA-256 hashes before retrying. Never re-upload a file already present on PyPI. A mismatch requires investigation. Route B requires the separately established OIDC workflow and environment from step 1; do not assume local twine commands supply that runtime.

9. **Verify publication.** Confirm PyPI JSON lists the intended version and both files with SHA-256 hashes matching the recorded local artifacts. In a fresh virtual environment, run `pip install scrappy-ai==X.Y.Z` and confirm `scrappy version`. Re-verify that the tag resolves to the gated SHA whose exact-main CI was green at step 7. Record the release URL, tag SHA, artifact hashes, smoke results, and CI result.

References: [Python packaging flow](https://packaging.python.org/en/latest/flow/) and [Using a PyPI Trusted Publisher](https://docs.pypi.org/trusted-publishers/using-a-publisher/).
