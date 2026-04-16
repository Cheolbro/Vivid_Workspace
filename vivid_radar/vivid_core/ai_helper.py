"""
vivid_core/ai_helper.py
AI 호출 헬퍼 — vivid_radar 전용 (utils/ 의존 없음, 완전 격리)

역할:
  Gemini CLI  → 전략 수립 (Google AI Pro 구독 권한, 5~10초)
  Ollama HTTP → 대량 생성 (로컬 gemma4:e4b, 무제한/무비용, 30~90초)

함수:
    ensure_ollama_running()       → bool  (Ollama 서버 자동 기동)
    call_gemini_cli(prompt)       → str   (동기)
    call_gemini_cli_async(prompt) → str   (async)
    call_gemma(prompt)            → str   (동기)
    call_gemma_async(prompt)      → str   (async)
"""

import json
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request
from urllib.error import URLError

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[mGKHF]")

_OLLAMA_BASE  = "http://localhost:11434"
_OLLAMA_API   = f"{_OLLAMA_BASE}/api/generate"
_OLLAMA_MODEL = "gemma4:e4b"


# ── Ollama 자동 기동 ──────────────────────────────────────────────────────────

def ensure_ollama_running(wait_sec: int = 15) -> bool:
    """
    Ollama 서버가 실행 중인지 확인하고, 꺼져 있으면 백그라운드로 기동.

    Returns:
        True  → 서버 정상 응답
        False → wait_sec 내에 기동 실패
    """
    def _is_up() -> bool:
        try:
            with urllib.request.urlopen(f"{_OLLAMA_BASE}/api/tags", timeout=3) as r:
                return r.status == 200
        except Exception:
            return False

    if _is_up():
        return True

    # ollama CLI가 있으면 serve 명령으로 백그라운드 기동
    if not shutil.which("ollama"):
        raise RuntimeError(
            "ollama 실행파일이 PATH에 없습니다. "
            "https://ollama.com 에서 설치하세요."
        )

    subprocess.Popen(
        ["ollama", "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # 최대 wait_sec 동안 기동 대기
    deadline = time.time() + wait_sec
    while time.time() < deadline:
        time.sleep(1)
        if _is_up():
            return True

    return False


# ── Gemini CLI ────────────────────────────────────────────────────────────────

def _find_gemini_exe() -> str:
    """
    gemini CLI 실행파일 경로를 반환한다.
    shutil.which 실패 시 Windows npm 글로벌 경로를 직접 탐색.
    """
    import os
    found = shutil.which("gemini") or shutil.which("gemini.cmd")
    if found:
        return found

    appdata = os.environ.get("APPDATA", "")
    if appdata:
        from pathlib import Path
        candidate = Path(appdata) / "npm" / "gemini.cmd"
        if candidate.exists():
            return str(candidate)

    raise RuntimeError(
        "'gemini' CLI를 찾을 수 없습니다.\n"
        "터미널에서 npm install -g @google/gemini-cli 를 실행하세요."
    )


def call_gemini_cli(prompt: str, timeout: int = 120) -> str:
    """
    gemini CLI 호출 → 응답 문자열 반환.
    Google AI Pro 구독 권한 사용 / API 한도 무관.
    cwd=tempdir: 프로젝트 폴더 스캔 방지 (속도 최적화)
    """
    exe = _find_gemini_exe()

    result = subprocess.run(
        [exe, "-p", prompt],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        cwd=tempfile.gettempdir(),
    )

    if result.returncode != 0:
        raise RuntimeError(f"gemini CLI 오류: {result.stderr[:400]}")

    return _ANSI_RE.sub("", result.stdout).strip()


async def call_gemini_cli_async(prompt: str, timeout: int = 120) -> str:
    """asyncio 컨텍스트에서 call_gemini_cli를 non-blocking 실행."""
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, call_gemini_cli, prompt, timeout)


# ── Ollama / Gemma ────────────────────────────────────────────────────────────

def call_gemma(prompt: str, timeout: int = 180) -> str:
    """
    로컬 Ollama 서버의 gemma4:e4b 모델 호출.
    완전 오프라인, 비용 없음.
    호출 전 ensure_ollama_running() 으로 서버 확인 권장.
    """
    payload = json.dumps({
        "model":  _OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
    }).encode("utf-8")

    req = urllib.request.Request(
        _OLLAMA_API,
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return body.get("response", "").strip()
    except URLError as e:
        raise RuntimeError(
            f"Ollama 서버 연결 실패: {e}\n"
            "ensure_ollama_running() 을 먼저 호출하세요."
        )


async def call_gemma_async(prompt: str, timeout: int = 180) -> str:
    """asyncio 컨텍스트에서 call_gemma를 non-blocking 실행."""
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, call_gemma, prompt, timeout)
