"""ri-release-macos-signed (D36): the project's build of a .pkg or .dmg with the
Developer ID certificates in a temporary keychain, then notarized, stapled and
checked. The steps run here with bash against stubs of security, xcrun,
pkgutil, spctl and codesign, which log their arguments and fail on demand."""

import pathlib
import shutil
import subprocess

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
PIECE = ROOT / ".github/workflows/ri-release-macos-signed.yml"
SHAPE = ROOT / "skills/repo-infra/references/project-shape.md"
SECRETS = ["MACOS_CERTS_P12", "MACOS_CERTS_PASSWORD", "NOTARY_KEY_P8", "NOTARY_KEY_ID",
           "NOTARY_ISSUER"]
TEAM = "ABCDE12345"

# Each stub appends its name and arguments to $STUB_LOG and fails when
# $FAIL_<NAME> names a word of its arguments.
STUB = """#!/bin/bash
echo "{name} $*" >> "$STUB_LOG"
for word in $FAIL_{upper}; do
  case " $* " in *" $word "*) echo "{name} failed" >&2; exit 1 ;; esac
done
{body}
"""
BODIES = {
    "security": """
case "$1" in
  find-identity) case " $* " in
      *" basic "*) if [ -n "$INSTALLER" ]; then printf '  1) 4567 "%s"\\n' "$INSTALLER"; fi ;;
      *) printf '  1) 0123 "%s"\\n' "$IDENTITY" ;;
    esac ;;
  list-keychains) echo '    "/Users/runner/Library/Keychains/login.keychain-db"' ;;
esac""",
    "xcrun": """
case "$1 $2" in
  "notarytool submit") n=$(grep -c "notarytool submit" "$STUB_LOG"); printf '{"id": "sub-%s"}\\n' "$n" ;;
  "notarytool wait")
    printf '{"id": "%s", "status": "%s"}\\n' "$3" "${NOTARY_STATUS:-Accepted}"
    [ "${NOTARY_STATUS:-Accepted}" = Accepted ] ;;
esac""",
    "pkgutil": """
echo "Status: signed by a developer certificate issued by Apple for distribution"
echo "   1. Developer ID Installer: $PKG_SIGNER"
echo "   2. Developer ID Certification Authority\"""",
    "codesign": """
if [ "$1" = -dv ]; then
  echo "Executable=$3" >&2
  echo "TeamIdentifier=$DMG_TEAM" >&2
  for i in $(seq 200); do echo "Sealed Resources line $i" >&2; done
fi
exit 0""",
    "spctl": "",
    "uuidgen": "echo 0000",
}


def doc():
    return yaml.safe_load(PIECE.read_text(encoding="utf-8"))


def job():
    return doc()["jobs"]["macos"]


def step(name):
    return next(s for s in job()["steps"] if s.get("name") == name)


@pytest.fixture
def run(tmp_path):
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is not installed")
    if shutil.which("jq") is None:
        pytest.skip("jq is not installed")
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    for name, body in BODIES.items():
        path = stubs / name
        path.write_text(STUB.format(name=name, upper=name.upper(), body=body))
        path.chmod(0o755)
    temp, work = tmp_path / "runner-temp", tmp_path / "work"
    temp.mkdir()
    work.mkdir()
    log, output = tmp_path / "stub.log", tmp_path / "output"
    log.touch()
    output.touch()

    def go(name, **env):
        base = {"PATH": f"{stubs}:/usr/bin:/bin", "RUNNER_TEMP": str(temp),
                "GITHUB_OUTPUT": str(output), "STUB_LOG": str(log),
                "IDENTITY": f"Developer ID Application: Example Ltd ({TEAM})",
                "PKG_SIGNER": f"Example Ltd ({TEAM})", "DMG_TEAM": TEAM}
        base["INSTALLER"] = f"Developer ID Installer: Example Ltd ({TEAM})"
        base.update({secret: "" for secret in SECRETS})
        base["ASSETS"] = "build/*.pkg"
        base.update(env)
        proc = subprocess.run([bash, "-c", step(name)["run"]], cwd=work, env=base,
                              capture_output=True, text=True)
        proc.log = log.read_text().splitlines()
        proc.output = dict(line.split("=", 1) for line in output.read_text().splitlines())
        return proc

    go.temp, go.work = temp, work
    return go


