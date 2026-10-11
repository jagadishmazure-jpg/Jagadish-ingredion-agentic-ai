"""Input/output security controls for the demo agent system.

- ``sanitize_input``: flags prompt-injection patterns in agent inputs.
- ``scrub_pii``: redacts PII-like patterns from agent outputs.
- ``assert_no_hardcoded_secrets``: fail-loudly scan used by the test suite
  to prove no secrets are baked into the codebase (secrets live in env only).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List, Tuple

# (pattern, description) — checked case-insensitively against agent inputs.
INJECTION_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.I), "instruction override"),
    (re.compile(r"disregard\s+(all\s+)?(prior|previous)\s+instructions", re.I), "instruction override"),
    (re.compile(r"^\s*system\s*:", re.I | re.M), "forged system message"),
    (re.compile(r"<\|(system|im_start|im_end)\|>", re.I), "chat-template injection"),
    (re.compile(r"jailbreak", re.I), "jailbreak attempt"),
    (re.compile(r"do\s+anything\s+now", re.I), "DAN-style jailbreak"),
    (re.compile(r"base64\s*,\s*[A-Za-z0-9+/=]{20,}", re.I), "possible encoded payload"),
]

# (pattern, replacement label)
PII_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[REDACTED-EMAIL]"),
    (re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b"), "[REDACTED-PHONE]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED-SSN]"),
    (re.compile(r"\b(?:\d[ -]?){13,16}\b"), "[REDACTED-CARD]"),
]

# Patterns that must never appear with a literal value in source files.
SECRET_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"""(?i)(api_key|apikey)\s*=\s*['"][^'"]{4,}['"]"""), "hardcoded api_key"),
    (re.compile(r"""(?i)(secret|password|passwd|pwd)\s*=\s*['"][^'"]{4,}['"]"""), "hardcoded secret"),
    (re.compile(r"""(?i)bearer\s+[A-Za-z0-9\-._~+/]{16,}"""), "hardcoded bearer token"),
    (re.compile(r"""sk-[A-Za-z0-9]{16,}"""), "hardcoded sk- key"),
]

_SECRET_SCAN_EXCLUDE = {".git", "__pycache__", ".venv", "node_modules", ".pytest_cache"}


def sanitize_input(text: str) -> Tuple[str, List[str]]:
    """Flag prompt-injection patterns in *text*.

    Returns ``(text, flags)`` — the text is returned unchanged (flag, don't
    silently rewrite) plus a list of matched pattern descriptions.
    """
    flags = [desc for pattern, desc in INJECTION_PATTERNS if pattern.search(text)]
    return text, flags


def scrub_pii(text: str) -> str:
    """Redact PII-like patterns from *text*."""
    for pattern, label in PII_PATTERNS:
        text = pattern.sub(label, text)
    return text


def assert_no_hardcoded_secrets(root: str | Path) -> List[str]:
    """Scan *root* for hardcoded secrets; raise AssertionError on any hit.

    Returns the list of scanned files when clean. ``.env`` files and this
    module's own pattern definitions are excluded from scanning.
    """
    root = Path(root)
    violations: List[str] = []
    scanned: List[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in _SECRET_SCAN_EXCLUDE for part in path.parts):
            continue
        if path.name == ".env" or path.suffix not in {".py", ".yaml", ".yml", ".json", ".toml", ".sh"}:
            continue
        if path.name == "security.py":
            continue  # this file defines the patterns themselves
        try:
            content = path.read_text(encoding="utf-8", errors="strict")
        except (UnicodeDecodeError, OSError):
            continue
        scanned.append(str(path))
        for lineno, line in enumerate(content.splitlines(), 1):
            for pattern, desc in SECRET_PATTERNS:
                if pattern.search(line):
                    violations.append(f"{path}:{lineno}: {desc}")
    if violations:
        raise AssertionError(
            "hardcoded secrets detected (secrets must come from env only):\n"
            + "\n".join(violations)
        )
    return scanned


def require_env(name: str) -> str:
    """Return ``os.environ[name]`` or raise a loud, helpful error."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"missing required environment variable {name!r}; "
            "see .env.example (never hardcode secrets in code)"
        )
    return value
