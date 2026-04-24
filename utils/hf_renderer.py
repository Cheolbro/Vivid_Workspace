"""
utils/hf_renderer.py
HyperFrames 슬라이드 렌더 엔진
  - slide_NN.html + delta JSON → 임시 index.html → hyperframes render → slide_NN.mp4
  - 1회 자동 재시도 / 실패 슬라이드 목록 반환
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

_HIDDEN = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}

_HF_BIN_NAME = "hyperframes.cmd" if sys.platform == "win32" else "hyperframes"

# Shared node_modules in the project template — used as fallback when a
# project's own hyperframes/node_modules is absent (avoids per-project npm install).
_TEMPLATE_HF_DIR = Path(__file__).parent.parent / "Project_templete" / "hyperframes"


def _resolve_hf_bin(hf_dir: Path) -> Path:
    """Return the hyperframes binary, preferring project-local, falling back to template."""
    local = hf_dir / "node_modules" / ".bin" / _HF_BIN_NAME
    if local.exists():
        return local
    shared = _TEMPLATE_HF_DIR / "node_modules" / ".bin" / _HF_BIN_NAME
    if shared.exists():
        return shared
    return local  # let subprocess raise a clear error if neither exists


# ══════════════════════════════════════════════
# Delta 적용
# ══════════════════════════════════════════════

def _apply_delta(html: str, delta: dict) -> str:
    """
    delta.json의 elements를 </body> 직전 인라인 스크립트로 주입.
    CSS 속성(x, y, fontSize, color)만 적용 — gsap_start는 Phase 4 편집 UI에서 처리.
    """
    elements = delta.get("elements", {})
    if not elements:
        return html

    parts = []
    for selector, props in elements.items():
        # selector에 큰따옴표가 포함되면 탈출
        safe_sel = selector.replace('"', '\\"')
        stmts = [f'var el=document.querySelector("{safe_sel}");if(!el)return;']
        if props.get("x") is not None:
            stmts.append(f'el.style.left="calc(50% + {props["x"]}px)";')
        if props.get("y") is not None:
            stmts.append(f'el.style.top="calc(50% + {props["y"]}px)";')
        if props.get("fontSize"):
            stmts.append(f'el.style.fontSize="{props["fontSize"]}";')
        if props.get("color"):
            stmts.append(f'el.style.color="{props["color"]}";')
        if stmts:
            parts.append("(function(){" + "".join(stmts) + "})();")

    if not parts:
        return html

    inject = "<script>" + "".join(parts) + "</script>"
    if "</body>" in html:
        return html.replace("</body>", inject + "</body>", 1)
    return html + inject


# ══════════════════════════════════════════════
# 단일 슬라이드 렌더
# ══════════════════════════════════════════════

def render_slide(
    html_path: Path,
    output_mp4: Path,
    hf_dir: Path,
    delta_path: Path | None = None,
) -> None:
    """
    슬라이드 1장을 .mp4로 렌더한다.

    hf_dir: 프로젝트 내 hyperframes/ 폴더 (node_modules/.bin/hyperframes 위치)
    실패 시 subprocess.CalledProcessError 발생.
    """
    html = html_path.read_text(encoding="utf-8")

    if delta_path and delta_path.exists():
        try:
            delta = json.loads(delta_path.read_text(encoding="utf-8"))
            html  = _apply_delta(html, delta)
        except Exception:
            pass  # delta 파싱 실패 시 원본 HTML로 진행

    hf_bin = _resolve_hf_bin(hf_dir)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_html = Path(tmpdir) / "index.html"
        tmp_html.write_text(html, encoding="utf-8")

        subprocess.run(
            [str(hf_bin), "render", tmpdir,
             "--format", "mp4",
             "--fps",    "30",
             "--output", str(output_mp4),
             "--quiet"],
            check=True,
            **_HIDDEN,
        )


# ══════════════════════════════════════════════
# 전체 슬라이드 일괄 렌더
# ══════════════════════════════════════════════

def render_all_slides(
    compositions_dir: Path,
    output_dir: Path,
    hf_dir: Path,
    progress_cb: Callable[[int, int, str], None] | None = None,
) -> dict:
    """
    compositions_dir 내 slide_*.html 전부 렌더.

    progress_cb(current, total, slide_name) — Step 4 상태창 업데이트용 콜백
    반환: {"rendered": ["slide_01", ...], "failed": ["slide_03", ...]}
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    html_files = sorted(
        compositions_dir.glob("slide_*.html"),
        key=lambda p: p.stem,
    )
    total     = len(html_files)
    rendered: list[str] = []
    failed:   list[str] = []

    for idx, html_path in enumerate(html_files, 1):
        name       = html_path.stem            # "slide_01"
        out_mp4    = output_dir / f"{name}.mp4"
        delta_path = compositions_dir / f"{name}_delta.json"

        if progress_cb:
            progress_cb(idx, total, name)

        success = False
        for attempt in range(2):            # 최초 1회 + 재시도 1회
            try:
                render_slide(html_path, out_mp4, hf_dir, delta_path)
                success = True
                break
            except Exception:
                if attempt == 0:
                    continue

        (rendered if success else failed).append(name)

    return {"rendered": rendered, "failed": failed}