FULL = {"MACOS_CERTS_P12": "cDEy", "MACOS_CERTS_PASSWORD": "pw", "NOTARY_KEY_P8": "key",
        "NOTARY_KEY_ID": "KEYID", "NOTARY_ISSUER": "issuer"}


def test_the_secrets_are_required_and_named_as_the_repository_secrets():
    secrets = doc()[True]["workflow_call"]["secrets"]
    assert list(secrets) == SECRETS
    assert all(s["required"] for s in secrets.values())
    text = PIECE.read_text(encoding="utf-8")
    for name in SECRETS:
        assert f"#       {name}: ${{{{ secrets.{name} }}}}" in text


def test_no_input_is_spliced_into_a_script():
    for s in job()["steps"]:
        assert "${{" not in s.get("run", ""), s.get("name")


def test_the_build_runs_the_command_from_the_environment():
    build = step("Build")
    assert build["run"] == 'eval "$BUILD"'
    assert build["env"]["BUILD"] == "${{ inputs.build }}"
    assert "MACOS_SIGNING" not in build["env"]
    assert build["env"]["MACOS_TEAM_ID"] == "${{ steps.certs.outputs.team }}"


def test_without_the_secrets_the_piece_refuses_to_build(run):
    proc = run("Import the signing certificates")
    assert proc.returncode == 1
    assert ("::error::MACOS_CERTS_P12 MACOS_CERTS_PASSWORD NOTARY_KEY_P8 NOTARY_KEY_ID "
            "NOTARY_ISSUER is empty") in proc.stdout
    assert "records the macos-signed exception" in proc.stdout
    assert proc.log == []


def test_there_is_no_unsigned_mode():
    text = PIECE.read_text(encoding="utf-8")
    assert "REQUIRE_SIGNED_RELEASES" not in text
    assert "vars." not in text
    assert all("if" not in s for s in job()["steps"][:-2])


def test_a_partial_set_of_secrets_names_what_is_missing(run):
    proc = run("Import the signing certificates", MACOS_CERTS_P12="cDEy", NOTARY_KEY_P8="key")
    assert proc.returncode == 1
    assert ("::error::MACOS_CERTS_PASSWORD NOTARY_KEY_ID NOTARY_ISSUER is empty") in proc.stdout
    assert proc.log == []


def test_a_p12_that_is_not_base64_names_the_secret(run):
    proc = run("Import the signing certificates", **{**FULL, "MACOS_CERTS_P12": "not base64!"})
    assert proc.returncode == 1
    assert "::error::MACOS_CERTS_P12 is not base64" in proc.stdout
    assert not any(line.startswith("security import") for line in proc.log)


def test_the_key_files_are_private(run):
    proc = run("Import the signing certificates", **FULL)
    assert proc.returncode == 0, proc.stderr
    assert (run.temp / "notary.p8").stat().st_mode & 0o077 == 0


def test_a_wrong_password_names_the_secret_before_the_build(run):
    proc = run("Import the signing certificates", FAIL_SECURITY="import", **FULL)
    assert proc.returncode == 1
    assert "does not open with MACOS_CERTS_PASSWORD" in proc.stdout
    assert not any(line.startswith("xcrun") for line in proc.log)


def test_a_p12_without_the_application_identity_is_refused(run):
    proc = run("Import the signing certificates", IDENTITY="Apple Development: X (ABCDE12345)",
               **FULL)
    assert proc.returncode == 1
    assert "holds no Developer ID Application certificate" in proc.stdout


