"""Base class for AGON format codecs."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class AGONFormat(ABC):
    """Abstract base class for AGON format codecs.

    All AGON formats should inherit from this class and implement:
        - encode(data, ...) -> str
        - decode(payload, ...) -> Any
        - hint() -> str
    """

    @staticmethod
    @abstractmethod
    def encode(data: object, *, include_header: bool = False) -> str:
        """Encode data to this format."""
        ...

    @staticmethod
    @abstractmethod
    def decode(payload: str) -> object:
        """Decode a payload in this format."""
        ...

    @staticmethod
    @abstractmethod
    def hint() -> str:
        """Return a short hint describing this format for LLMs."""
        ...

    # ---------- Projection ----------

    @staticmethod
    def project_data(data: list[dict[str, Any]], keep_paths: list[str]) -> list[dict[str, Any]]:
        """Project data to only keep specified fields.

        Args:
            data: List of objects to project.
            keep_paths: List of field paths to keep. Supports dotted paths
                like "user.name" or "quotes.symbol".

        Returns:
            Projected data with only the specified fields.
        """
        keep_tree = AGONFormat._build_keep_tree(keep_paths)
        return [AGONFormat._project_obj(r, keep_tree) for r in data]

    @staticmethod
    def _build_keep_tree(keep_paths: list[str]) -> dict[str, Any]:
        keep_tree: dict[str, Any] = {}

        for raw_path in keep_paths:
            path = raw_path.strip().strip(".")
            if not path:
                continue
            parts = [p for p in path.split(".") if p]

            cur: dict[str, Any] = keep_tree
            for part in parts[:-1]:
                nxt = cur.get(part)
                if nxt is None:
                    nxt = {}
                    cur[part] = nxt
                cur = nxt

            cur.setdefault(parts[-1], None)

        return keep_tree

    @staticmethod
    def _project_obj(obj: dict[str, Any], keep_tree: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k, sub_keep in keep_tree.items():
            if k not in obj:
                continue
            v = obj[k]
            if v is None or sub_keep is None:
                out[k] = v
                continue

            # If sub_keep is not None, it is always a dict produced by _build_keep_tree().
            if isinstance(v, dict):
                out[k] = AGONFormat._project_obj(v, sub_keep)
            elif isinstance(v, list) and (not v or all(isinstance(x, dict) for x in v)):
                out[k] = [AGONFormat._project_obj(x, sub_keep) for x in v]
            else:
                out[k] = v
        return out
