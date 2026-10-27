"""Canonical containment plus lexical and resolved protected-path checks."""

from fnmatch import fnmatchcase
from pathlib import Path


class UnsafePath(ValueError):
    """A path cannot safely be authorized; never include its value in errors."""


def matches(path: Path, patterns: list[str]) -> bool:
    # A leading slash lets **/.env also match a root-level .env.
    value = "/" + path.as_posix().lstrip("/").casefold()
    return any(fnmatchcase(value, pattern.casefold()) or
               fnmatchcase(value + "/", pattern.casefold()) for pattern in patterns)


def protected(path: Path) -> bool:
    return any(part.casefold() in {".aws", ".ssh", "secrets"} or
               part.casefold().startswith(".env") for part in path.parts)


def validate_path(value: object, roots: list[Path]) -> tuple[Path, Path]:
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise UnsafePath("Invalid path argument")
    if any(ord(char) < 32 for char in value) or any(char in value for char in ("\\", ":", "%", "~")):
        raise UnsafePath("Unsupported path syntax")
    lexical = Path(value)
    if ".." in lexical.parts:
        raise UnsafePath("Directory traversal")
    candidate = lexical if lexical.is_absolute() else roots[0] / lexical
    try:
        canonical = candidate.resolve(strict=True)
    except (OSError, ValueError, RuntimeError):
        raise UnsafePath("Path resolution failed") from None
    if not any(candidate.is_relative_to(root) and canonical.is_relative_to(root) for root in roots):
        raise UnsafePath("Path outside approved roots")
    if protected(candidate) or protected(canonical):
        raise UnsafePath("Protected credential path")
    return candidate, canonical