def test_a_pkg_needs_the_installer_identity_before_the_build(run):
    proc = run("Import the signing certificates", INSTALLER="", **FULL)
    assert proc.returncode == 1
    assert ("::error::assets names a .pkg, but MACOS_CERTS_P12 holds no Developer ID Installer "
            f"certificate of team {TEAM}") in proc.stdout
    assert not any(line.startswith("xcrun") for line in proc.log)


def test_the_installer_identity_must_be_of_the_same_team(run):
    proc = run("Import the signing certificates",
               INSTALLER="Developer ID Installer: Someone (ZZZZZ99999)", **FULL)
    assert proc.returncode == 1
    assert "holds no Developer ID Installer certificate" in proc.stdout


def test_an_image_needs_no_installer_identity(run):
    proc = run("Import the signing certificates", INSTALLER="", ASSETS="build/*.dmg", **FULL)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_rejected_notary_credentials_fail_before_the_build(run):
    proc = run("Import the signing certificates", FAIL_XCRUN="history", **FULL)
    assert proc.returncode == 1
    assert "notarytool does not accept NOTARY_KEY_P8 with NOTARY_KEY_ID" in proc.stdout


def test_the_certificates_go_into_a_temporary_keychain_and_the_team_is_read(run):
    proc = run("Import the signing certificates", **FULL)
    assert proc.returncode == 0, proc.stderr
    assert proc.output == {"team": TEAM}
    keychain = f"{run.temp}/signing.keychain-db"
    assert f"security create-keychain -p 0000 {keychain}" in proc.log
    assert any(line.startswith(f"security import {run.temp}/certs.p12 -k {keychain} -P pw")
               for line in proc.log)
    assert any(line.startswith("security set-key-partition-list") for line in proc.log)
    assert not (run.temp / "certs.p12").exists()
    assert (run.temp / "notary.p8").read_text() == "key"
    assert (f"xcrun notarytool history --key {run.temp}/notary.p8 --key-id KEYID "
            "--issuer issuer") in proc.log


def test_the_assets_are_collected_from_every_pattern(run):
    (run.work / "build").mkdir()
    for name in ("App-1.0.pkg", "App-1.0.dmg"):
        (run.work / "build" / name).write_text("x")
    proc = run("Collect the assets", ASSETS="build/*.pkg\nbuild/App-1.0.dmg")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert sorted(p.name for p in (run.temp / "dist").iterdir()) == ["App-1.0.dmg", "App-1.0.pkg"]


def test_a_pattern_without_a_file_fails(run):
    proc = run("Collect the assets", ASSETS="build/*.pkg")
    assert proc.returncode == 1
    assert "::error::assets names build/*.pkg, but the build wrote no file there" in proc.stdout


def test_a_plain_path_without_a_file_fails_with_the_same_error(run):
    proc = run("Collect the assets", ASSETS="build/App-1.0.pkg")
    assert proc.returncode == 1
    assert ("::error::assets names build/App-1.0.pkg, but the build wrote no file there"
            in proc.stdout)


def test_two_assets_of_the_same_name_are_refused(run):
    for arch in ("arm64", "x86_64"):
        (run.work / arch).mkdir()
        (run.work / arch / "App.pkg").write_text(arch)
    proc = run("Collect the assets", ASSETS="arm64/App.pkg x86_64/App.pkg")
    assert proc.returncode == 1
    assert "::error::two assets are named App.pkg" in proc.stdout


def test_a_file_that_cannot_be_stapled_is_refused(run):
    (run.work / "app.zip").write_text("x")
    proc = run("Collect the assets", ASSETS="app.zip")
    assert proc.returncode == 1
    assert "::error::app.zip is neither a .pkg nor a .dmg" in proc.stdout


def dist(run, *names):
    (run.temp / "dist").mkdir()
    for name in names:
        (run.temp / "dist" / name).write_text("x")


