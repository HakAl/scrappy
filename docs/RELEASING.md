# Releasing scrappy-ai

This guide describes maintainer actions for a reviewed release. It does not establish publishing access or authorize a release by itself.

1. **Confirm existing owner-held access.** Route A uses an existing PyPI project-scoped API token for `scrappy-ai` from a maintainer's local shell. Never commit, echo, or paste the token. Route B uses an already configured PyPI Trusted Publisher plus a matching publishing workflow and environment that can mint an OIDC token. Route B is implemented by `.github/workflows/release.yml` with the `pypi` environment. Before using it, confirm the PyPI publisher is registered for this repository, `release.yml`, and environment `pypi`; configure that environment with custom deployment policy allowing only tags matching `v*.*.*`, no branches and no secrets. Workflow existence alone does not establish publishing access. Confirm GitHub tag push rights on the reviewed commit. No new credentials or TestPyPI account are assumed; a TestPyPI dry run is optional only if the owner already has access.

2. **Isolate release tooling.** First select an installed Python >=3.11 and confirm its version: use `python3` on macOS/Linux, or `py -3` or `python` on Windows, whichever exists. Create a fresh virtual environment with that interpreter, used only for release tooling. Install `build` and `twine` there and record their versions. They are not included in the project's development extras.

   ```bash
   # macOS/Linux: confirm Python >=3.11 before creating the environment
   python3 --version
   python3 -m venv /absolute/path/to/new-release-tools
   /absolute/path/to/new-release-tools/bin/python -m pip install build twine
   /absolute/path/to/new-release-tools/bin/python -m pip show build twine
   ```

   On Windows, first confirm Python >=3.11 with `py -3 --version` (or `python --version` if that is the installed command), then create the environment with `py -3 -m venv C:\absolute\path\to\new-release-tools` (or the confirmed interpreter's absolute path with `-m venv`). Use the environment's `Scripts\python.exe` in place of `bin/python`.

3. **Select the version from a proven baseline.** Read the latest release from [PyPI JSON](https://pypi.org/pypi/scrappy-ai/json); never reuse a published version. Use the previous release tag when available. Published 1.3.0 has no release tag and no recorded artifact provenance binding it to a commit. The accepted 1.3.0 assessment found that, after CRLF normalization, all 313 Git-tracked packaged sdist paths match both `8ac6b95` and `d141222` (eight generated paths excluded). This is packaged-source content equivalence, not a unique build-commit identity, whole-repository equivalence, or wheel verification. For another baseline, download the published sdist into a new empty directory, verify its SHA-256 against PyPI, and compare its source tree with the candidate commit, or explicitly record the baseline as unresolved. Do not infer release contents from commit dates alone. Compare the proven baseline with the proposed release commit, including top-level exports, public constructors, dependency floors, and `requires-python`. Breaking changes or support drops require a major version; features a minor version; fixes alone a patch. Keep version selection unresolved until the comparison supports it.

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

7. **Gate publication, then tag the reviewed commit.** Before any tag or upload, require green main CI on the exact reviewed release SHA (green PR CI is insufficient) and confirm the artifacts were built from that SHA. If either condition fails, stop: no tag, no upload. Once both conditions hold, create an annotated `vX.Y.Z` tag on that gated SHA, push it, and confirm that the tag resolves to the gated SHA. Create GitHub release notes from the changelog section only after publication verification in step 9.

8. **Upload using the confirmed route.** For Route A, use the existing token through the maintainer's secure local credential mechanism and upload exactly the checked files:

   ```bash
   "$RELEASE_PYTHON" -m twine upload "$WHEEL" "$SDIST"
   ```

   If upload times out, is interrupted, or has an uncertain result, query `https://pypi.org/pypi/scrappy-ai/X.Y.Z/json` and compare filenames and SHA-256 hashes before retrying. Never re-upload a file already present on PyPI. A mismatch requires investigation. For Route B, use the two dispatches below. Do not rebuild after tagging or assume local twine commands supply the OIDC runtime.

9. **Verify publication.** Confirm PyPI JSON lists the intended version and both files with SHA-256 hashes matching the recorded local artifacts. In a fresh virtual environment, run `pip install scrappy-ai==X.Y.Z` and confirm `scrappy version`. Re-verify that the tag resolves to the gated SHA whose exact-main CI was green at step 7. Record the release URL, tag SHA, artifact hashes, smoke results, and CI result.


## Route B: two dispatches, one set of artifact bytes

The four jobs in `release.yml` are verify, build, publish and confirm. The top-level token has no permissions; only publish receives `id-token: write` and the `pypi` environment. Publish runs no repository code. Release tooling pins are `build==1.6.1`, `twine==7.0.0` and `packaging==26.3`, installed with binary-only resolution. Transitive dependencies are not hash-locked. Existing source mypy debt is disclosed and the CI type check remains nonblocking; all blocking Tests jobs must pass.

Complete steps 1-4 above in a reviewed PR. Merge, require the newest main Tests push run to succeed on the exact merged release SHA, and record that SHA. Phase A performs steps 5-6 before any tag. Replace `RELEASE_SHA` with that full lowercase commit SHA:

```bash
RELEASE_SHA=<exact-reviewed-main-SHA>
gh workflow run release.yml --ref main -f version=2.0.0 -f sha="$RELEASE_SHA"
```

Record the Phase A run ID and require its successful completion. Download and independently inspect its single artifact, named `dist-2.0.0-<SHA>`. Record the artifact ID and digest, the manifest, and both SHA-256 values. The exact four files are `scrappy_ai-2.0.0-py3-none-any.whl`, `scrappy_ai-2.0.0.tar.gz`, `SHA256SUMS` (two lines), and `manifest.json`. The workflow checks both archives' metadata against pyproject, exact filenames and hashes, and the first-run Terms smoke. Confirm the manifest binds the main ref, SHA, version, Phase A run ID and attempt, and file hashes. Complete the step 7 gate before creating an annotated tag:

```bash
git tag -a v2.0.0 "$RELEASE_SHA" -m 'scrappy-ai 2.0.0'
git push origin refs/tags/v2.0.0
git rev-parse 'v2.0.0^{commit}'
```

Require that output to equal `RELEASE_SHA`. Phase B downloads the existing artifact by ID from the successful Phase A run and checks its digest; it never rebuilds. The verify job binds the artifact's run, workflow, SHA and manifest, checks exact-main Tests success, confirms the release SHA remains an ancestor of main, and refuses an existing PyPI version. Set `BUILD_RUN_ID` to the recorded Phase A run ID:

```bash
BUILD_RUN_ID=<successful-Phase-A-run-id>
gh workflow run release.yml --ref v2.0.0 -f version=2.0.0 -f sha="$RELEASE_SHA" -f publish=true -f build_run_id="$BUILD_RUN_ID"
```

Publish rechecks the two hashes handed over by verify and copies only the two distributions into a fresh packages directory for PyPI Trusted Publishing. The tag-only `pypi` environment must already exist. OIDC or trust failure is a stop, not a reason to bypass gates. Confirm polls PyPI (up to 20 attempts, 15 seconds apart; only 404 is retried), requires exactly those two filenames and hashes, then installs `scrappy-ai==2.0.0` into a fresh environment and checks `scrappy v2.0.0` and Terms `q` exit 0. Its environment has isolated HOME/config/cache, dotenv loading disabled and no provider keys. This verifies first-run startup and exit, not live provider behavior.

Never blindly rerun Phase B after an uncertain upload or confirm failure. First query `https://pypi.org/pypi/scrappy-ai/2.0.0/json`. If it is 200, save the JSON and run the checked-out release script with the original artifact's checksum file:

```bash
VERSION=2.0.0 SHA="$RELEASE_SHA" PUBLISH=true BUILD_RUN_ID="$BUILD_RUN_ID" \
  python3 scripts/release_gate.py pypi-files /absolute/path/pypi.json /absolute/path/SHA256SUMS
```

A complete hash match means the bytes are already published: reconcile smoke or confirmation separately. A partial/different release requires investigation and must never be re-uploaded. Only an authoritative 404 permits retrying publication; other HTTP or transport errors leave the state unknown. Phase B itself fails closed if the version already exists.

After confirm succeeds, independently complete step 9: compare PyPI filenames/hashes, fresh-install and Terms smoke, exact tag SHA and exact-main CI. Then extract the 2.0.0 changelog section to a notes file and create notes without assets:

```bash
gh release create v2.0.0 --verify-tag --notes-file /absolute/path/2.0.0-notes.txt
```

Record and verify the release URL and notes. Do not create notes before successful publication verification. Route A remains available only with confirmed existing owner-held token access and the same gates above.

References: [Python packaging flow](https://packaging.python.org/en/latest/flow/) and [Using a PyPI Trusted Publisher](https://docs.pypi.org/trusted-publishers/using-a-publisher/).
