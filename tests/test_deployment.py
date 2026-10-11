"""Deployment-artifact tests: compose file, deploy scripts, Dockerfile, runbook.

Static validation only — no docker/az binaries are exercised here.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
DEPLOY_AZURE = SCRIPTS / "deploy-azure.sh"
DEPLOY_LOCAL = SCRIPTS / "deploy-local.sh"
COMPOSE = REPO / "docker-compose.yml"
DOCKERFILE = REPO / "Dockerfile"
RUNBOOK = REPO / "DEPLOYMENT.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# -- existence --------------------------------------------------------------


def test_deploy_scripts_exist():
    assert DEPLOY_AZURE.is_file()
    assert DEPLOY_LOCAL.is_file()


def test_compose_and_runbook_exist():
    assert COMPOSE.is_file()
    assert RUNBOOK.is_file()


def test_scripts_are_executable():
    for script in (DEPLOY_AZURE, DEPLOY_LOCAL):
        mode = os.stat(script).st_mode
        assert mode & stat.S_IXUSR, f"{script.name} is not executable"


# -- docker-compose.yml -----------------------------------------------------


def test_compose_parses_and_exposes_port_8000():
    doc = yaml.safe_load(_read(COMPOSE))
    services = doc.get("services", {})
    assert "api" in services
    ports = services["api"].get("ports", [])
    assert any(str(p).startswith("8000:8000") for p in ports)


def test_compose_builds_local_dockerfile():
    doc = yaml.safe_load(_read(COMPOSE))
    build = doc["services"]["api"].get("build", {})
    assert build.get("dockerfile", "Dockerfile") == "Dockerfile"


def test_compose_sets_guardrails_env():
    doc = yaml.safe_load(_read(COMPOSE))
    env = doc["services"]["api"].get("environment", {})
    assert env.get("GUARDRAILS_STRICTNESS") == "standard"


# -- bash syntax ------------------------------------------------------------


@pytest.mark.parametrize("script", [DEPLOY_AZURE, DEPLOY_LOCAL], ids=["azure", "local"])
def test_scripts_pass_bash_syntax_check(script):
    result = subprocess.run(
        ["bash", "-n", str(script)], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr


# -- deploy-azure.sh content -------------------------------------------------


def test_azure_script_is_strict_and_idempotent():
    text = _read(DEPLOY_AZURE)
    assert "set -euo pipefail" in text


def test_azure_script_checks_az_login():
    text = _read(DEPLOY_AZURE)
    assert "az account show" in text
    assert "az login" in text  # the error message tells the user to log in


def test_azure_script_covers_required_steps():
    text = _read(DEPLOY_AZURE)
    for step in (
        "az group create",
        "az acr create",
        "az acr build",  # build+push in Azure, no local docker needed
        "az containerapp env create",
        "az containerapp create",
        "az containerapp update",  # idempotent re-runs
        "/api/health",  # readiness gate
    ):
        assert step in text, f"missing step: {step}"


def test_azure_script_uses_managed_identity_not_admin_keys():
    text = _read(DEPLOY_AZURE)
    assert "--admin-enabled false" in text
    assert "AcrPull" in text
    assert "--system-assigned" in text


def test_azure_script_has_no_hardcoded_secrets():
    text = _read(DEPLOY_AZURE)
    lowered = text.lower()
    assert "password" not in lowered
    # No literal key assignments (values come from env, never in code)
    assert not re.search(r"(?i)(api[_-]?key|secret|token)\s*=\s*['\"][^'\"]+['\"]", text)


def test_azure_script_documents_teardown():
    text = _read(DEPLOY_AZURE)
    assert "az group delete" in text


# -- deploy-local.sh content -------------------------------------------------


def test_local_script_uses_compose_and_health_gate():
    text = _read(DEPLOY_LOCAL)
    assert "set -euo pipefail" in text
    assert "docker compose up" in text
    assert "localhost:8000/api/health" in text


# -- Dockerfile --------------------------------------------------------------


def test_dockerfile_runs_nonroot_with_pinned_base():
    text = _read(DOCKERFILE)
    assert "USER appuser" in text
    # Base image pinned by digest, not a floating tag
    assert re.search(r"FROM python:3\.12-slim@sha256:[0-9a-f]{64}", text)


def test_dockerfile_serves_port_8000_with_healthcheck():
    text = _read(DOCKERFILE)
    assert "EXPOSE 8000" in text
    assert "HEALTHCHECK" in text
    assert "/api/health" in text


# -- DEPLOYMENT.md -----------------------------------------------------------


def test_runbook_documents_prereqs_and_teardown():
    text = _read(RUNBOOK)
    assert "az login" in text
    assert "deploy-azure.sh" in text
    assert "deploy-local.sh" in text
    assert "az group delete" in text  # teardown command


def test_runbook_covers_costs_and_aks_path():
    text = _read(RUNBOOK)
    assert "Cost estimate" in text or "cost" in text.lower()
    assert "AKS" in text
    assert "terraform" in text.lower()


# -- .github/workflows (manual-add deliverables; validated locally) ---------

WORKFLOWS = REPO / ".github" / "workflows"


def _workflow(name: str):
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def test_workflow_files_exist():
    for name in ("ci.yml", "deploy.yml", "qa.yml"):
        assert (WORKFLOWS / name).is_file(), f"missing {name}"


def test_ci_workflow_has_static_checks():
    text = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    assert "bash -n" in text
    assert "docker-compose.yml" in text


def test_deploy_workflow_uses_oidc_not_secrets():
    text = (WORKFLOWS / "deploy.yml").read_text(encoding="utf-8")
    doc = _workflow("deploy.yml")
    assert "azure/login" in text
    assert "client-id" in text  # OIDC fields, not a stored credential
    assert "AZURE_CREDENTIALS" not in text  # legacy secret-based login is gone
    assert doc.get("permissions", {}).get("id-token") == "write"
    assert "workflow_dispatch" in text  # manual re-deploy supported


def test_deploy_workflow_targets_production_environment():
    doc = _workflow("deploy.yml")
    jobs = doc.get("jobs", {})
    assert jobs, "deploy.yml has no jobs"
    for job in jobs.values():
        assert job.get("environment") == "production"
    text = (WORKFLOWS / "deploy.yml").read_text(encoding="utf-8")
    assert "scripts/deploy-azure.sh" in text
    assert "/api/health" in text  # smoke test
