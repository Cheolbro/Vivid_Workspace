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
    Gemini API를 이용해 슬라이드 대본을 분석하고
    핵심 키워드 + 연출 분위기 요약문을 반환하는 워커.
    """
    finished = Signal(str)   # 분석 결과 텍스트
    error    = Signal(str)

    def __init__(self, script_text: str, api_key: str = "", parent=None):
        super().__init__(parent)
        self._api_key = api_key
        self._script  = script_text

    def run(self):
        # ── 1. google-genai 임포트 확인 ─────────────────────────────────
        try:
            from google import genai  # type: ignore
        except ImportError:
            self.error.emit(
                "google-genai 라이브러리가 설치되어 있지 않습니다.\n"
                "터미널에서 아래 명령어를 실행해 설치하세요:\n"
                "  pip install google-genai"
            )
            return

        try:
            # ── 2. 인증 방식 선택 ────────────────────────────────────────
            #    client_secret.json 이 ROOT_DIR 에 있으면 OAuth2 우선 사용.
            #    없으면 API Key fallback.
            _client_secret = ROOT_DIR / "client_secret.json"

            if _client_secret.exists():
                # OAuth2 경로
                try:
                    from utils.google_auth import get_genai_client
                    client = get_genai_client()
                except ImportError as imp_err:
                    self.error.emit(str(imp_err))
                    return
                except Exception as auth_err:
                    self.error.emit(f"OAuth2 인증 중 오류 발생:\n{auth_err}")
                    return
            else:
                # API Key fallback
                if not self._api_key:
                    self.error.emit(
                        "Gemini API Key가 입력되지 않았습니다.\n"
                        "OAuth 사용 시 client_secret.json을 프로젝트 루트에 배치하세요."
                    )
                    return
                client = genai.Client(api_key=self._api_key)

            # ── 3. 모델 호출 ─────────────────────────────────────────────
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

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            self.finished.emit(response.text)

        except Exception as e:
            err_msg = str(e)
            _using_oauth = (ROOT_DIR / "client_secret.json").exists()
            if "API_KEY" in err_msg.upper() or "invalid" in err_msg.lower():
                if _using_oauth:
                    self.error.emit(
                        f"OAuth 인증은 성공했으나 API 호출에 실패했습니다.\n"
                        f"Google AI Pro 구독 상태 및 API 권한을 확인하세요.\n\n원본 오류: {err_msg[:200]}"
                    )
                else:
                    self.error.emit(
                        f"API Key가 유효하지 않습니다.\n"
                        f"OAuth를 사용하려면 client_secret.json을 루트에 배치하세요.\n\n원본 오류: {err_msg[:200]}"
                    )
            elif "gemini-2.5-flash" in err_msg:
                self.error.emit(
                    f"gemini-2.5-flash 모델에 접근할 수 없습니다.\n"
                    f"{'OAuth 계정의 Google AI Pro 구독을 확인하세요.' if _using_oauth else 'API Key 권한 또는 모델명을 확인하세요.'}\n\n원본 오류: {err_msg[:200]}"
                )
            else:
                self.error.emit(f"Gemini API 오류:\n{err_msg[:300]}")


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
        import re as _re

        # ── 1. google-genai 임포트 확인 ─────────────────────────────────
        try:
            from google import genai  # type: ignore  # noqa: F401
        except ImportError:
            self.error.emit(
                "google-genai 라이브러리가 설치되어 있지 않습니다.\n"
                "  pip install google-genai"
            )
            return

        # ── 2. OAuth 인증 → Client 생성 ───────────────────────────────
        try:
            from utils.google_auth import get_genai_client
            client = get_genai_client()
        except Exception as auth_err:
            self.error.emit(f"OAuth 인증 실패:\n{auth_err}")
            return

        # ── 3. 프롬프트 조합 ──────────────────────────────────────────
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

        # ── 4. Gemini 호출 (503/UNAVAILABLE 최대 3회 재시도) ────────────
        _TRANSIENT_CODES = ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED")
        MAX_RETRIES = 3
        RETRY_DELAY = 5  # seconds
        raw = ""

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                )
                raw = response.text.strip()
                break  # 성공 → 루프 탈출
            except Exception as e:
                err_str = str(e)
                is_transient = any(c in err_str for c in _TRANSIENT_CODES)
                if is_transient and attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * attempt)
                    continue  # 재시도
                self.error.emit(
                    f"시맨틱 매칭 오류 (시도 {attempt}/{MAX_RETRIES}):\n{e}"
                )
                return

        if not raw:
            self.error.emit(f"시맨틱 매칭 최대 재시도 초과 ({MAX_RETRIES}회)")
            return

        # ── 5. JSON 파싱 ──────────────────────────────────────────────
        try:
            # JSON 추출 (응답에 마크다운이 섞여 있어도 처리)
            json_match = _re.search(r'\{[\s\S]*\}', raw)
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
            self.error.emit(f"시맨틱 매칭 JSON 파싱 오류:\n{e}")
