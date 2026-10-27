from pathlib import Path

import pytest

from boba.security.path_validator import UnsafePath, matches, validate_path


@pytest.mark.parametrize("path", [".aws/credentials", ".ssh/id_rsa", ".env", ".env.production", "secrets/key",
                                  "../hello.txt", "../../etc/passwd", "hello.txt/../hello.txt", "~/.ssh/id_rsa",
                                  "file:///etc/passwd", "%2e%2e/hello.txt", "a\\b", "a\x00b", "", [], None])
def test_reject_paths(sandbox: Path, path: object) -> None:
    with pytest.raises(UnsafePath):
        validate_path(path, [sandbox])


def test_resolve_safe_path(sandbox: Path) -> None:
    assert validate_path("./hello.txt", [sandbox])[1] == sandbox / "hello.txt"


def test_symlinks(sandbox: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.write_text("private")
    (sandbox / "escape").symlink_to(outside)
    (sandbox / "alias").symlink_to(sandbox / ".env")
    for path in ("escape", "alias"):
        with pytest.raises(UnsafePath):
            validate_path(path, [sandbox])


def test_patterns() -> None:
    assert matches(Path(".env"), ["**/.env"])
    assert matches(Path("secrets"), ["**/secrets/**"])
