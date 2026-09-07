"""Sandboxed read-only access to the mounted project workspace"""

import os
import re
from collections.abc import Iterator
from fnmatch import fnmatch
from pathlib import Path

import pathspec

DENIED_NAMES = (
    ".env",
    ".env.*",
    "*.env",
    "*.pem",
    "*.key",
    "id_rsa*",
    "*credential*",
    "*secret*",
)
MAX_FILE_BYTES = 100_000
MAX_LIST_ENTRIES = 500
MAX_SEARCH_MATCHES = 100
BINARY_SNIFF_BYTES = 8192

DENIED_DIRECTORIES = (
    ".git",
    "node_modules",
    ".venv",
    "__pycache__",
    ".pytest_cache",
)


class WorkspaceError(Exception):
    """Raised when a request falls outside what the workspace allows"""


class Workspace:
    """Read-only view of a project directory with escape and secret guards"""

    def __init__(self, root: Path | str,
                 max_file_bytes: int = MAX_FILE_BYTES) -> None:
        """Open a workspace rooted at a project directory

        Args:
            root: The directory the agent is allowed to read
            max_file_bytes: The most bytes one file read may return
        """
        self.root = Path(root).resolve()
        self.max_file_bytes = max_file_bytes
        self.ignored = self._load_gitignore()

    def _load_gitignore(self) -> pathspec.PathSpec:
        """Read the project's gitignore rules

        Returns:
            The compiled ignore rules, empty when there is no gitignore
        """
        gitignore = self.root / ".gitignore"
        if not gitignore.is_file():
            return pathspec.PathSpec([])
        lines = gitignore.read_text().splitlines()
        return pathspec.PathSpec.from_lines("gitignore", lines)

    def resolve(self, relative_path: str) -> Path:
        """Turn a workspace-relative path into a real path inside the root

        Args:
            relative_path: A path relative to the workspace root

        Returns:
            The absolute path inside the workspace

        Raises:
            WorkspaceError: If the path escapes the workspace root
        """
        if Path(relative_path).is_absolute():
            raise WorkspaceError(f"Path must be relative: {relative_path}")

        target = (self.root / relative_path).resolve()
        if not target.is_relative_to(self.root):
            raise WorkspaceError(f"Path escapes the workspace: {relative_path}")
        return target

    def is_visible(self, relative_path: str) -> bool:
        """Decide whether the agent is allowed to see a path

        Args:
            relative_path: A path relative to the workspace root

        Returns:
            True when the path is neither denied nor gitignored
        """
        parts = Path(relative_path).parts
        if any(part in DENIED_DIRECTORIES for part in parts):
            return False
        if any(fnmatch(parts[-1], pattern) for pattern in DENIED_NAMES):
            return False
        return not self.ignored.match_file(relative_path)

    def read_file(
        self,
        relative_path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> str:
        """Read a text file, optionally narrowed to a range of lines

        Args:
            relative_path: A path relative to the workspace root
            start_line: The first line to include, counting from one
            end_line: The last line to include, counting from one

        Returns:
            The file text, marked when it was cut short by the size cap

        Raises:
            WorkspaceError: If the file is hidden, missing, or not text
        """
        target = self._readable_file(relative_path)
        lines: list[str] = []
        size = 0
        truncated = False

        with target.open(encoding="utf-8", errors="replace") as handle:
            for number, line in enumerate(handle, start=1):
                if start_line is not None and number < start_line:
                    continue
                if end_line is not None and number > end_line:
                    break
                size += len(line)
                if size > self.max_file_bytes:
                    truncated = True
                    break
                lines.append(line)

        text = "".join(lines)
        if truncated:
            text += f"\n[truncated at {self.max_file_bytes} bytes]"
        return text

    def _readable_file(self, relative_path: str) -> Path:
        """Check that a path points at a text file the agent may read

        Args:
            relative_path: A path relative to the workspace root

        Returns:
            The absolute path of the file

        Raises:
            WorkspaceError: If the file is hidden, missing, or not text
        """
        if not self.is_visible(relative_path):
            raise WorkspaceError(f"Path is not readable: {relative_path}")

        target = self.resolve(relative_path)
        if not target.is_file():
            raise WorkspaceError(f"No such file: {relative_path}")
        if b"\x00" in target.read_bytes()[:BINARY_SNIFF_BYTES]:
            raise WorkspaceError(f"File is not text: {relative_path}")
        return target

    def list_files(self, subdir: str = ".") -> str:
        """List the files the agent is allowed to see

        Args:
            subdir: A directory relative to the workspace root

        Returns:
            One path per line, marked when cut short by the entry cap

        Raises:
            WorkspaceError: If the directory escapes the workspace
        """
        found = self._visible_files(self.resolve(subdir))
        return self._capped(found, MAX_LIST_ENTRIES, "files")

    def search_code(self, pattern: str, glob: str | None = None) -> str:
        """Find lines matching a regular expression across visible files

        Args:
            pattern: The regular expression to look for
            glob: Optional filename filter such as "*.py"

        Returns:
            One "path:line: text" hit per line, marked when cut short

        Raises:
            WorkspaceError: If the pattern is not a valid expression
        """
        try:
            expression = re.compile(pattern)
        except re.error as error:
            raise WorkspaceError(f"Invalid search pattern: {error}") from error

        return self._capped(
            self._matches(expression, glob), MAX_SEARCH_MATCHES, "matches"
        )

    def _matches(self, expression: re.Pattern,
                 glob: str | None) -> Iterator[str]:
        """Yield every matching line across the visible files

        Args:
            expression: The compiled expression to look for
            glob: Optional filename filter

        Yields:
            One "path:line: text" hit per match
        """
        for relative in self._visible_files(self.root):
            if glob and not fnmatch(relative, glob):
                continue
            try:
                text = self.read_file(relative)
            except WorkspaceError:
                continue
            for number, line in enumerate(text.splitlines(), start=1):
                if expression.search(line):
                    yield f"{relative}:{number}: {line.strip()}"

    def _visible_files(self, start: Path) -> Iterator[str]:
        """Walk a directory, skipping anything the agent may not see

        Args:
            start: The directory to walk

        Yields:
            Visible file paths relative to the workspace root
        """
        for current, directories, filenames in os.walk(start):
            base = Path(current)
            directories[:] = sorted(
                name for name in directories
                if self.is_visible(self._relative(base / name))
            )
            for name in sorted(filenames):
                relative = self._relative(base / name)
                if self.is_visible(relative):
                    yield relative

    def _relative(self, path: Path) -> str:
        """Express an absolute path relative to the workspace root

        Args:
            path: An absolute path inside the workspace

        Returns:
            The path relative to the workspace root
        """
        return str(path.relative_to(self.root))

    @staticmethod
    def _capped(found: Iterator[str], limit: int, noun: str) -> str:
        """Join results into text, stopping at a limit

        Args:
            found: The results to join
            limit: The most results to include
            noun: What the results are, used in the truncation marker

        Returns:
            One result per line, marked when cut short
        """
        kept = []
        for item in found:
            if len(kept) == limit:
                return "\n".join(kept) + f"\n[truncated at {limit} {noun}]"
            kept.append(item)
        return "\n".join(kept)
