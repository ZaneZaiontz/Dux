"""Code reading tools the agent calls while investigating a problem"""

import os
from collections.abc import Callable

from langchain_core.tools import BaseTool, tool

from workspace.sandbox import Workspace, WorkspaceError

DEFAULT_WORKSPACE_ROOT = "/workspace"


def open_workspace(root: str | None = None) -> Workspace:
    """Open the project directory mounted into the container

    Args:
        root: The directory to read, defaulting to the mounted workspace

    Returns:
        A workspace rooted at that directory
    """
    return Workspace(
        root or os.environ.get("DUX_WORKSPACE_ROOT", DEFAULT_WORKSPACE_ROOT)
    )


def build_workspace_tools(root: str | None = None) -> list[BaseTool] | None:
    """Build the code tools when a project is actually mounted

    Args:
        root: The directory to read, defaulting to the mounted workspace

    Returns:
        The tools, or None when no project directory is present
    """
    workspace = open_workspace(root)
    return build_tools(workspace) if workspace.root.is_dir() else None


def build_tools(workspace: Workspace) -> list[BaseTool]:
    """Build the tools the agent uses to read a project

    Args:
        workspace: The project the tools are allowed to read

    Returns:
        The tools, ready to bind to a chat model
    """

    @tool
    def list_files(subdir: str = ".") -> str:
        """List the project's files. Start here to learn the layout.

        Secrets, dependencies and ignored files are never listed.
        """
        return _reported(workspace.list_files, subdir)

    @tool
    def search_code(pattern: str, glob: str | None = None) -> str:
        """Search file contents for a regular expression.

        Returns matching lines as "path:line: text". Narrow the search with
        a glob such as "*.py" when you know the file type.
        """
        return _reported(workspace.search_code, pattern, glob)

    @tool
    def read_file(path: str, start_line: int | None = None,
                  end_line: int | None = None) -> str:
        """Read a text file, optionally a range of lines.

        Prefer a line range for large files. Line numbers start at one.
        """
        return _reported(workspace.read_file, path, start_line, end_line)

    return [list_files, search_code, read_file]


def _reported(action: Callable[..., str], *args) -> str:
    """Run a workspace call, turning refusals into text the model can read

    Args:
        action: The workspace method to call
        args: The arguments to pass through

    Returns:
        The result, or an explanation of why the request was refused
    """
    try:
        return action(*args)
    except WorkspaceError as error:
        return f"Error: {error}"