def test_every_asset_is_submitted_before_any_is_waited_for(run):
    dist(run, "App-1.0.pkg", "App-1.0.dmg")
    proc = run("Notarize and staple", NOTARY_KEY_ID="KEYID", NOTARY_ISSUER="issuer")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    creds = f"--key {run.temp}/notary.p8 --key-id KEYID --issuer issuer --output-format json"
    files = [f"{run.temp}/dist/App-1.0.{ext}" for ext in ("dmg", "pkg")]
    calls = [line for line in proc.log if line.startswith("xcrun")]
    assert calls == [f"xcrun notarytool submit {files[0]} {creds}",
                     f"xcrun notarytool submit {files[1]} {creds}",
                     f"xcrun notarytool wait sub-1 {creds}",
                     f"xcrun stapler staple {files[0]}",
                     f"xcrun notarytool wait sub-2 {creds}",
                     f"xcrun stapler staple {files[1]}"]


def test_a_rejected_submission_prints_the_log_and_fails(run):
    dist(run, "App-1.0.pkg")
    proc = run("Notarize and staple", NOTARY_STATUS="Invalid", NOTARY_KEY_ID="K",
               NOTARY_ISSUER="I")
    assert proc.returncode == 1
    assert "::error::notarization of App-1.0.pkg ended with Invalid" in proc.stdout
    assert any(line.startswith("xcrun notarytool log sub-1") for line in proc.log)
    assert not any("stapler" in line for line in proc.log)


def test_a_failed_submit_is_reported_not_swallowed(run):
    dist(run, "App-1.0.pkg")
    proc = run("Notarize and staple", FAIL_XCRUN="submit", NOTARY_KEY_ID="K",
               NOTARY_ISSUER="I")
    assert proc.returncode == 1
    assert "::error::notarytool did not accept App-1.0.pkg for notarization" in proc.stdout


def test_the_check_passes_a_package_and_an_image_of_the_team(run):
    dist(run, "App-1.0.pkg", "App-1.0.dmg")
    proc = run("Check the signatures", TEAM=TEAM)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    pkg, dmg = (f"{run.temp}/dist/App-1.0.{ext}" for ext in ("pkg", "dmg"))
    assert f"spctl --assess --type install -vv {pkg}" in proc.log
    assert f"spctl --assess --type open --context context:primary-signature -vv {dmg}" in proc.log
    assert f"xcrun stapler validate {pkg}" in proc.log
    assert f"xcrun stapler validate {dmg}" in proc.log


def test_the_check_refuses_a_package_of_another_team(run):
    dist(run, "App-1.0.pkg")
    proc = run("Check the signatures", TEAM=TEAM, PKG_SIGNER="Someone (ZZZZZ99999)")
    assert proc.returncode == 1
    assert f"is not signed by a Developer ID Installer of team {TEAM}" in proc.stdout


def test_the_check_refuses_an_image_of_another_team(run):
    dist(run, "App-1.0.dmg")
    proc = run("Check the signatures", TEAM=TEAM, DMG_TEAM="ZZZZZ99999")
    assert proc.returncode == 1
    assert f"is not signed by team {TEAM}" in proc.stdout


def test_a_failed_staple_check_fails_the_job(run):
    dist(run, "App-1.0.pkg")
    proc = run("Check the signatures", TEAM=TEAM, FAIL_XCRUN="validate")
    assert proc.returncode == 1


def test_the_keychain_and_the_key_are_removed_even_after_a_failure():
    cleanup = step("Remove the keychain and the notary key")
    assert cleanup["if"] == "always()"
    assert "security delete-keychain" in cleanup["run"]
    assert "notary.p8" in cleanup["run"]
    names = [s.get("name") for s in job()["steps"]]
    assert names.index("Remove the keychain and the notary key") < len(names) - 1


def test_the_upload_is_the_release_asset_artifact():
    upload = job()["steps"][-1]
    assert upload["uses"] == "actions/upload-artifact@v7"
    assert upload["with"] == {"name": "release-asset-macos", "path": "${{ runner.temp }}/dist/*",
                              "if-no-files-found": "error"}


def test_the_shape_names_the_piece():
    assert "`ri-release-macos-signed`" in SHAPE.read_text(encoding="utf-8")
