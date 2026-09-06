#!/usr/bin/env bash
#
# scripts/contained-pytest.sh -- contained pytest launcher (scrappy-i2jo PR-1).
#
# WHY OUT OF PROCESS: import ordering, and nothing else.
#   - infrastructure/paths.py:25-29 computes USER_CONFIG_DIR, USER_CONFIG_FILE and
#     LEGACY_USER_DIR at module import.
#   - huggingface_hub/constants.py:150-181 binds its whole cache chain at import.
#   - pytest loads plugins and conftests before it calls _do_configure, so
#     pytest_configure cannot be proven to precede those imports for an arbitrary
#     installed plugin set.
#   A launcher that assigns the containment environment before `exec` has no such
#   window. This does NOT claim a shell script is the only possible early bootstrap;
#   it claims pytest_configure is not one. Any equally-early mechanism would substitute.
#
# The launcher VALIDATES (fail-closed) -> ASSIGNS -> CREATES -> execs pytest.
#
# It refuses to run on Windows. The reason is PARTIALITY, not impossibility: on
# Windows USERPROFILE steers Path.home()-derived storage, but platformdirs binds and
# caches SHGetFolderPathW at import (platformdirs/windows.py:258-274, :241-243) and is
# not redirected by any environment variable on that branch. A launcher there would
# contain some profile paths and silently miss others; Windows containment is delivered
# by injection (PR-3, PR-4), not by this instrument. See plan S-1 / 3f.

set -euo pipefail

# --- optional dry-run flag: print the plan instead of exec'ing pytest ----------
# This runs the full platform gate, preflight and directory creation; it only skips
# the final exec. It is a CLI flag, not an environment variable, and cannot bypass
# the platform refusal or any validation.
PRINT_ONLY=0
if [ "${1:-}" = "--contained-print-env" ]; then
    PRINT_ONLY=1
    shift
fi

# --- platform gate (probeable: derives the platform from `uname -s`) -----------
# A probe can exercise the refusal by placing a stub `uname` earlier on PATH.
contained_pytest_platform() {
    uname -s 2>/dev/null || printf 'unknown'
}

_platform="$(contained_pytest_platform)"
case "$_platform" in
    Darwin | Linux) : ;;
    *)
        cat >&2 <<EOF
contained-pytest: REFUSING to run on platform '${_platform}'.
Reason: PARTIALITY, not impossibility. Environment steering on this platform does not
cover every application-profile path: USERPROFILE steers Path.home(), but platformdirs
binds SHGetFolderPathW at import and no environment variable redirects it (plan S-1/3f).
A boundary that contains some profile paths and silently misses others invites the very
false confidence this instrument exists to remove. Windows containment is delivered by
injection (PR-3 for U-1, PR-4 for the provider directories), not by this launcher.
EOF
        exit 3
        ;;
esac

# --- repo root, canonicalized to match tests/conftest.py's Path.resolve() -------
_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd "${_script_dir}/.." && pwd -P)"

# --- interpreter: stdlib + third-party only in preflight; never the app ---------
VENV_PYTHON="${REPO_ROOT}/.venv/bin/python"
if [ ! -x "${VENV_PYTHON}" ]; then
    echo "contained-pytest: expected a virtualenv interpreter at ${VENV_PYTHON}" >&2
    exit 4
fi

# --- capture INHERITED, UNGUARDED inputs (S-13) before overriding them ----------
_inherited_scratch_root="${SCRAPPY_TEST_TEMP:-}"
_inherited_session_id="${SCRAPPY_TEST_SESSION_ID:-}"
_original_home="${HOME:-}"

# --- session id: adopt a valid inherited one, else generate a fresh one ---------
if [ -n "${_inherited_session_id}" ]; then
    SESSION_ID="${_inherited_session_id}"
else
    SESSION_ID="run-$(date +%Y%m%d-%H%M%S)-$$"
fi

# --- profile layout, gitignored, under the repository ---------------------------
#   home/    -> HOME. THE MEASURED REGION (manifested).
#   caches/  -> HF + fastembed. SIBLING, deliberately NOT measured.
#   scratch/<sid>/system -> the os scratch dir (the exact path conftest recomputes)
#   scratch/<sid>/pytest -> pytest basetemp
PROFILE_ROOT="${REPO_ROOT}/.pytest_profile/${SESSION_ID}"
HOME_DIR="${PROFILE_ROOT}/home"
CACHES_DIR="${PROFILE_ROOT}/caches"
SCRATCH_BASE="${PROFILE_ROOT}/scratch"
SCRATCH_OS_DIR="${SCRATCH_BASE}/${SESSION_ID}/system"
SCRATCH_PYTEST_DIR="${SCRATCH_BASE}/${SESSION_ID}/pytest"
CLI_CONFIG_ABSENT="${HOME_DIR}/.config/scrappy/contained-cli-config.absent.json"

# --- STEP A: fail-closed preflight (runs BEFORE any directory is created) --------
# Validates the inherited S-13 inputs, the chosen session id, the effective
# --basetemp, and the installed python-dotenv capability. On any failure `set -e`
# stops the script here and pytest never starts.
"${VENV_PYTHON}" "${_script_dir}/_contained_pytest_preflight.py" \
    --repo-root "${REPO_ROOT}" \
    --profile-root "${PROFILE_ROOT}" \
    --home "${HOME_DIR}" \
    --original-home "${_original_home}" \
    --session-id "${SESSION_ID}" \
    --inherited-test-temp "${_inherited_scratch_root}" \
    --inherited-session-id "${_inherited_session_id}" \
    --dotenv-floor "1.2.0" \
    -- "$@"

