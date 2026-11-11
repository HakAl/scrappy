"""Fail-closed release decisions. Network acquisition belongs to the workflow."""
from __future__ import annotations

import argparse
import email
import hashlib
import json
import os
import re
import tarfile
import tomllib
import zipfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

WORKFLOW = ".github/workflows/release.yml"


class GateError(Exception):
    """A release precondition failed, with a stable machine-readable code."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail


def require(ok: bool, code: str, detail: str) -> None:
    if not ok:
        raise GateError(code, detail)


def inputs(env: Mapping[str, str]) -> dict[str, str]:
    version, sha = env.get("VERSION", ""), env.get("SHA", "")
    publish, run = env.get("PUBLISH", ""), env.get("BUILD_RUN_ID", "")
    require(re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) is not None,
            "invalid-version", version)
    require(re.fullmatch(r"[0-9a-f]{40}", sha) is not None, "invalid-sha", sha)
    require(publish in {"true", "false"}, "invalid-publish", publish)
    require((publish == "true" and re.fullmatch(r"[1-9][0-9]{0,19}", run) is not None)
            or (publish == "false" and run == ""), "invalid-build-run-id", run)
    return {"version": version, "sha": sha, "publish": publish, "build_run_id": run}


def ref(env: Mapping[str, str], tag_type: str = "", tag_commit: str = "") -> dict[str, str]:
    p = inputs(env)
    expected = f"refs/tags/v{p['version']}" if p["publish"] == "true" else "refs/heads/main"
    require(env.get("GITHUB_REF") == expected, "ref-mismatch", expected)
    require(env.get("GITHUB_SHA") == p["sha"], "sha-mismatch", "dispatch commit")
    if p["publish"] == "true":
        require(tag_type.strip() == "tag", "tag-not-annotated", tag_type)
        require(tag_commit.strip() == p["sha"], "tag-mismatch", tag_commit)
    return p


def main_head(env: Mapping[str, str], commit: dict[str, Any], ancestor_exit: str) -> dict[str, str]:
    p = inputs(env)
    if p["publish"] == "false":
        require(commit.get("sha") == p["sha"], "main-moved", "main is not release SHA")
    else:
        require(ancestor_exit == "0", "not-main-ancestor", ancestor_exit)
    return p


def version(env: Mapping[str, str], project: dict[str, Any]) -> dict[str, str]:
    p = inputs(env)
    require(project.get("project", {}).get("version") == p["version"],
            "version-mismatch", "pyproject version")
    return p


def tests_run(env: Mapping[str, str], workflow: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    p = inputs(env)
    runs = data.get("workflow_runs", [])
    # Select identity first, then require the newest run to be successful. Filtering
    # success first would silently accept an old success after a failed rerun.
    matching = [r for r in runs if all((
        r.get("workflow_id") == workflow.get("id") and workflow.get("id") is not None,
        r.get("path") == ".github/workflows/tests.yml",
        r.get("head_sha") == p["sha"], r.get("head_branch") == "main",
        r.get("event") == "push",
        r.get("repository", {}).get("full_name") == env.get("GITHUB_REPOSITORY"),
    ))]
    require(bool(matching), "tests-run-mismatch", "no matching main Tests push run")
    latest = max(matching, key=lambda r: (r.get("run_number", 0), r.get("run_attempt", 0)))
    require(latest.get("status") == "completed" and latest.get("conclusion") == "success",
            "tests-not-success", "newest matching run must succeed")
    return {"tests_run_id": latest["id"]}


def pypi_absent(status: str, curl_exit: str = "0") -> dict[str, str]:
    require(curl_exit == "0" and status in {"200", "404"}, "pypi-unavailable", status)
    require(status == "404", "already-published", status)
    return {"pypi": "absent"}


def build_run(env: Mapping[str, str], workflow: dict[str, Any], run: dict[str, Any],
              artifacts: dict[str, Any]) -> dict[str, Any]:
    p = inputs(env)
    require(p["publish"] == "true", "build-run-mismatch", "publish required")
    expected = {"id": int(p["build_run_id"]), "workflow_id": workflow.get("id"),
                "path": WORKFLOW, "event": "workflow_dispatch", "head_branch": "main",
                "head_sha": p["sha"], "status": "completed", "conclusion": "success"}
    require(workflow.get("id") is not None and all(run.get(k) == v for k, v in expected.items())
            and run.get("repository", {}).get("full_name") == env.get("GITHUB_REPOSITORY")
            and type(run.get("run_attempt")) is int and run["run_attempt"] > 0,
            "build-run-mismatch", "Phase A run identity/status")
    candidates = artifacts.get("artifacts", [])
    require(len(candidates) == 1, "artifact-mismatch", "expected exactly one artifact")
    artifact = candidates[0]
    require(artifact.get("name") == f"dist-{p['version']}-{p['sha']}"
            and artifact.get("expired") is False
            and artifact.get("workflow_run", {}).get("id") == int(p["build_run_id"])
            and artifact.get("workflow_run", {}).get("head_sha") == p["sha"]
            and type(artifact.get("id")) is int and artifact["id"] > 0
            and re.fullmatch(r"sha256:[0-9a-f]{64}", artifact.get("digest", "")) is not None,
            "artifact-mismatch", "Phase A artifact identity/digest")
    return {"artifact_id": artifact["id"], "artifact_digest": artifact["digest"],
            "run_attempt": run["run_attempt"]}


def filenames(v: str) -> tuple[str, str]:
    return f"scrappy_ai-{v}-py3-none-any.whl", f"scrappy_ai-{v}.tar.gz"


def hashes(directory: Path, v: str) -> dict[str, str]:
    return {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
            for name in filenames(v)}


def read_sums(path: Path, v: str) -> dict[str, str]:
    lines = path.read_text().splitlines()
    require(len(lines) == 2, "sums-mismatch", "exactly two checksum lines required")
    result: dict[str, str] = {}
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  ([^/]+)", line)
        require(match is not None, "sums-mismatch", "malformed checksum line")
        assert match is not None
        digest, name = match.groups()
        require(name not in result, "sums-mismatch", "duplicate checksum")
        result[name] = digest
    require(set(result) == set(filenames(v)), "sums-mismatch", "checksum filenames")
    return result


def dist_dir(env: Mapping[str, str], directory: Path, run_attempt: str = "") -> dict[str, str]:
    p = inputs(env)
    names = set(filenames(p["version"])) | {"SHA256SUMS", "manifest.json"}
    require({x.name for x in directory.iterdir()} == names
            and all(x.is_file() and not x.is_symlink() for x in directory.iterdir()),
            "dist-files-mismatch", "exact four regular files required")
    sums = read_sums(directory / "SHA256SUMS", p["version"])
    require(sums == hashes(directory, p["version"]), "hash-mismatch", "distribution bytes")
    manifest = json.loads((directory / "manifest.json").read_text())
    require(set(manifest) == {"version", "sha", "publish", "workflow_path", "run_id",
                              "run_attempt", "github_ref", "files"},
            "manifest-mismatch", "manifest keys")
    expected: dict[str, Any] = {"version": p["version"], "sha": p["sha"], "publish": False,
                               "workflow_path": WORKFLOW, "github_ref": "refs/heads/main",
                               "files": sums}
    require(all(manifest[k] == val for k, val in expected.items())
            and manifest["publish"] is False
            and type(manifest["run_id"]) is int and manifest["run_id"] > 0
            and type(manifest["run_attempt"]) is int and manifest["run_attempt"] > 0,
            "manifest-mismatch", "manifest identity")
    expected_run = p["build_run_id"] if p["publish"] == "true" else env.get("GITHUB_RUN_ID", "")
    require(str(manifest["run_id"]) == expected_run, "manifest-mismatch", "manifest run id")
    expected_attempt = run_attempt or (env.get("GITHUB_RUN_ATTEMPT", "")
                                       if p["publish"] == "false" else "")
    if expected_attempt:
        require(str(manifest["run_attempt"]) == expected_attempt,
                "manifest-mismatch", "manifest run attempt")
    wheel, sdist = filenames(p["version"])
    return {"wheel": wheel, "wheel_sha256": sums[wheel],
            "sdist": sdist, "sdist_sha256": sums[sdist]}


def manifest_write(env: Mapping[str, str], directory: Path) -> dict[str, str]:
    p = inputs(env)
    require(p["publish"] == "false" and env.get("GITHUB_REF") == "refs/heads/main",
            "manifest-mismatch", "Phase A only")
    require({x.name for x in directory.iterdir()} == set(filenames(p["version"]))
            and all(x.is_file() and not x.is_symlink() for x in directory.iterdir()),
            "dist-files-mismatch", "writer requires exactly two distributions")
    require(re.fullmatch(r"[1-9][0-9]*", env.get("GITHUB_RUN_ID", "")) is not None
            and re.fullmatch(r"[1-9][0-9]*", env.get("GITHUB_RUN_ATTEMPT", "")) is not None,
            "manifest-mismatch", "run identity required")
    sums = hashes(directory, p["version"])
    (directory / "SHA256SUMS").write_text("".join(f"{h}  {n}\n" for n, h in sums.items()))
    manifest = {"version": p["version"], "sha": p["sha"], "publish": False,
                "workflow_path": WORKFLOW, "run_id": int(env["GITHUB_RUN_ID"]),
                "run_attempt": int(env["GITHUB_RUN_ATTEMPT"]),
                "github_ref": "refs/heads/main", "files": sums}
    (directory / "manifest.json").write_text(json.dumps(manifest, sort_keys=True) + "\n")
    return dist_dir(env, directory)


def metadata(env: Mapping[str, str], wheel: Path, sdist: Path,
             project: dict[str, Any]) -> dict[str, str]:
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name

    p = inputs(env)
    require((wheel.name, sdist.name) == filenames(p["version"]),
            "metadata-filename", "unexpected distribution filename")
    config = project["project"]

    def normalized(raw: str) -> tuple[Any, ...]:
        r = Requirement(raw)
        return (canonicalize_name(r.name), tuple(sorted(r.extras)), str(r.specifier),
                r.url, str(r.marker) if r.marker else "")

    expected = set(map(normalized, config.get("dependencies", [])))
    for extra, deps in config.get("optional-dependencies", {}).items():
        for dep in deps:
            r = Requirement(dep)
            marker = f'({r.marker}) and extra == "{extra}"' if r.marker else f'extra == "{extra}"'
            r.marker = None
            expected.add(normalized(f"{r}; {marker}"))
    with zipfile.ZipFile(wheel) as archive:
        members = [n for n in archive.namelist() if n.endswith(".dist-info/METADATA")]
        require(len(members) == 1, "metadata-mismatch", "one wheel metadata required")
        wheel_data = archive.read(members[0])
    with tarfile.open(sdist) as sdist_archive:
        member = sdist_archive.extractfile(f"scrappy_ai-{p['version']}/PKG-INFO")
        require(member is not None, "metadata-mismatch", "sdist PKG-INFO absent")
        assert member is not None
        sdist_data = member.read()
    for content in (wheel_data, sdist_data):
        msg = email.message_from_bytes(content)
        require(canonicalize_name(str(msg.get("Name", ""))) == "scrappy-ai"
                and msg.get("Version") == p["version"]
                and msg.get("Requires-Python") == config["requires-python"]
                and set(map(normalized, msg.get_all("Requires-Dist", []))) == expected,
                "metadata-mismatch", "distribution metadata differs from pyproject")
    return {"metadata": "matched"}


def pypi_files(env: Mapping[str, str], data: dict[str, Any], path: Path) -> dict[str, str]:
    p = inputs(env)
    sums = read_sums(path / "SHA256SUMS" if path.is_dir() else path, p["version"])
    urls = data.get("urls", [])
    require(len(urls) == 2 and {u.get("filename") for u in urls} == set(sums)
            and all(u.get("digests", {}).get("sha256") == sums[u["filename"]] for u in urls),
            "pypi-mismatch", "published files/hashes differ; reconcile, never re-upload")
    return {"pypi": "matched"}


def load_json(path: str) -> dict[str, Any]:
    value: dict[str, Any] = json.loads(Path(path).read_text())
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["inputs", "ref", "main-head", "version", "tests-run",
                                           "pypi-absent", "build-run", "dist-dir", "metadata",
                                           "pypi-files", "manifest-write"])
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args()
    env = os.environ
    paths = args.paths
    try:
        result: dict[str, Any]
        if args.command == "inputs":
            result = inputs(env)
        elif args.command == "ref":
            result = ref(env, Path(paths[0]).read_text() if paths else "",
                         Path(paths[1]).read_text() if paths else "")
        elif args.command == "main-head":
            result = main_head(env, load_json(paths[0]), env.get("ANCESTOR_EXIT", ""))
        elif args.command == "version":
            result = version(env, tomllib.loads(Path(paths[0]).read_text()))
        elif args.command == "tests-run":
            result = tests_run(env, load_json(paths[0]), load_json(paths[1]))
        elif args.command == "pypi-absent":
            result = pypi_absent(Path(paths[0]).read_text().strip(), env.get("CURL_EXIT", "0"))
        elif args.command == "build-run":
            result = build_run(env, *(load_json(p) for p in paths))
        elif args.command == "dist-dir":
            result = dist_dir(env, Path(paths[0]), env.get("BUILD_RUN_ATTEMPT", ""))
        elif args.command == "manifest-write":
            result = manifest_write(env, Path(paths[0]))
        elif args.command == "metadata":
            result = metadata(env, Path(paths[0]), Path(paths[1]),
                              tomllib.loads(Path(paths[2]).read_text()))
        else:
            result = pypi_files(env, load_json(paths[0]), Path(paths[1]))
    except GateError as exc:
        print(json.dumps({"ok": False, "code": exc.code, "detail": exc.detail}))
        return 2
    print(json.dumps({"ok": True, **result}, sort_keys=True))
    output = env.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a") as stream:
            for key, value in result.items():
                stream.write(f"{key}={value}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
