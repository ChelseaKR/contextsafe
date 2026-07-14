"""Structured, value-minimizing errors for the local runner."""

from dataclasses import dataclass


@dataclass(slots=True)
class ContextSafeError(Exception):
    """A stable error that never includes an input value."""

    code: str
    path: str
    message: str

    def __str__(self) -> str:
        """Return a safe human-readable form."""

        return f"{self.code} at {self.path}: {self.message}"

    def to_dict(self) -> dict[str, str]:
        """Return the stable CLI error object."""

        return {"code": self.code, "message": self.message, "path": self.path}
