"""Controlled and validated Windows filesystem operations."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.execution.policy import default_policy


class ControlledFileSystem:
    """Safe filesystem operations bounded by workspace policy."""

    def __init__(self, policy=default_policy) -> None:
        self.policy = policy

    def resolve_path(self, raw_path: str | None) -> Path:
        """Resolve aliases like Desktop, Downloads, ~, or project relative paths."""
        if not raw_path or not raw_path.strip():
            return Path(r"C:\kirtan\IRIS").resolve()

        clean = raw_path.strip().replace("/", "\\")
        home = Path.home().resolve()

        if clean == "~" or clean.lower() == "home":
            return home
        if clean.startswith("~\\"):
            return (home / clean[2:]).resolve()

        alias_map = {
            "desktop": home / "Desktop",
            "downloads": home / "Downloads",
            "documents": home / "Documents",
            "iris": Path(r"C:\kirtan\IRIS"),
        }
        first_segment = clean.split("\\")[0].lower()
        if first_segment in alias_map:
            rest = clean[len(first_segment):].lstrip("\\")
            return (alias_map[first_segment] / rest).resolve()

        cand = Path(clean)
        if cand.is_absolute():
            return cand.resolve()

        return (Path(r"C:\kirtan\IRIS") / clean).resolve()

    def list_directory(
        self,
        directory: str | None = None,
        max_items: int = 50,
    ) -> dict[str, Any]:
        """List files and subdirectories within permitted paths."""
        target = self.resolve_path(directory)
        ok, err = self.policy.validate_path(target, write=False)
        if not ok:
            return {"success": False, "error": err, "entries": []}

        if not target.exists():
            return {"success": False, "error": f"Directory '{target}' does not exist.", "entries": []}

        if not target.is_dir():
            return {"success": False, "error": f"Path '{target}' is a file, not a directory.", "entries": []}

        entries = []
        try:
            for item in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                entries.append({
                    "name": item.name,
                    "path": str(item),
                    "type": "directory" if item.is_dir() else "file",
                    "size_bytes": item.stat().st_size if item.is_file() else None,
                    "modified_time": item.stat().st_mtime,
                })
                if len(entries) >= max_items:
                    break
            return {
                "success": True,
                "directory": str(target),
                "count": len(entries),
                "entries": entries,
            }
        except Exception as exc:
            return {"success": False, "error": str(exc), "entries": []}

    def read_file(
        self,
        file_path: str,
        max_lines: int = 150,
        offset_lines: int = 0,
    ) -> dict[str, Any]:
        """Read text content of a file within permitted paths."""
        target = self.resolve_path(file_path)
        ok, err = self.policy.validate_path(target, write=False)
        if not ok:
            return {"success": False, "error": err, "content": ""}

        if not target.exists() or not target.is_file():
            return {"success": False, "error": f"File '{target}' does not exist.", "content": ""}

        try:
            lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
            total_lines = len(lines)
            selected = lines[offset_lines : offset_lines + max_lines]
            preview = "\n".join(selected)

            return {
                "success": True,
                "file_path": str(target),
                "total_lines": total_lines,
                "read_lines": len(selected),
                "offset": offset_lines,
                "content": preview,
            }
        except Exception as exc:
            return {"success": False, "error": str(exc), "content": ""}

    def write_file(
        self,
        file_path: str,
        content: str,
        mode: str = "overwrite",
    ) -> dict[str, Any]:
        """Create or append content to a file within permitted paths."""
        target = self.resolve_path(file_path)
        ok, err = self.policy.validate_path(target, write=True)
        if not ok:
            return {"success": False, "error": err}

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if mode == "append" and target.exists():
                with target.open("a", encoding="utf-8") as f:
                    f.write(content)
            else:
                target.write_text(content, encoding="utf-8")

            return {
                "success": True,
                "file_path": str(target),
                "size_bytes": target.stat().st_size,
                "message": f"Successfully wrote {len(content)} characters to '{target.name}'.",
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def search_files(
        self,
        query: str,
        directory: str | None = None,
        max_results: int = 25,
    ) -> dict[str, Any]:
        """Search for files by wildcard pattern across allowed directories."""
        root = self.resolve_path(directory)
        ok, err = self.policy.validate_path(root, write=False)
        if not ok:
            return {"success": False, "error": err, "matches": []}

        if not root.exists():
            return {"success": False, "error": f"Directory '{root}' does not exist.", "matches": []}

        pattern = query if ("*" in query or "?" in query) else f"*{query}*"
        matches = []
        try:
            # Bounded recursion
            count = 0
            for p in root.rglob(pattern):
                if p.is_file():
                    matches.append({
                        "name": p.name,
                        "path": str(p),
                        "size_bytes": p.stat().st_size,
                        "modified_time": p.stat().st_mtime,
                    })
                    count += 1
                    if count >= max_results:
                        break

            return {
                "success": True,
                "query": query,
                "directory": str(root),
                "count": len(matches),
                "matches": matches,
            }
        except Exception as exc:
            return {"success": False, "error": str(exc), "matches": []}

    def find_latest_file(
        self,
        directory: str | None = None,
        extension: str | None = None,
    ) -> dict[str, Any]:
        """Find the most recently modified file in a directory matching an optional extension."""
        root = self.resolve_path(directory)
        ok, err = self.policy.validate_path(root, write=False)
        if not ok:
            return {"success": False, "error": err}

        if not root.exists():
            return {"success": False, "error": f"Directory '{root}' does not exist."}

        ext_clean = extension.strip().lstrip(".").lower() if extension else None
        pattern = f"*.{ext_clean}" if ext_clean else "*"

        try:
            files = [
                p for p in root.glob(pattern)
                if p.is_file() and (not ext_clean or p.suffix.lower() == f".{ext_clean}")
            ]
            if not files:
                return {
                    "success": False,
                    "error": f"No matching files found in '{root}' with extension '{extension or '*'}'",
                }

            latest = max(files, key=lambda f: f.stat().st_mtime)
            return {
                "success": True,
                "file_path": str(latest),
                "name": latest.name,
                "size_bytes": latest.stat().st_size,
                "modified_time": latest.stat().st_mtime,
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}


controlled_fs = ControlledFileSystem()
