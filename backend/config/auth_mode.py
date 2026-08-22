"""Canonical portfolio branch/auth-mode adapter for Django settings."""

from __future__ import annotations

import os
import re
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from django.core.exceptions import ImproperlyConfigured

_BRANCH_PATTERN = re.compile(r"^[A-Za-z0-9._/-]+$")


@dataclass(frozen=True, slots=True)
class PortfolioAuthContract:
    branch: str
    mode: str
    sso_enabled: bool


def _normalize_branch(branch: str) -> str:
    normalized = branch.removeprefix("refs/heads/")
    if not normalized or _BRANCH_PATTERN.fullmatch(normalized) is None:
        raise ImproperlyConfigured("PORTFOLIO_BRANCH is missing or invalid.")
    return normalized


def _mode_for_branch(branch: str) -> str:
    normalized = _normalize_branch(branch)
    return "sso" if normalized in {"main", "dev"} else "local"


def _strict_boolean(name: str, value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in {"true", "false"}:
        return value.lower() == "true"
    raise ImproperlyConfigured(f"{name} must be true or false.")


def _resolver_path(base_dir: Path) -> Path | None:
    for candidate in (
        base_dir.parent / "scripts" / "portfolio-auth-mode.sh",
        base_dir / "scripts" / "portfolio-auth-mode.sh",
    ):
        if candidate.is_file():
            return candidate
    return None


def _canonical_contract(
    base_dir: Path,
    environment: Mapping[str, str],
) -> tuple[str, str, bool]:
    resolver = _resolver_path(base_dir)
    if resolver is not None:
        process_environment = os.environ.copy()
        process_environment.update(environment)
        try:
            result = subprocess.run(
                (
                    "/bin/sh",
                    str(resolver),
                    "exec",
                    "--",
                    "/bin/sh",
                    "-c",
                    'printf "%s\\n%s\\n" "$PORTFOLIO_BRANCH" "$PORTFOLIO_AUTH_MODE"',
                ),
                cwd=resolver.parent.parent,
                env=process_environment,
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ImproperlyConfigured(
                "The portfolio auth-mode resolver could not run."
            ) from exc
        if result.returncode != 0:
            detail = result.stderr.strip() or "portfolio auth-mode resolution failed"
            raise ImproperlyConfigured(detail)
        lines = result.stdout.splitlines()
        if len(lines) != 2:
            raise ImproperlyConfigured(
                "The portfolio auth-mode resolver returned an invalid contract."
            )
        branch = _normalize_branch(lines[0])
        mode = lines[1]
        if mode != _mode_for_branch(branch):
            raise ImproperlyConfigured(
                "The portfolio auth-mode resolver returned an invalid contract."
            )
        return branch, mode, False

    branch = environment.get("PORTFOLIO_BRANCH")
    if branch is None:
        branch = environment.get("GITHUB_REF_NAME")
    if branch is None:
        raise ImproperlyConfigured(
            "Packaged runtimes must set PORTFOLIO_BRANCH explicitly."
        )
    normalized_branch = _normalize_branch(branch)
    expected_mode = _mode_for_branch(normalized_branch)
    explicit_mode = environment.get("PORTFOLIO_AUTH_MODE")
    if explicit_mode is None:
        raise ImproperlyConfigured(
            "Packaged runtimes must set PORTFOLIO_AUTH_MODE explicitly."
        )
    if explicit_mode != expected_mode:
        raise ImproperlyConfigured(
            f"PORTFOLIO_BRANCH requires PORTFOLIO_AUTH_MODE={expected_mode}."
        )
    return normalized_branch, expected_mode, True


def _read_build_contract(path: Path) -> tuple[str, str]:
    try:
        metadata = path.lstat()
        payload = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ImproperlyConfigured(
            "Packaged runtimes require /etc/portfolio-auth-build."
        ) from exc
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise ImproperlyConfigured(
            "The image portfolio auth contract must be a regular file."
        )
    if stat.S_IMODE(metadata.st_mode) != 0o444:
        raise ImproperlyConfigured(
            "The image portfolio auth contract must have mode 0444."
        )
    lines = payload.splitlines()
    if len(lines) != 2:
        raise ImproperlyConfigured(
            "The image portfolio auth contract must contain branch and mode."
        )
    branch = _normalize_branch(lines[0])
    mode = lines[1]
    if mode != _mode_for_branch(branch):
        raise ImproperlyConfigured("The image portfolio auth contract is invalid.")
    return branch, mode


def resolve_portfolio_auth_contract(
    *,
    base_dir: Path,
    environment: Mapping[str, str],
    legacy_sso_name: str,
    legacy_sso_value: object | None,
    build_mode: str | None = None,
    build_contract_path: Path = Path("/etc/portfolio-auth-build"),
) -> PortfolioAuthContract:
    """Resolve the canonical mode and reject every explicit adapter mismatch."""

    branch, mode, packaged = _canonical_contract(base_dir, environment)
    if packaged:
        build_branch, file_build_mode = _read_build_contract(build_contract_path)
        if build_branch != branch or file_build_mode != mode:
            raise ImproperlyConfigured(
                "The runtime portfolio auth contract conflicts with the image build."
            )
    sso_enabled = mode == "sso"
    if legacy_sso_value is not None:
        legacy_enabled = _strict_boolean(legacy_sso_name, legacy_sso_value)
        if legacy_enabled != sso_enabled:
            raise ImproperlyConfigured(
                f"{legacy_sso_name} conflicts with PORTFOLIO_AUTH_MODE={mode}."
            )
    if build_mode is not None and build_mode != mode:
        raise ImproperlyConfigured(
            "The runtime portfolio auth mode conflicts with the image build mode."
        )
    return PortfolioAuthContract(branch=branch, mode=mode, sso_enabled=sso_enabled)
