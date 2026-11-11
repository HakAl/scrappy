"""Offline release decisions, with real REST-shaped data and archive bytes."""
import copy
import importlib.util
import io
import json
import tarfile
import zipfile
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "release_gate", Path(__file__).resolve().parents[2] / "scripts/release_gate.py"
)
assert SPEC is not None and SPEC.loader is not None
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)
SHA = "a" * 40


@pytest.fixture
def env():
    return {"VERSION": "2.0.0", "SHA": SHA, "PUBLISH": "false", "BUILD_RUN_ID": "",
            "GITHUB_REF": "refs/heads/main", "GITHUB_SHA": SHA,
            "GITHUB_REPOSITORY": "HakAl/scrappy", "GITHUB_RUN_ID": "123",
            "GITHUB_RUN_ATTEMPT": "1"}


def fails(code, fn, *args):
    with pytest.raises(gate.GateError) as caught:
        fn(*args)
    assert caught.value.code == code


@pytest.mark.parametrize(("key", "value", "code"), [
    ("SHA", "g" * 40, "invalid-sha"), ("SHA", "a" * 39, "invalid-sha"),
    ("SHA", "A" * 40, "invalid-sha"), ("VERSION", "1.2", "invalid-version"),
    ("VERSION", "2.0.0;x", "invalid-version"), ("VERSION", "v2.0.0", "invalid-version"),
    ("PUBLISH", "True", "invalid-publish"), ("PUBLISH", "", "invalid-publish"),
    ("BUILD_RUN_ID", "123", "invalid-build-run-id"),
])
def test_inputs_negative(env, key, value, code):
    env[key] = value
    fails(code, gate.inputs, env)


@pytest.mark.parametrize("run", ["", "0123", " 123", "1" * 21])
def test_publish_run_id_negative(env, run):
    env.update(PUBLISH="true", BUILD_RUN_ID=run)
    fails("invalid-build-run-id", gate.inputs, env)


def test_inputs_positive(env):
    assert gate.inputs(env)["version"] == "2.0.0"
    env.update(PUBLISH="true", BUILD_RUN_ID="123")
    assert gate.inputs(env)["build_run_id"] == "123"


def test_ref_positive(env):
    assert gate.ref(env)["sha"] == SHA
    env.update(PUBLISH="true", BUILD_RUN_ID="123", GITHUB_REF="refs/tags/v2.0.0")
    assert gate.ref(env, "tag\n", SHA + "\n")["sha"] == SHA


@pytest.mark.parametrize(("publish", "ref", "sha", "tag_type", "commit", "code"), [
    ("true", "refs/heads/main", SHA, "tag", SHA, "ref-mismatch"),
    ("false", "refs/tags/v2.0.0", SHA, "", "", "ref-mismatch"),
    ("false", "refs/heads/main", "b" * 40, "", "", "sha-mismatch"),
    ("true", "refs/tags/v2.0.0", SHA, "commit", SHA, "tag-not-annotated"),
    ("true", "refs/tags/v2.0.0", SHA, "tag", "b" * 40, "tag-mismatch"),
])
def test_ref_negative(env, publish, ref, sha, tag_type, commit, code):
    env.update(PUBLISH=publish, BUILD_RUN_ID="123" if publish == "true" else "",
               GITHUB_REF=ref, GITHUB_SHA=sha)
    fails(code, gate.ref, env, tag_type, commit)


def test_main_head(env):
    assert gate.main_head(env, {"sha": SHA}, "")["sha"] == SHA
    fails("main-moved", gate.main_head, env, {"sha": "b" * 40}, "")
    env.update(PUBLISH="true", BUILD_RUN_ID="123")
    assert gate.main_head(env, {}, "0")["sha"] == SHA
    fails("not-main-ancestor", gate.main_head, env, {}, "1")


def test_version(env):
    assert gate.version(env, {"project": {"version": "2.0.0"}})["version"] == "2.0.0"
    fails("version-mismatch", gate.version, env, {"project": {"version": "1.3.0"}})


@pytest.fixture
def tests_data():
    return {"workflow_runs": [{"id": 55, "workflow_id": 10,
            "path": ".github/workflows/tests.yml", "head_sha": SHA, "head_branch": "main",
            "event": "push", "status": "completed", "conclusion": "success",
            "repository": {"full_name": "HakAl/scrappy"}, "run_number": 7, "run_attempt": 1}]}


def test_tests_run_positive(env, tests_data):
    assert gate.tests_run(env, {"id": 10}, tests_data) == {"tests_run_id": 55}


