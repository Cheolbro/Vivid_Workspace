"""
utils/step4_workers.py
4단계에서 사용하는 비즈니스 로직 모음 (UI 비종속)

· 경로 상수    : ROOT_DIR, CATALOG_PATH, CONFIG_PATH, _NPX, _NPM
· 헬퍼 함수    : parse_plan_json(), detect_custom_fx()
· Worker 클래스 : RenderWorker, VrewWorker, GeminiWorker, SemanticMatchWorker
"""

import json
import re
import subprocess
import sys
import time
import shutil
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from utils.theme import SHARED_FX_DIR
from utils.backend_ext import (
    diff_check_effects,
    assemble_vrew,
)
from utils.fx_gallery import invalidate_cache as invalidate_fx_cache

# ── 경로 상수 ─────────────────────────────────────────────────────────────
ROOT_DIR     = Path(__file__).parent.parent   # Vivid_Workspace/
CATALOG_PATH = ROOT_DIR / "fx_catalog.txt"
CONFIG_PATH  = ROOT_DIR / "config.json"

# Windows에서 Python subprocess는 .cmd 확장자를 자동 탐색하지 않음
_NPX = "npx.cmd" if sys.platform == "win32" else "npx"
_NPM = "npm.cmd" if sys.platform == "win32" else "npm"


# ══════════════════════════════════════════════
# 헬퍼 함수
# ══════════════════════════════════════════════

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[mGKHF]")

# node.exe + gemini entry.js 경로 캐시 (프로세스당 1회 탐색)
_gemini_node_cmd_cache: list[str] | None = None


def _find_gemini_exe() -> str:
    """
    gemini CLI 실행파일 경로를 반환한다.
    shutil.which 실패 시 Windows npm 글로벌 경로를 직접 탐색.
    """
    found = shutil.which("gemini") or shutil.which("gemini.cmd")
    if found:
        return found

    import os
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        candidate = Path(appdata) / "npm" / "gemini.cmd"
        if candidate.exists():
            return str(candidate)

    raise RuntimeError(
        "'gemini' CLI를 찾을 수 없습니다.\n"
        "터미널에서 npm install -g @google/gemini-cli 를 실행한 뒤\n"
        "Vivid Studio 서버를 재시작하세요."
    )


def _find_node_gemini_cmd() -> list[str]:
    """
    [node.exe경로, entry.js경로] 를 3계층 탐색으로 반환 (결과 캐싱).

    Layer 1 — require.resolve (가장 정확, Node.js 모듈 탐색 알고리즘 직접 활용)
    Layer 2 — cmd_path.parent/node_modules (글로벌 npm 표준 구조)
    Layer 3 — cmd_path.parent.parent (로컬 node_modules/.bin 구조 대응)
    """
    global _gemini_node_cmd_cache
    if _gemini_node_cmd_cache is not None:
        return _gemini_node_cmd_cache

    node = shutil.which("node.exe") or shutil.which("node")
    if not node:
        raise RuntimeError("node.exe를 찾을 수 없습니다. Node.js 설치를 확인하세요.")

    _BUNDLE = ("node_modules", "@google", "gemini-cli", "bundle", "gemini.js")

    # ── Layer 1: require.resolve로 Node.js에게 직접 질의 ──────────────────
    try:
        resolve_script = (
            "const r=require.resolve('@google/gemini-cli');"
            "const p=require('path');"
            "console.log(p.join(p.dirname(r),'../bundle/gemini.js'))"
        )
        res = subprocess.run(
            [node, "-e", resolve_script],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=10,
        )
        if res.returncode == 0:
            js_path = Path(res.stdout.strip())
            if js_path.exists():
                _gemini_node_cmd_cache = [node, str(js_path)]
                return _gemini_node_cmd_cache
    except Exception:
        pass

    # ── Layer 2 / 3: cmd_path 기준 직접 경로 구성 ─────────────────────────
    cmd_path = Path(_find_gemini_exe())
    for base in (cmd_path.parent, cmd_path.parent.parent):
        js_path = base.joinpath(*_BUNDLE)
        if js_path.exists():
            _gemini_node_cmd_cache = [node, str(js_path)]
            return _gemini_node_cmd_cache

    raise RuntimeError(
        "gemini entry.js를 찾을 수 없습니다.\n"
        f"탐색 기준 경로: {cmd_path.parent}\n"
        "npm install -g @google/gemini-cli 재설치 후 서버를 재시작하세요."
    )


