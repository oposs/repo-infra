"""publish-gitea-packages (D27)."""

import json
import pathlib

import yaml

from repo_infra.assemble import assemble_publish, block_job_ids

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/repo-infra/assets"
MANIFEST = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
BLOCK = "publish-gitea-packages"


def workflow():
    return yaml.safe_load(assemble_publish(ASSETS, [BLOCK], MANIFEST))


def job():
    return workflow()["jobs"][BLOCK]


def script():
    return next(s["with"]["script"] for s in job()["steps"] if "script" in s.get("with", {}))


def test_the_block_declares_its_one_job():
    text = (ASSETS / f"publish/{BLOCK}.yml").read_text(encoding="utf-8")
    assert block_job_ids(text) == MANIFEST["publish_blocks"][BLOCK]["jobs"] == [BLOCK]


def test_a_failed_upload_keeps_the_release_a_draft():
    # Blocking: a version public on GitHub but absent from apt and dnf is the
    # inconsistency worth preventing.
    assert BLOCK in workflow()["jobs"]["finalize"]["needs"]


def test_it_waits_for_publish_and_honours_the_guard():
    assert job()["needs"] == ["publish"]
    assert job()["if"] == "needs.publish.outputs.release_id != ''"


def test_it_can_see_the_draft():
    # A token that cannot push cannot see a draft release or its assets.
    assert job()["permissions"] == {"contents": "write"}


def test_the_credential_reaches_the_script_only_through_env():
    step = next(s for s in job()["steps"] if "script" in s.get("with", {}))
    assert step["env"] == {
        "GITEA_PACKAGE_TOKEN": "${{ secrets.GITEA_PACKAGE_TOKEN }}",
        "GITEA_PACKAGE_USER": "${{ vars.GITEA_PACKAGE_USER }}",
    }
    assert "secrets." not in script()


def test_it_refuses_before_uploading_anything():
    s = script()
    for guard in ("packageConfig", "missingCredentials", "no .deb or .rpm"):
        assert s.index(guard) < s.index("method: 'PUT'"), guard


def test_a_conflict_is_judged_not_ignored():
    s = script()
    assert "res.status === 409" in s and "conflictVerdict" in s


def test_a_files_listing_that_is_not_an_array_fails_with_the_status():
    # conflictVerdict would throw on an error object; the message must name
    # package, version and HTTP status instead.
    s = script()
    assert "Array.isArray(files)" in s
    assert s.index("Array.isArray(files)") < s.index("gitea.conflictVerdict")
    assert "pkg.version" in s and "list.status" in s


def test_a_package_name_that_does_not_parse_fails_before_any_upload():
    s = script()
    assert "unparsable" in s and "Expected name_version_arch.deb" in s
    assert s.index("unparsable") < s.index("method: 'PUT'")


def test_the_derived_basic_credential_is_masked():
    s = script()
    assert "core.setSecret(authorization)" in s
    assert s.index("core.setSecret(authorization)") < s.index("method: 'PUT'")


def test_every_job_has_a_timeout():
    assert isinstance(job()["timeout-minutes"], int)
