"""Tests for sandboxed access to the mounted project workspace"""

import pytest

from workspace.sandbox import Workspace, WorkspaceError
from workspace.tools import build_tools, build_workspace_tools


@pytest.fixture(name="project")
def project_fixture(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("import os\nprint('hello')\n")
    (tmp_path / "docker").mkdir()
    (tmp_path / "docker" / ".env").write_text("GEMINI_KEY=real-secret\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "left-pad.js").write_text("module.exports\n")
    (tmp_path / ".gitignore").write_text("build/\n")
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "out.js").write_text("compiled\n")
    return Workspace(tmp_path)


def test_resolve_accepts_a_path_inside_the_workspace(project):
    assert project.resolve("src/main.py").name == "main.py"


@pytest.mark.parametrize("escape", ["../../etc/passwd", "/etc/passwd"])
def test_resolve_rejects_paths_outside_the_workspace(project, escape):
    with pytest.raises(WorkspaceError):
        project.resolve(escape)


def test_resolve_rejects_a_symlink_pointing_outside(project, tmp_path):
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("secret\n")
    (tmp_path / "src" / "link.txt").symlink_to(outside)

    with pytest.raises(WorkspaceError):
        project.resolve("src/link.txt")


@pytest.mark.parametrize("path,visible", [
    ("src/main.py", True),
    ("docker/.env", False),
    ("node_modules/left-pad.js", False),
    ("build/out.js", False),
])
def test_visibility_hides_secrets_dependencies_and_ignored_files(
    project, path, visible
):
    assert project.is_visible(path) is visible


def test_read_file_returns_the_requested_lines(project):
    assert project.read_file("src/main.py") == "import os\nprint('hello')\n"
    assert project.read_file("src/main.py", start_line=2) == "print('hello')\n"


def test_read_file_truncates_a_large_file_and_says_so(project, tmp_path):
    (tmp_path / "src" / "big.py").write_text("x = 1\n" * 40000)

    result = project.read_file("src/big.py")

    assert "truncated" in result
    assert len(result) < 120000


def test_read_file_refuses_anything_that_is_not_readable_text(project,
                                                              tmp_path):
    (tmp_path / "src" / "logo.png").write_bytes(b"\x89PNG\x00\x01")

    with pytest.raises(WorkspaceError):
        project.read_file("src/logo.png")
    with pytest.raises(WorkspaceError):
        project.read_file("src/nope.py")


def test_list_files_shows_source_and_hides_secrets(project):
    listing = project.list_files()

    assert "src/main.py" in listing
    assert ".env" not in listing
    assert "node_modules" not in listing


def test_list_files_truncates_a_huge_tree_and_says_so(project, tmp_path):
    for number in range(600):
        (tmp_path / "src" / f"file{number}.py").write_text("x = 1\n")

    assert "truncated" in project.list_files()


def test_search_code_reports_path_and_line(project):
    assert "src/main.py:1" in project.search_code("import os")


def test_search_code_never_reads_denied_files(project):
    assert "GEMINI_KEY" not in project.search_code("GEMINI_KEY")


def test_search_code_reports_an_invalid_pattern(project):
    with pytest.raises(WorkspaceError):
        project.search_code("unclosed(")


def test_tools_report_refusals_instead_of_raising(project):
    tools = {each.name: each for each in build_tools(project)}

    result = tools["read_file"].invoke({"path": "docker/.env"})

    assert result.startswith("Error")
    assert "GEMINI_KEY" not in result


def test_tools_exist_only_when_a_project_is_mounted(tmp_path):
    assert build_workspace_tools(tmp_path / "not_mounted") is None
    assert len(build_workspace_tools(tmp_path)) == 3


def test_the_file_cap_can_be_sized_for_the_model(project, tmp_path):
    (tmp_path / "src" / "big.py").write_text("x = 1\n" * 1000)
    small = Workspace(tmp_path, max_file_bytes=200)

    assert "truncated" in small.read_file("src/big.py")
    assert "truncated" not in project.read_file("src/big.py")