def _call_gemini_cli(prompt: str) -> str:
    """
    시스템에 설치된 'gemini' CLI를 호출하여 응답을 받는다.
    Windows: node.exe + entry.js 직접 호출로 cmd.exe 8191자 제한 우회.
    """
    import tempfile as _tmp

    if sys.platform == "win32":
        cmd = _find_node_gemini_cmd() + ["-p", prompt]
    else:
        cmd = [_find_gemini_exe(), "-p", prompt]

    result = subprocess.run(
        cmd,
        capture_output=True,
        cwd=_tmp.gettempdir(),
        timeout=600,
    )

    if result.returncode != 0:
        err = result.stderr
        if isinstance(err, bytes):
            err = err.decode("utf-8", errors="replace")
        raise RuntimeError(f"gemini CLI 호출 실패: {err[:300]}")

    out = result.stdout
    if isinstance(out, bytes):
        out = out.decode("utf-8", errors="replace")
    return _ANSI_RE.sub("", out).strip()


def parse_plan_json(plan_path: Path) -> dict:
    """
    remotion_plan.json 검증 및 파싱.
    하네스: 0바이트 / JSON 포맷 오류 / effects[] 없음
    """
    if not plan_path.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {plan_path}")
    if plan_path.stat().st_size == 0:
        raise ValueError("remotion_plan.json 파일이 비어 있습니다 (0바이트).")

    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON 형식 오류:\n{e}")

    if not isinstance(plan.get("effects"), list):
        raise ValueError(
            "'effects' 배열이 없거나 형식이 올바르지 않습니다.\n"
            "remotion_plan.json 에 effects[] 키가 있어야 합니다."
        )
    return plan


def detect_custom_fx(plan: dict) -> list[dict]:
    """
    effects[] 중 type=Custom 인 항목 목록을 반환한다.
    매칭은 SemanticMatchWorker가 담당하므로 여기서는 감지만 수행.
    """
    return [e for e in plan.get("effects", []) if e.get("type") == "Custom"]


# ══════════════════════════════════════════════
# RenderWorker  (QThread — UI 블로킹 방지)
# ══════════════════════════════════════════════