# --- STEP B: create the disposable destinations before exec ---------------------
# So the redirected scratch and cache roots exist inside the repo before pytest runs.
mkdir -p \
    "${HOME_DIR}/.config" \
    "${HOME_DIR}/.local/share" \
    "${HOME_DIR}/.cache" \
    "${CACHES_DIR}/huggingface/hub" \
    "${CACHES_DIR}/huggingface/assets" \
    "${CACHES_DIR}/fastembed" \
    "${SCRATCH_OS_DIR}" \
    "${SCRATCH_PYTEST_DIR}"

# --- STEP C: post-creation containment assertions (validation items 1, 2) -------
if [ ! -d "${PROFILE_ROOT}" ]; then
    echo "contained-pytest: profile root was not created: ${PROFILE_ROOT}" >&2
    exit 5
fi
case "${PROFILE_ROOT}/" in
    "${REPO_ROOT}"/*) : ;;
    *)
        echo "contained-pytest: profile root ${PROFILE_ROOT} is not under the repo ${REPO_ROOT}" >&2
        exit 5
        ;;
esac
if [ "${HOME_DIR}" = "${_original_home}" ]; then
    echo "contained-pytest: contained HOME still equals the real HOME ${_original_home}" >&2
    exit 5
fi

# --- STEP D: ASSIGN the containment environment (plain assignment, never setdefault) ---
export HOME="${HOME_DIR}"
# Linux platformdirs prefers XDG over the HOME fallback; keep them inside the
# MEASURED home region. XDG_CACHE_HOME also feeds the HF default chain, which the
# explicit HF_* assignments below then override to the unmeasured caches sibling.
export XDG_DATA_HOME="${HOME_DIR}/.local/share"
export XDG_CONFIG_HOME="${HOME_DIR}/.config"
export XDG_CACHE_HOME="${HOME_DIR}/.cache"
# Full HF override chain -> caches sibling. HF_HOME alone loses to either of the
# other two, so all four are assigned (plan S-2).
export HF_HOME="${CACHES_DIR}/huggingface"
export HUGGINGFACE_HUB_CACHE="${CACHES_DIR}/huggingface/hub"
export HF_HUB_CACHE="${CACHES_DIR}/huggingface/hub"
export HF_ASSETS_CACHE="${CACHES_DIR}/huggingface/assets"
# fastembed resolves at call time; an ambient value would win otherwise (S-3).
export FASTEMBED_CACHE_PATH="${CACHES_DIR}/fastembed"
# Supported disable switch, checked before discovery (S-4); the preflight proved the
# installed distribution honours it.
export PYTHON_DOTENV_DISABLED="1"
# Bootstrap ordering, and canonical values for the independently-based macOS/tmux
# children (S-13, S-5). These equal the path tests/conftest.py will recompute.
export TMPDIR="${SCRATCH_OS_DIR}"
export TEMP="${SCRATCH_OS_DIR}"
export TMP="${SCRATCH_OS_DIR}"
# Align conftest's in-process tempfile owner with the launcher (S-13).
export SCRAPPY_TEST_TEMP="${SCRATCH_BASE}"
export SCRAPPY_TEST_SESSION_ID="${SESSION_ID}"
# ALWAYS assign CLI_CONFIG_PATH. An ambient value outranks the CWD scan and reaches a
# real parser (S-12); absence is not inheritable state (R-L), so unsetting a parent
# copy would leave a hostile value intact in an independently-based child. The value
# is a contained path that does not exist: config_factory.py:163 gates the load on
# file_to_load.exists(), so a missing path skips discovery gracefully and falls back
# to defaults, while still displacing any real config the CWD scan would have found.
export CLI_CONFIG_PATH="${CLI_CONFIG_ABSENT}"

if [ "${PRINT_ONLY}" = "1" ]; then
    # Print the assignment plan from the launcher's own source variables (never by
    # re-reading the exported temp variables, which a static guard treats as touching
    # the real system scratch path). pytest is NOT started in this mode.
    printf '%s\n' \
        "# contained-pytest plan (dry run; pytest NOT started)" \
        "REPO_ROOT=${REPO_ROOT}" \
        "SESSION_ID=${SESSION_ID}" \
        "PROFILE_ROOT=${PROFILE_ROOT}" \
        "HOME=${HOME_DIR}" \
        "XDG_DATA_HOME=${HOME_DIR}/.local/share" \
        "XDG_CONFIG_HOME=${HOME_DIR}/.config" \
        "XDG_CACHE_HOME=${HOME_DIR}/.cache" \
        "HF_HOME=${CACHES_DIR}/huggingface" \
        "HUGGINGFACE_HUB_CACHE=${CACHES_DIR}/huggingface/hub" \
        "HF_HUB_CACHE=${CACHES_DIR}/huggingface/hub" \
        "HF_ASSETS_CACHE=${CACHES_DIR}/huggingface/assets" \
        "FASTEMBED_CACHE_PATH=${CACHES_DIR}/fastembed" \
        "PYTHON_DOTENV_DISABLED=1" \
        "TMPDIR=${SCRATCH_OS_DIR}" \
        "TEMP=${SCRATCH_OS_DIR}" \
        "TMP=${SCRATCH_OS_DIR}" \
        "SCRAPPY_TEST_TEMP=${SCRATCH_BASE}" \
        "SCRAPPY_TEST_SESSION_ID=${SESSION_ID}" \
        "CLI_CONFIG_PATH=${CLI_CONFIG_ABSENT}"
    exit 0
fi

# --- STEP E: exec pytest with the caller's arguments ----------------------------
exec "${VENV_PYTHON}" -m pytest "$@"
