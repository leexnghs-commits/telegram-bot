# -*- coding: utf-8 -*-
"""
CLI executor for Claude Code and OpenAI Codex via asyncio subprocess.
"""
import asyncio
import os
import re
import tempfile
from pathlib import Path
from dataclasses import dataclass, field

from config import (
    CLAUDE_EXE, CLAUDE_TIMEOUT, PROJECT_ROOT, DEFAULT_MODEL,
    CODEX_EXE, CODEX_TIMEOUT,
)


@dataclass
class ExecutionResult:
    stdout: str = ""
    stderr: str = ""
    returncode: int = -1
    timed_out: bool = False
    files: list = field(default_factory=list)


# Patterns to detect generated file paths in output
FILE_PATTERNS = [
    re.compile(r'(?:saved?|created?|wrote|generated?|output)\s*(?:to|:)?\s*[`"\']?([A-Za-z]:\\[^\s`"\'<>|]+\.\w{2,5})', re.IGNORECASE),
    re.compile(r'(?:saved?|created?|wrote|generated?|output)\s*(?:to|:)?\s*[`"\']?((?:\./|\.\\|/)?[\w/\\.-]+\.\w{2,5})', re.IGNORECASE),
    re.compile(r'[`"\']([A-Za-z]:\\[^\s`"\'<>|]+\.(?:png|html|csv|md|txt|pdf|xlsx))[`"\']', re.IGNORECASE),
]

SENDABLE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.html', '.csv', '.md', '.txt', '.pdf', '.xlsx'}


def detect_files(text: str, cwd: Path) -> list[Path]:
    """Extract file paths from output and return existing ones."""
    found = []
    seen = set()
    for pattern in FILE_PATTERNS:
        for match in pattern.finditer(text):
            raw = match.group(1).strip().rstrip('.')
            p = Path(raw)
            if not p.is_absolute():
                p = cwd / p
            p = p.resolve()
            if p.suffix.lower() in SENDABLE_EXTENSIONS and p not in seen and p.exists():
                found.append(p)
                seen.add(p)
    return found


async def _run_subprocess(cmd: list, cwd: Path, timeout: int, env: dict | None = None) -> ExecutionResult:
    """Generic async subprocess runner."""
    result = ExecutionResult()
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd),
            env=env,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            result.stdout = stdout_bytes.decode("utf-8", errors="replace")
            result.stderr = stderr_bytes.decode("utf-8", errors="replace")
            result.returncode = proc.returncode
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            result.timed_out = True
            result.stdout = "(timeout: 실행 시간 초과)"
    except Exception as e:
        result.stderr = str(e)
        result.returncode = -1

    result.files = detect_files(result.stdout, cwd)
    return result


async def run_claude(prompt: str, cwd: Path = PROJECT_ROOT, timeout: int = CLAUDE_TIMEOUT, model: str | None = None) -> ExecutionResult:
    """Run `claude -p "prompt"` as async subprocess."""
    env = {k: v for k, v in os.environ.items() if "CLAUDECODE" not in k.upper()}

    use_model = model or DEFAULT_MODEL
    cmd = [
        str(CLAUDE_EXE),
        "-p", prompt,
        "--model", use_model,
        "--dangerously-skip-permissions",
    ]
    return await _run_subprocess(cmd, cwd, timeout, env)


async def run_codex(prompt: str, cwd: Path = PROJECT_ROOT, timeout: int = CODEX_TIMEOUT) -> ExecutionResult:
    """Run `codex exec "prompt"` as async subprocess.

    Uses --output-last-message to capture the final assistant response cleanly,
    and --json for structured output parsing.
    """
    # Write final message to a temp file for clean extraction
    out_file = Path(tempfile.mktemp(suffix=".txt", prefix="codex_out_"))

    cmd = [
        str(CODEX_EXE),
        "exec", prompt,
        "-C", str(cwd),
        "--dangerously-bypass-approvals-and-sandbox",
        "--skip-git-repo-check",
        "--output-last-message", str(out_file),
    ]

    result = await _run_subprocess(cmd, cwd, timeout)

    # Prefer the clean output file over raw stdout
    if out_file.exists():
        clean_output = out_file.read_text(encoding="utf-8", errors="replace").strip()
        if clean_output:
            result.stdout = clean_output
        out_file.unlink(missing_ok=True)

    # Re-detect files from the clean output
    result.files = detect_files(result.stdout, cwd)

    return result
