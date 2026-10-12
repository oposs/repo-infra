"""references/project-shape.md (D32): every rule complete, every id once, and
the snippets other files rely on."""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
SHAPE = ROOT / "skills/repo-infra/references/project-shape.md"
RULES = {"readme-current", "badges", "install-text", "writing-style", "man-page", "demo",
         "screenshot", "native-targets", "source-archive", "linux-packages", "homebrew"}
FIELDS = ("Trigger:", "Requires:", "Verify:", "Met by:")


def text():
    return SHAPE.read_text(encoding="utf-8")


def section(title):
    return text().split(f"\n## {title}\n", 1)[1].split("\n## ", 1)[0]


def fenced(title, language):
    return re.findall(rf"```{language}\n(.*?)```", section(title), re.S)


def triggers():
    return re.findall(r"^- `([a-z][a-z ]*)`:", section("Triggers"), re.M)


def rules():
    parts = re.split(r"^### ", section("Rules"), flags=re.M)[1:]
    return [(part.splitlines()[0], part) for part in parts]


def test_every_rule_heading_is_one_id():
    for heading, _ in rules():
        assert re.fullmatch(r"`[a-z][a-z0-9-]*`", heading), heading


def test_the_rule_ids_are_unique_and_complete():
    ids = [heading.strip("`") for heading, _ in rules()]
    assert len(ids) == len(set(ids))
    assert set(ids) == RULES


def test_every_rule_states_each_field_once_in_order():
    for heading, body in rules():
        starts = [line.split(":", 1)[0] + ":" for line in body.splitlines()
                  if line.startswith(FIELDS)]
        assert starts == list(FIELDS), heading


def test_every_rule_names_a_trigger_the_file_defines():
    known = set(triggers())
    assert known == {"every project", "has a command line", "runs in a terminal",
                     "has a web or graphical interface", "is installed by users"}
    for heading, body in rules():
        trigger = re.search(r"^Trigger: (.+)\.$", body, re.M).group(1)
        assert trigger in known, f"{heading}: {trigger}"


def test_the_badges_link_the_ci_workflow_and_the_latest_release():
    (block,) = fenced("Badges", "markdown")
    assert "https://github.com/<owner>/<repo>/actions/workflows/ci.yml/badge.svg" in block
    assert "https://img.shields.io/github/v/release/<owner>/<repo>" in block
    assert "https://github.com/<owner>/<repo>/releases/latest" in block


def test_the_install_snippets_settle_the_differences_of_issue_57():
    blocks = "\n".join(fenced("Install snippets", "sh"))
    assert "sudo install -d -m 0755 /etc/apt/keyrings" in blocks
    assert "/etc/apt/keyrings/gitea-<gitea-owner>.asc" in blocks
    assert "-o /etc/yum.repos.d/<gitea-owner>.repo" in blocks
    assert "config-manager" not in blocks
    assert "/debian <distribution> <component>" in blocks
    assert "<name>" not in text()
    assert "<gitea-url>/api/packages/<gitea-owner>/rpm/<group>.repo" in text()
    assert "brew trust --formula <owner>/<repo>/<bin>" in blocks
    assert "mise use -g github:<owner>/<repo>" in blocks


def test_the_formula_template_carries_every_marker_and_installs_every_man_page():
    (ruby,) = fenced("Formula template", "ruby")
    for marker in ("# mac-arm", "# mac-x86", "# linux-x86", "# linux-arm",
                   "# BOTTLE-START", "# BOTTLE-END"):
        assert ruby.count(marker) == 1, marker
    lines = ruby.splitlines()
    shas = [i for i, line in enumerate(lines) if re.search(r'sha256 "0{64}" # ', line)]
    assert len(shas) == 4
    for i in shas:
        assert lines[i - 1].strip().startswith(
            'url "https://github.com/<owner>/<repo>/releases/download/v#{version}/<bin>-#{version}-')
    assert ('Dir["man/*.[1-9]"].each { |page| (man/"man#{page[-1]}").install page }'
            in ruby)


def test_the_prose_follows_the_house_style():
    prose = re.sub(r"```.*?```", "", text(), flags=re.S)
    assert "e.g." not in prose
    for heading in re.findall(r"^#{2,6} (.+)$", prose, re.M):
        later = [w for w in heading.split()[1:] if not w.startswith("`")]
        assert all(not w[0].isupper() for w in later), heading


def test_the_rust_rules_name_the_release_pieces():
    bodies = {heading.strip("`"): body for heading, body in rules()}
    assert "`ri-release-rust-binaries`" in bodies["native-targets"]
    assert "`ri-release-nfpm`" in bodies["linux-packages"]
    assert "`ri-release-homebrew`" in bodies["homebrew"]
    assert "`ri-release-homebrew` rewrites" in section("Formula template")