@pytest.mark.parametrize(("key", "value", "code"), [
    ("workflow_id", 11, "tests-run-mismatch"), ("path", "other.yml", "tests-run-mismatch"),
    ("event", "pull_request", "tests-run-mismatch"),
    ("head_branch", "other", "tests-run-mismatch"),
    ("head_sha", "b" * 40, "tests-run-mismatch"),
    ("status", "in_progress", "tests-not-success"),
    ("conclusion", "failure", "tests-not-success"),
    ("repository", {"full_name": "other/repo"}, "tests-run-mismatch"),
])
def test_tests_run_negative(env, tests_data, key, value, code):
    tests_data["workflow_runs"][0][key] = value
    fails(code, gate.tests_run, env, {"id": 10}, tests_data)


def test_tests_run_empty(env):
    fails("tests-run-mismatch", gate.tests_run, env, {"id": 10}, {"workflow_runs": []})


@pytest.mark.parametrize("rerun", [False, True])
def test_tests_newest_failure(env, tests_data, rerun):
    later = copy.deepcopy(tests_data["workflow_runs"][0])
    later.update(conclusion="failure", run_number=7 if rerun else 8, run_attempt=2)
    tests_data["workflow_runs"].append(later)
    fails("tests-not-success", gate.tests_run, env, {"id": 10}, tests_data)


def test_pypi_absent():
    assert gate.pypi_absent("404") == {"pypi": "absent"}
    fails("already-published", gate.pypi_absent, "200")
    fails("pypi-unavailable", gate.pypi_absent, "500")
    fails("pypi-unavailable", gate.pypi_absent, "404", "7")


@pytest.fixture
def build_data(env):
    env.update(PUBLISH="true", BUILD_RUN_ID="123")
    return ({"id": 20}, {"id": 123, "workflow_id": 20,
        "path": ".github/workflows/release.yml", "event": "workflow_dispatch",
        "head_branch": "main", "head_sha": SHA, "status": "completed",
        "conclusion": "success", "repository": {"full_name": "HakAl/scrappy"},
        "run_attempt": 2}, {"artifacts": [{"id": 456, "name": f"dist-2.0.0-{SHA}",
        "expired": False, "digest": "sha256:" + "c" * 64,
        "workflow_run": {"id": 123, "head_sha": SHA}}]})


def test_build_run_positive(env, build_data):
    result = gate.build_run(env, *build_data)
    assert result == {"artifact_id": 456, "artifact_digest": "sha256:" + "c" * 64,
                      "run_attempt": 2}


@pytest.mark.parametrize(("key", "value"), [
    ("id", 124), ("workflow_id", 21), ("path", "other.yml"), ("event", "push"),
    ("head_branch", "v2.0.0"), ("head_sha", "b" * 40), ("conclusion", "failure"),
    ("repository", {"full_name": "other/repo"}), ("run_attempt", None),
])
def test_build_run_negative(env, build_data, key, value):
    build_data[1][key] = value
    fails("build-run-mismatch", gate.build_run, env, *build_data)


@pytest.mark.parametrize("change", ["none", "two", "name", "expired", "run", "sha", "digest"])
def test_build_artifact_negative(env, build_data, change):
    artifacts = build_data[2]["artifacts"]
    if change == "none":
        artifacts.clear()
    elif change == "two":
        artifacts.append(copy.deepcopy(artifacts[0]))
    elif change == "run":
        artifacts[0]["workflow_run"]["id"] = 124
    elif change == "sha":
        artifacts[0]["workflow_run"]["head_sha"] = "b" * 40
    else:
        artifacts[0][change] = {"name": "wrong", "expired": True, "digest": "wrong"}[change]
    fails("artifact-mismatch", gate.build_run, env, *build_data)


@pytest.fixture
def dist(env, tmp_path):
    for name in gate.filenames("2.0.0"):
        (tmp_path / name).write_bytes(b"distribution bytes")
    gate.manifest_write(env, tmp_path)
    return tmp_path


def test_manifest_write(env, tmp_path):
    for name in gate.filenames("2.0.0"):
        (tmp_path / name).write_bytes(b"bytes")
    result = gate.manifest_write(env, tmp_path)
    assert result["wheel"] == gate.filenames("2.0.0")[0]
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["files"] == gate.hashes(tmp_path, "2.0.0")
    assert manifest["run_id"] == 123 and manifest["publish"] is False


def test_manifest_write_negative(env, tmp_path):
    fails("dist-files-mismatch", gate.manifest_write, env, tmp_path)


def test_dist_positive(env, dist):
    result = gate.dist_dir(env, dist)
    assert result["wheel_sha256"] == gate.hashes(dist, "2.0.0")[result["wheel"]]
    env.update(PUBLISH="true", BUILD_RUN_ID="123")
    assert gate.dist_dir(env, dist, "1") == result
    fails("manifest-mismatch", gate.dist_dir, env, dist, "2")