class RenderWorker(QObject):
    """
    Remotion 투명 렌더링 워커 — 슬라이드 단위 렌더링.

    슬라이드 Composition(VividSlide-p1 등)을 previewMode=false 로 렌더링하여
    투명 WebM(FX만, 배경 제외)을 생성한다.
    Diff-Check: 슬라이드 내 어떤 FX라도 변경된 슬라이드만 재렌더링.
    """
    progress  = Signal(int, int)       # (current, total)
    item_done = Signal(str, str)       # (slide_id, webm_path_str)
    item_skip = Signal(str)            # (slide_id) — 변경 없어 스킵
    finished  = Signal(object)         # render_cache: dict[str, str]
    error     = Signal(str)

    def __init__(
        self,
        plan: dict,
        remotion_dir: Path,
        renders_dir: Path,
        cache_path: Path,
        parent=None,
    ):
        super().__init__(parent)
        self._plan       = plan
        self._remotion   = remotion_dir
        self._renders    = renders_dir
        self._cache_path = cache_path
        self._abort      = False

    def abort(self):
        self._abort = True

    def run(self):
        try:
            self._do_render()
        except Exception as e:
            self.error.emit(str(e))

    @staticmethod
    def _group_slides(effects: list[dict]) -> dict[str, list[dict]]:
        """슬라이드별로 FX를 그룹핑 (Video 타입 제외)."""
        groups: dict[str, list[dict]] = {}
        for eff in effects:
            if eff.get("type") == "Video":
                continue
            m = re.match(r'^(p\d+)', eff.get("id", ""))
            slide = m.group(1) if m else "misc"
            groups.setdefault(slide, []).append(eff)
        return dict(sorted(groups.items(), key=lambda x: (len(x[0]), x[0])))

    def _do_render(self):
        renders_dir = self._renders
        renders_dir.mkdir(parents=True, exist_ok=True)

        # 슬라이드 그룹핑
        effects_all = self._plan.get("effects", [])
        slides      = self._group_slides(effects_all)

        # Diff-Check: 슬라이드 내 어떤 FX가 바뀌었으면 해당 슬라이드 재렌더
        changed_fx_ids, new_cache = diff_check_effects(self._cache_path, self._plan)
        changed_fx_set = set(changed_fx_ids)

        changed_slides: list[str] = []
        skip_slides:    list[str] = []
        for sid, effs in slides.items():
            slide_fx_ids = {e["id"] for e in effs}
            if slide_fx_ids & changed_fx_set:
                changed_slides.append(sid)
            else:
                skip_slides.append(sid)

        for sid in skip_slides:
            self.item_skip.emit(sid)

        if not changed_slides:
            self.finished.emit(new_cache)
            return

        total = len(changed_slides)
        fps   = self._plan.get("fps", 30)

        # node_modules 미설치 시 npm install 선행
        if not (self._remotion / "node_modules").exists():
            self.progress.emit(0, total)
            ret = subprocess.run(
                [_NPM, "install"],
                cwd=str(self._remotion),
                capture_output=True, text=True,
            )
            if ret.returncode != 0:
                self.error.emit(f"npm install 실패:\n{ret.stderr[:800]}")
                return

        for idx, sid in enumerate(changed_slides, start=1):
            if self._abort:
                self.error.emit("렌더링이 사용자에 의해 중단되었습니다.")
                return

            # 슬라이드 duration = 해당 슬라이드 FX들의 총 길이
            effs        = slides[sid]
            slide_start = min(e.get("startFrame", 0) for e in effs)
            slide_end   = max(
                e.get("startFrame", 0) + e.get("durationFrames", 60)
                for e in effs
            )
            slide_dur   = slide_end - slide_start

            # Remotion 4.x: ID 언더스코어 불가
            comp_id = f"VividSlide-{sid.replace('_', '-')}"
            out_w   = renders_dir / f"slide_{sid}.webm"

            self.progress.emit(idx - 1, total)

            cmd = [
                _NPX, "remotion", "render",
                "src/index.ts",
                comp_id,
                str(out_w),
                "--codec=vp8",
                "--pixel-format=yuva420p",
                f"--frames=0-{slide_dur - 1}",
                '--props={"previewMode":false}',   # 배경/자막 제외 → 투명 FX만
                "--overwrite",
            ]

            ret = subprocess.run(
                cmd,
                cwd=str(self._remotion),
                capture_output=True, text=True,
            )

            if ret.returncode != 0:
                self.error.emit(
                    f"[{sid}] 렌더링 실패 (exit {ret.returncode}):\n"
                    f"{ret.stderr[-600:]}"
                )
                return

            self.item_done.emit(sid, str(out_w))
            self.progress.emit(idx, total)

        self.finished.emit(new_cache)


# ══════════════════════════════════════════════
# VrewWorker  (QThread)
# ══════════════════════════════════════════════

class VrewWorker(QObject):
    """최종 Vrew 파일 조립 워커"""
    finished = Signal(str)   # 출력 .vrew 경로
    error    = Signal(str)

    def __init__(
        self,
        asset_dir: Path,
        plan: dict,
        renders_dir: Path,
        fps: int = 30,
        parent=None,
    ):
        super().__init__(parent)
        self._asset   = asset_dir
        self._plan    = plan
        self._renders = renders_dir
        self._fps     = fps

    def run(self):
        try:
            out = assemble_vrew(self._asset, self._plan, self._renders, self._fps)
            self.finished.emit(str(out))
        except Exception as e:
            self.error.emit(str(e))


# ══════════════════════════════════════════════
# GeminiWorker  (QThread — Gemini API 호출)
# ══════════════════════════════════════════════

