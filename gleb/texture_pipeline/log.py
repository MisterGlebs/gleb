"""Structured logging for texture pipeline (agent-facing JSON, not TTY prints)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TextureLog:
    """Collects info and warning lines without printing."""

    infos: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def info(self, msg: str) -> None:
        self.infos.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)