@pytest.mark.parametrize(("change", "code"), [
    ("extra", "dist-files-mismatch"), ("missing", "dist-files-mismatch"),
    ("subdir", "dist-files-mismatch"), ("tampered", "hash-mismatch"),
    ("sums-extra", "sums-mismatch"), ("sums-missing", "sums-mismatch"),
])
def test_dist_negative(env, dist, change, code):
    wheel = dist / gate.filenames("2.0.0")[0]
    sums = dist / "SHA256SUMS"
    if change == "extra":
        (dist / "extra").write_bytes(b"extra")
    elif change == "missing":
        wheel.unlink()
    elif change == "subdir":
        wheel.unlink()
        wheel.mkdir()
    elif change == "tampered":
        wheel.write_bytes(b"wrong")
    elif change == "sums-extra":
        sums.write_text(sums.read_text() + "extra\n")
    else:
        sums.write_text(sums.read_text().splitlines()[0] + "\n")
    fails(code, gate.dist_dir, env, dist)


@pytest.mark.parametrize(("key", "value"), [
    ("version", "1.3.0"), ("sha", "b" * 40), ("publish", True), ("publish", 0),
    ("run_id", 124), ("github_ref", "refs/tags/v2.0.0"), ("extra", "x"),
    ("workflow_path", "other.yml"), ("files", {}),
])
def test_dist_manifest_negative(env, dist, key, value):
    path = dist / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest[key] = value
    path.write_text(json.dumps(manifest))
    fails("manifest-mismatch", gate.dist_dir, env, dist)


@pytest.fixture
def project():
    return {"project": {"version": "2.0.0", "requires-python": ">=3.11",
            "dependencies": ["example>=1; python_version >= '3.11'"],
            "optional-dependencies": {"dev": ["helper>=2"]}}}


def archives(path, wheel_text, sdist_text=None):
    wheel, sdist = (path / name for name in gate.filenames("2.0.0"))
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("scrappy_ai-2.0.0.dist-info/METADATA", wheel_text)
    content = (sdist_text if sdist_text is not None else wheel_text).encode()
    with tarfile.open(sdist, "w:gz") as archive:
        info = tarfile.TarInfo("scrappy_ai-2.0.0/PKG-INFO")
        info.size = len(content)
        archive.addfile(info, io.BytesIO(content))
    return wheel, sdist


METADATA = ('Metadata-Version: 2.4\nName: scrappy_ai\nVersion: 2.0.0\n'
            'Requires-Python: >=3.11\n'
            'Requires-Dist: example>=1; python_version >= "3.11"\n'
            'Requires-Dist: helper>=2; extra == "dev"\n\n')


def test_metadata_positive(env, tmp_path, project):
    assert gate.metadata(env, *archives(tmp_path, METADATA), project) == {"metadata": "matched"}


@pytest.mark.parametrize("change", ["version", "python", "missing", "extra", "marker", "sdist", "filename"])
def test_metadata_negative(env, tmp_path, project, change):
    text = METADATA
    if change == "version":
        text = text.replace("Version: 2.0.0", "Version: 1.3.0")
    elif change == "python":
        text = text.replace(">=3.11\n", ">=3.12\n")
    elif change == "missing":
        text = text.replace('Requires-Dist: helper>=2; extra == "dev"\n', '')
    elif change == "extra":
        text = text.replace("\n\n", "\nRequires-Dist: unwanted>=1\n\n")
    elif change == "marker":
        text = text.replace('extra == "dev"', 'extra == "other"')
    wheel, sdist = archives(tmp_path, text, text.replace("Version: 2.0.0", "Version: 1.3.0")
                            if change == "sdist" else None)
    if change == "filename":
        wheel = wheel.rename(tmp_path / "wrong.whl")
    fails("metadata-filename" if change == "filename" else "metadata-mismatch",
          gate.metadata, env, wheel, sdist, project)


def pypi_json(dist):
    return {"urls": [{"filename": name, "digests": {"sha256": digest}}
                     for name, digest in gate.hashes(dist, "2.0.0").items()]}


def test_pypi_files_positive(env, dist):
    assert gate.pypi_files(env, pypi_json(dist), dist) == {"pypi": "matched"}
    assert gate.pypi_files(env, pypi_json(dist), dist / "SHA256SUMS") == {"pypi": "matched"}


@pytest.mark.parametrize("change", ["missing", "extra", "hash"])
def test_pypi_files_negative(env, dist, change):
    data = pypi_json(dist)
    if change == "missing":
        data["urls"].pop()
    elif change == "extra":
        data["urls"].append({"filename": "extra", "digests": {"sha256": "b" * 64}})
    else:
        data["urls"][0]["digests"]["sha256"] = "b" * 64
    fails("pypi-mismatch", gate.pypi_files, env, data, dist)
