"""ri-release-distro-packages (D38). lib/distro.js holds the plan and
lib/distro-leg.sh the leg; here: the piece's structure and what it hands to
them."""

import pathlib

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
PIECE = ROOT / ".github/workflows/ri-release-distro-packages.yml"
NFPM_PIECE = ROOT / ".github/workflows/ri-release-nfpm.yml"
LIB = ROOT / ".github/workflows/lib"


def load(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def doc():
    return load(PIECE)


def steps(job):
    return {s.get("name") or s.get("uses"): s for s in doc()["jobs"][job]["steps"]}


def test_the_header_names_the_piece_v2():
    text = PIECE.read_text(encoding="utf-8")
    assert text.startswith("# repo-infra: ri-release-distro-packages v2\n")
    header = text.split("\n\n", 1)[0]
    assert "# Choose: The program links system libraries, so one static build cannot serve every distribution (D38).\n" in header


def test_the_inputs_and_their_defaults():
    inputs = doc()[True]["workflow_call"]["inputs"]
    assert {k: v.get("default") for k, v in inputs.items()} == {
        "version": None, "ref": None, "repository": "${{ github.repository }}",
        "submodules": "false", "directory": ".", "config": "nfpm.yaml",
        "packagers": "{}", "distributions": ""}
    assert [k for k, v in inputs.items() if v["required"]] == ["version", "ref"]


def test_nfpm_is_the_pin_of_ri_release_nfpm():
    ours = steps("packages")["Install nfpm"]["env"]
    theirs = {s.get("name"): s for s in load(NFPM_PIECE)["jobs"]["packages"]["steps"]}["Install nfpm"]["env"]
    assert ours["NFPM_VERSION"] == theirs["NFPM_VERSION"]
    assert ours["NFPM_SHA256"] == theirs["NFPM_SHA256"]
    assert ours["NFPM_SHA256_ARM64"]


def test_the_matrix_comes_from_the_plan_and_does_not_fail_fast():
    job = doc()["jobs"]["packages"]
    assert job["needs"] == ["plan", "man"]
    assert job["strategy"] == {"fail-fast": False,
                               "matrix": "${{ fromJSON(needs.plan.outputs.matrix) }}"}
    assert job["runs-on"] == "${{ matrix.os }}"
    assert job["timeout-minutes"] == 120
    plan = steps("plan")["Choose the releases"]
    assert plan["env"] == {"DISTRIBUTIONS": "${{ inputs.distributions }}"}
    assert "distroPlan(process.env.DISTRIBUTIONS)" in plan["with"]["script"]
    assert "core.setFailed(error.message)" in plan["with"]["script"]


def test_every_input_reaches_the_library_through_env():
    leg = steps("packages")["Build the package"]
    assert leg["env"] == {
        "ENGINE": "docker", "IMAGE": "${{ matrix.image }}", "DISTRO": "${{ matrix.distro }}",
        "ARCH": "${{ matrix.arch }}", "VERSION": "${{ inputs.version }}",
        "DIRECTORY": "${{ inputs.directory }}", "CONFIG": "${{ inputs.config }}",
        "PACKAGERS": "${{ inputs.packagers }}",
        "LIB": "${{ github.workspace }}/.repo-infra/.github/workflows/lib"}
    assert "${{" not in leg["run"]
    assert "distro-leg.sh" in leg["run"]
    assert (LIB / "distro-leg.sh").is_file()


def test_the_artifact_name_carries_distro_and_arch():
    upload = steps("packages")["actions/upload-artifact@v7"]
    assert upload["with"]["name"] == "release-asset-packages-${{ matrix.distro }}-${{ matrix.arch }}"
    assert upload["with"]["path"] == "packages/"
    assert upload["with"]["if-no-files-found"] == "error"


def test_the_man_job_builds_only_when_man_mk_exists():
    job = doc()["jobs"]["man"]
    assert job["outputs"] == {"present": "${{ steps.detect.outputs.present }}"}
    detect = steps("man")["Look for the man page build"]
    assert detect["id"] == "detect"
    assert "build/man.mk" in detect["run"]
    assert "${{" not in detect["run"]
    for name in ("Install pandoc", "Build the man pages", "actions/upload-artifact@v7"):
        assert steps("man")[name]["if"] == "${{ steps.detect.outputs.present == 'true' }}"
    assert steps("man")["actions/upload-artifact@v7"]["with"]["name"] == "man-pages"


def test_the_packages_job_fetches_the_man_pages_into_the_directory():
    fetch = steps("packages")["Fetch the man pages"]
    assert fetch["if"] == "${{ needs.man.outputs.present == 'true' }}"
    assert fetch["with"] == {"name": "man-pages", "path": "${{ inputs.directory }}/man"}


def test_no_docker_driver_is_set_up():
    text = PIECE.read_text(encoding="utf-8")
    assert "setup-buildx" not in text and "docker/" not in text.replace("docker.io", "")


def test_collect_needs_packages_and_checks_the_plan():
    job = doc()["jobs"]["collect"]
    assert job["needs"] == ["plan", "packages"]
    assert job["if"] == "${{ !cancelled() }}"
    download = steps("collect")["actions/download-artifact@v8"]
    assert download["with"]["pattern"] == "release-asset-packages-*"
    check = steps("collect")["Check every leg made one package"]
    assert check["env"] == {"MATRIX": "${{ needs.plan.outputs.matrix }}"}
    assert "${{" not in check["run"]
    # A missing artifact folder must reach the ::error:: line: under pipefail a
    # failing find inside the pipeline would end the script silently.
    assert '[ -d "collected/release-asset-packages-$leg" ]' in check["run"]


def test_permissions_are_contents_read():
    assert doc()["permissions"] == {"contents": "read"}


GATE = ROOT / ".github/workflows/gate-distro-packages.yml"


def test_the_gate_calls_the_piece_on_the_fixture():
    """Dispatched by hand, it builds tests/fixtures/distro-hello with the piece
    and the library of the dispatched commit, every release the piece knows."""
    gate = load(GATE)
    # PyYAML reads the bare key on as True.
    assert gate[True] == {"workflow_dispatch": None}
    assert gate["permissions"] == {"contents": "read"}
    assert gate["jobs"] == {"packages": {
        "uses": "./.github/workflows/ri-release-distro-packages.yml",
        "with": {
            "repository": "${{ github.repository }}",
            "ref": "${{ github.sha }}",
            "directory": "tests/fixtures/distro-hello",
            "version": "0.0.0",
        },
    }}