class GeminiWorker(QObject):
    """
    Gemini CLI를 이용해 슬라이드 대본을 분석하고
    핵심 키워드 + 연출 분위기 요약문을 반환하는 워커.
    """
    finished = Signal(str)   # 분석 결과 텍스트
    error    = Signal(str)

    def __init__(self, script_text: str, api_key: str = "", parent=None):
        super().__init__(parent)
        self._script  = script_text

    def run(self):
        try:
            # ── 1. 프롬프트 구성 ─────────────────────────────────────────
            prompt = (
                "아래는 유튜브 영상 대본입니다. 슬라이드별로 다음 항목을 분석하여 정리해주세요:\n\n"
                "1. 핵심 키워드 (3개 이내)\n"
                "2. 연출 분위기 (예: 긴박, 충격, 감동, 해설, 유머 등)\n"
                "3. 권장 시각 효과 방향 (간략하게 1~2줄)\n\n"
                "대본:\n"
                "────────────────────────────────────────\n"
                f"{self._script}\n"
                "────────────────────────────────────────\n\n"
                "슬라이드가 여러 개인 경우 [슬라이드 N] 구분을 유지하며 각각 분석해주세요."
            )

            # ── 2. Gemini CLI 호출 ───────────────────────────────────────
            result = _call_gemini_cli(prompt)
            self.finished.emit(result)

        except Exception as e:
            self.error.emit(f"Gemini 분석 오류: {e}")


# ══════════════════════════════════════════════
# SemanticMatchWorker  (QThread — Gemini 시맨틱 매칭)
# ══════════════════════════════════════════════

class SemanticMatchWorker(QObject):
    """
    fx_catalog.txt 전체 내용 + Custom FX 설명들을 Gemini에 전송하여
    각 효과에 맞는 컴포넌트명을 일괄 시맨틱 매칭한다.

    반환 Signal: dict[str, str]  — {effect_id: componentName}
    """
    finished = Signal(object)   # dict[str, str]
    error    = Signal(str)

    def __init__(self, custom_effects: list[dict], catalog_text: str, parent=None):
        super().__init__(parent)
        self._effects = custom_effects
        self._catalog = catalog_text

    def run(self):
        try:
            # ── 1. 프롬프트 조합 ──────────────────────────────────────────
            effect_lines = "\n".join(
                f'  - id: "{e.get("id","")}", description: "{e.get("description","(없음)")}"'
                for e in self._effects
            )

            prompt = (
                "당신은 Remotion FX 컴포넌트 매칭 전문가입니다.\n\n"
                "아래는 현재 프로젝트에서 사용 가능한 FX 컴포넌트 카탈로그입니다:\n"
                "---\n"
                f"{self._catalog}\n"
                "---\n\n"
                "아래는 영상 기획안에 포함된 Custom FX 효과들입니다:\n"
                f"{effect_lines}\n\n"
                "각 Custom FX 효과에 대해 카탈로그에서 가장 적합한 컴포넌트를 1개 골라주세요.\n"
                "반드시 아래 JSON 형식으로만 응답하세요 (마크다운 코드블록, 설명 없이 JSON만):\n"
                '{\n'
                '  "matches": [\n'
                '    {"id": "effect_id_1", "componentName": "ExactComponentName1"},\n'
                '    {"id": "effect_id_2", "componentName": "ExactComponentName2"}\n'
                '  ]\n'
                '}\n\n'
                "카탈로그에 실제로 존재하는 컴포넌트 이름만 사용하세요. "
                "적합한 컴포넌트가 없으면 가장 가까운 것을 선택하세요."
            )

            # ── 2. Gemini CLI 호출 ───────────────────────────────────────
            raw = _call_gemini_cli(prompt)

            # ── 3. JSON 파싱 ──────────────────────────────────────────────
            json_match = re.search(r'\{[\s\S]*\}', raw)
            if not json_match:
                raise ValueError(f"Gemini 응답에서 JSON을 찾을 수 없습니다.\n응답 원문:\n{raw[:400]}")

            result  = json.loads(json_match.group())
            matches = {
                m["id"]: m["componentName"]
                for m in result.get("matches", [])
                if "id" in m and "componentName" in m
            }

            if not matches:
                raise ValueError("Gemini가 빈 매칭 결과를 반환했습니다.")

            self.finished.emit(matches)

        except Exception as e:
            self.error.emit(f"시맨틱 매칭 오류: {e}")
