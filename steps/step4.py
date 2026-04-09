"""
steps/step4.py
4단계 — 영상 기획안 및 조립

① 기획안 업로드  : remotion_plan.json 파싱 + Custom FX 동적 생성 + 역주입
② Remotion 미리보기 : npx remotion studio (브라우저 자동 오픈)
③ Remotion 투명 렌더링 : Diff-Check 기반 부분 렌더 (QThread 비동기)
                         렌더 완료 시 소요시간/렌더 수/캐시 수 골드 리포트 출력
④ 최종 Vrew 생성 : 원본.vrew + webm → 최종_vN.vrew (QThread 비동기)
⑤ Vrew 열기     : subprocess로 Vrew 프로그램 실행
⑥ FX 카탈로그 보기 : 갤러리 팝업 (★ 즐겨찾기 / 메모리 캐시)
⑦ 기획 지시문 복사 : Gemini API → 슬라이드별 요약 → 클립보드 복사

Vrew 구조 (실물 분석):
  .vrew = ZIP(project.json + media/)
  project.json: files[] / transcript.clips[] / props.tracks{} / props.assets{}
"""

import json
import re
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QObject, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QStackedWidget, QFileDialog,
    QProgressBar, QLineEdit, QApplication,
    QDialog, QTextEdit, QFrame,
)

from utils.theme import C_HIGHLIGHT, C_SUCCESS, C_ERROR, C_BG_INPUT, C_BORDER, C_TEXT
from utils.widgets import (
    make_title, make_divider, make_status_box,
    StatusLogger, DropZone,
)
from utils.backend_ext import (
    generate_custom_fx_component, update_fx_catalog,
    generate_compositions, diff_check_effects, save_render_cache,
    assemble_vrew,
)
from utils.fx_gallery import FxGalleryDialog, invalidate_cache as invalidate_fx_cache

ROOT_DIR     = Path(__file__).parent.parent   # Vivid_Workspace/
CATALOG_PATH = ROOT_DIR / "fx_catalog.md"
CONFIG_PATH  = ROOT_DIR / "config.json"


# ══════════════════════════════════════════════
# 기획안 파싱 헬퍼
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


def _process_custom_fx(plan: dict, remotion_dir: Path) -> tuple[dict, list[str]]:
    """
    effects[] 중 type=Custom 항목에 대해:
    1) TSX 컴포넌트 생성 → fx_catalog.md 등재
    2) specificProps 역주입
    반환: (updated_plan, generated_component_names)
    """
    fx_dir    = remotion_dir / "src" / "components" / "fx"
    generated = []

    for eff in plan["effects"]:
        if eff.get("type") != "Custom":
            continue

        info = generate_custom_fx_component(eff, fx_dir)
        update_fx_catalog(CATALOG_PATH, info)
        invalidate_fx_cache()   # 카탈로그 업데이트 → 갤러리 캐시 초기화

        # 역주입: specificProps에 default 값 병합
        if "specificProps" not in eff or not eff["specificProps"]:
            eff["specificProps"] = {}
        for k, v in info["defaultProps"].items():
            eff["specificProps"].setdefault(k, v)

        # 컴포넌트 참조 정보 주입
        eff["_componentName"] = info["componentName"]
        eff["_componentFile"] = info["fileName"]

        generated.append(info["componentName"])

    return plan, generated


# ══════════════════════════════════════════════
# PreflightDialog  — Custom FX 사전 검수 팝업
# ══════════════════════════════════════════════

class PreflightDialog(QDialog):
    """
    렌더링 직전 Custom FX 항목을 일괄 검출하여 표시하는 Human-in-the-loop 팝업.

    흐름:
      1) _on_render_click() 이 effects[] 에서 type=Custom 항목을 추출
      2) Custom 항목이 있으면 이 다이얼로그를 exec() (모달)
      3) 파이썬이 통합 지시문 프롬프트를 자동 조합하여 QTextEdit에 표시
      4) 사용자가 프롬프트를 복사 → 터미널 Claude Code 에 전달 → 코딩 완료
      5) '코딩 완료 (렌더링 계속)' 클릭 → accept() → 렌더링 재개
    """

    def __init__(self, custom_effects: list[dict], parent=None):
        super().__init__(parent)
        self._custom_effects = custom_effects
        self._prompt_text    = self._build_prompt(custom_effects)

        self.setWindowTitle("⚙️  Custom FX 사전 검수 (Pre-flight Check)")
        self.setMinimumSize(700, 440)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setStyleSheet(
            f"QDialog {{ background:{C_BG_INPUT}; color:{C_TEXT}; }}"
            f"QLabel  {{ color:{C_TEXT}; }}"
        )
        self._build_ui()

    # ── 프롬프트 자동 조합 ──────────────────────────────────────────────

    @staticmethod
    def _build_prompt(effects: list[dict]) -> str:
        lines = [
            "기획안에 포함된 아래 Custom 효과들을 "
            "src/components/fx/ 폴더에 각각 TSX 컴포넌트로 코딩해 줘. "
            "사용할 commonProps와 specificProps의 기본값을 세팅하고, "
            "완성 후 fx_catalog.md에 등록해 줘.\n",
        ]
        for eff in effects:
            eid  = eff.get("id", "(id없음)")
            desc = eff.get("description", "(설명없음)")
            lines.append(f"- [id: {eid}] 연출 설명: {desc}")
        return "\n".join(lines)

    # ── UI 구성 ─────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        # 경고 배너
        banner = QLabel(
            f"🚧  새로운 Custom 시각 효과 코딩이 필요합니다  "
            f"({len(self._custom_effects)}개 항목)"
        )
        banner.setStyleSheet(
            f"background:{C_HIGHLIGHT}; color:#000000; font-size:13px;"
            "font-weight:bold; padding:8px 12px; border-radius:4px;"
        )
        banner.setWordWrap(True)
        root.addWidget(banner)

        # 안내문
        guide = QLabel(
            "아래 프롬프트를 복사하여 터미널의 Claude Code에 전달하세요.\n"
            "Claude가 TSX 컴포넌트 코딩을 완료하면 '코딩 완료' 버튼을 클릭하여 렌더링을 계속하세요."
        )
        guide.setStyleSheet("color:#AAAAAA; font-size:11px;")
        guide.setWordWrap(True)
        root.addWidget(guide)

        # 항목 목록 요약 (골드)
        items_label = QLabel(
            "  •  " + "\n  •  ".join(
                f"[{e.get('id','?')}]  {e.get('description','')[:60]}"
                for e in self._custom_effects
            )
        )
        items_label.setStyleSheet(
            f"color:{C_HIGHLIGHT}; font-size:11px;"
            f"background:#1A1A1A; border:1px solid {C_BORDER};"
            "border-radius:4px; padding:8px 12px;"
        )
        items_label.setWordWrap(True)
        root.addWidget(items_label)

        # 구분선
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet(f"color:{C_BORDER};")
        root.addWidget(div)

        # 통합 지시문 프롬프트 텍스트 박스
        prompt_label = QLabel("📋  Claude Code 전달용 통합 지시문 프롬프트")
        prompt_label.setStyleSheet(
            f"color:{C_TEXT}; font-size:11px; font-weight:bold;"
        )
        root.addWidget(prompt_label)

        self._prompt_box = QTextEdit()
        self._prompt_box.setReadOnly(True)
        self._prompt_box.setPlainText(self._prompt_text)
        self._prompt_box.setStyleSheet(
            f"background:#111111; color:#DDDDDD; font-family:Consolas,monospace;"
            f"font-size:11px; border:1px solid {C_BORDER}; border-radius:4px;"
            "padding:8px;"
        )
        self._prompt_box.setFixedHeight(140)
        root.addWidget(self._prompt_box)

        # 버튼 행
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        copy_btn = QPushButton("📋  프롬프트 복사")
        copy_btn.setStyleSheet(
            f"background:#2A2A2A; color:{C_TEXT}; border:1px solid {C_BORDER};"
            "padding:6px 16px; border-radius:4px;"
        )
        copy_btn.clicked.connect(self._on_copy)
        btn_row.addWidget(copy_btn)

        btn_row.addStretch()

        cancel_btn = QPushButton("취소")
        cancel_btn.setFixedWidth(70)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        confirm_btn = QPushButton("✅  코딩 완료 (렌더링 계속)")
        confirm_btn.setStyleSheet(
            f"background:{C_SUCCESS}; color:#000000; font-weight:bold;"
            "padding:6px 20px; border-radius:4px;"
        )
        confirm_btn.setDefault(True)
        confirm_btn.clicked.connect(self._on_confirm)
        btn_row.addWidget(confirm_btn)

        root.addLayout(btn_row)

    # ── 핸들러 ──────────────────────────────────────────────────────────

    def _on_copy(self):
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(self._prompt_text)
            # 복사 버튼 일시적 피드백
            sender = self.sender()
            if isinstance(sender, QPushButton):
                sender.setText("✔  복사됨!")
                QTimer.singleShot(1800, lambda: sender.setText("📋  프롬프트 복사"))

    def _on_confirm(self):
        self.accept()


# ══════════════════════════════════════════════
# RenderWorker  (QThread — UI 블로킹 방지)
# ══════════════════════════════════════════════

class RenderWorker(QObject):
    """
    Remotion 투명 렌더링 워커.
    Diff-Check 결과 변경된 FX 항목만 npx remotion render 로 렌더링.
    """
    progress  = Signal(int, int)       # (current, total)
    item_done = Signal(str, str)       # (effect_id, webm_path_str)
    item_skip = Signal(str)            # (effect_id) — 변경 없어 스킵
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

    def _do_render(self):
        renders_dir = self._renders
        renders_dir.mkdir(parents=True, exist_ok=True)

        changed_ids, new_cache = diff_check_effects(self._cache_path, self._plan)
        effects = {e["id"]: e for e in self._plan.get("effects", [])}

        # 스킵 항목 알림
        for eid in effects:
            if eid not in changed_ids:
                self.item_skip.emit(eid)

        if not changed_ids:
            self.finished.emit(new_cache)
            return

        total = len(changed_ids)
        fps   = self._plan.get("fps", 30)

        # node_modules 미설치 시 npm install 선행
        node_modules = self._remotion / "node_modules"
        if not node_modules.exists():
            self.progress.emit(0, total)
            ret = subprocess.run(
                ["npm", "install"],
                cwd=str(self._remotion),
                capture_output=True, text=True,
            )
            if ret.returncode != 0:
                self.error.emit(f"npm install 실패:\n{ret.stderr[:800]}")
                return

        for idx, eid in enumerate(changed_ids, start=1):
            if self._abort:
                self.error.emit("렌더링이 사용자에 의해 중단되었습니다.")
                return

            eff     = effects[eid]
            dur_f   = eff.get("durationFrames", 60)
            out_w   = renders_dir / f"{eid}.webm"
            comp_id = f"VividFX_{eid}"

            self.progress.emit(idx - 1, total)

            cmd = [
                "npx", "remotion", "render",
                "src/index.ts",
                comp_id,
                str(out_w),
                "--codec=vp8",
                "--pixel-format=yuva420p",
                f"--frames=0-{dur_f - 1}",
                "--overwrite",
            ]

            ret = subprocess.run(
                cmd,
                cwd=str(self._remotion),
                capture_output=True, text=True,
            )

            if ret.returncode != 0:
                self.error.emit(
                    f"[{eid}] 렌더링 실패 (exit {ret.returncode}):\n"
                    f"{ret.stderr[-600:]}"
                )
                return

            self.item_done.emit(eid, str(out_w))
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

    def __init__(self, api_key: str, script_text: str, parent=None):
        super().__init__(parent)
        self._api_key = api_key
        self._script  = script_text

    def run(self):
        try:
            import google.generativeai as genai  # type: ignore
        except ImportError:
            self.error.emit(
                "google-generativeai 라이브러리가 설치되어 있지 않습니다.\n"
                "터미널에서 아래 명령어를 실행해 설치하세요:\n"
                "  pip install google-generativeai"
            )
            return

        try:
            genai.configure(api_key=self._api_key)
            model = genai.GenerativeModel("gemini-2.5-flash")

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

            response = model.generate_content(prompt)
            self.finished.emit(response.text)

        except Exception as e:
            err_msg = str(e)
            # 흔한 오류 친절 설명
            if "API_KEY" in err_msg.upper() or "invalid" in err_msg.lower():
                self.error.emit(
                    f"API Key가 유효하지 않습니다.\n올바른 Gemini API Key를 입력하세요.\n\n원본 오류: {err_msg[:200]}"
                )
            elif "gemini-2.5-flash" in err_msg:
                self.error.emit(
                    f"gemini-2.5-flash 모델에 접근할 수 없습니다.\n"
                    f"API Key 권한 또는 모델명을 확인하세요.\n\n원본 오류: {err_msg[:200]}"
                )
            else:
                self.error.emit(f"Gemini API 오류:\n{err_msg[:300]}")


# ══════════════════════════════════════════════
# Step4Widget
# ══════════════════════════════════════════════

class Step4Widget(QWidget):

    def __init__(self, stack: QStackedWidget, parent=None):
        super().__init__(parent)
        self._stack        = stack
        self._project_dir: Path | None = None
        self._plan: dict | None = None

        # 스레드 레퍼런스
        self._render_thread: QThread | None = None
        self._render_worker: RenderWorker | None = None
        self._vrew_thread:   QThread | None = None
        self._vrew_worker:   VrewWorker | None = None
        self._gemini_thread: QThread | None = None
        self._gemini_worker: GeminiWorker | None = None

        # 타이밍 추적 (최종 리포트용)
        self._render_start_time: float | None = None
        self._render_done_count: int = 0
        self._skip_count:        int = 0

        self._latest_vrew: Path | None = None

        self._build_ui()

    # ── UI 구성 ──────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 32, 24)
        root.setSpacing(12)

        root.addWidget(make_title("4. 영상 기획안 및 조립"))

        # 상태창
        self._status_box = make_status_box()
        root.addWidget(self._status_box)
        self._log = StatusLogger(self._status_box)

        root.addWidget(make_divider())

        # ─────────────────────────────────────────────────
        # STEP A: 기획안 업로드
        # ─────────────────────────────────────────────────
        lbl_a = QLabel("[ STEP A ]  영상 기획안 업로드 (remotion_plan.json)")
        lbl_a.setStyleSheet(
            f"color:{C_HIGHLIGHT}; font-size:12px; font-weight:bold;"
        )
        root.addWidget(lbl_a)

        self._drop_zone = DropZone(
            label="remotion_plan.json 파일을 여기에 끌어다 놓으세요\n(또는 아래 버튼으로 선택)",
            accepted_ext=".json",
        )
        self._drop_zone.file_dropped.connect(self._on_plan_received)
        root.addWidget(self._drop_zone)

        row_a = QHBoxLayout()
        row_a.setSpacing(10)

        self._upload_btn = QPushButton("📁  기획안 업로드")
        self._upload_btn.clicked.connect(self._on_upload_click)
        row_a.addWidget(self._upload_btn)

        self._fx_gallery_btn = QPushButton("🎨  FX 카탈로그 보기")
        self._fx_gallery_btn.setToolTip(
            "현재 등록된 FX 효과 목록을 갤러리로 확인하고 즐겨찾기를 등록합니다."
        )
        self._fx_gallery_btn.clicked.connect(self._on_fx_gallery_click)
        row_a.addWidget(self._fx_gallery_btn)

        row_a.addStretch()
        root.addLayout(row_a)

        # 파일명 정규화 안내
        plan_hint = QLabel(
            "※ 업로드 시 파일명에 상관없이 remotion_plan.json 으로 자동 변환되어 저장됩니다."
        )
        plan_hint.setStyleSheet(
            f"color:{C_HIGHLIGHT}; font-size:11px;"
        )
        plan_hint.setWordWrap(True)
        root.addWidget(plan_hint)

        root.addWidget(make_divider())

        # ─────────────────────────────────────────────────
        # STEP B: Remotion 제어
        # ─────────────────────────────────────────────────
        lbl_b = QLabel("[ STEP B ]  Remotion 미리보기 / 투명 렌더링")
        lbl_b.setStyleSheet(
            f"color:{C_HIGHLIGHT}; font-size:12px; font-weight:bold;"
        )
        root.addWidget(lbl_b)

        row_b = QHBoxLayout()
        row_b.setSpacing(10)

        self._preview_btn = QPushButton("▶  Remotion 미리보기")
        self._preview_btn.setEnabled(False)
        self._preview_btn.setToolTip(
            "Remotion Studio를 열어 시각 효과 타이밍을 실시간 검수합니다"
        )
        self._preview_btn.clicked.connect(self._on_preview_click)
        row_b.addWidget(self._preview_btn)

        self._render_btn = QPushButton("🎬  Remotion 투명 렌더링")
        self._render_btn.setEnabled(False)
        self._render_btn.setToolTip(
            "배경 투명 .webm 파일 생성 (변경된 FX만 재렌더링 — Diff Check)"
        )
        self._render_btn.clicked.connect(self._on_render_click)
        row_b.addWidget(self._render_btn)

        self._abort_btn = QPushButton("⏹  중단")
        self._abort_btn.setEnabled(False)
        self._abort_btn.clicked.connect(self._on_abort_click)
        row_b.addWidget(self._abort_btn)

        row_b.addStretch()
        root.addLayout(row_b)

        # 진행 바
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setTextVisible(True)
        self._progress.setStyleSheet(
            f"QProgressBar {{ background:{C_BG_INPUT}; border:1px solid {C_BORDER};"
            f"border-radius:4px; height:18px; }}"
            f"QProgressBar::chunk {{ background:{C_SUCCESS}; border-radius:3px; }}"
        )
        root.addWidget(self._progress)

        root.addWidget(make_divider())

        # ─────────────────────────────────────────────────
        # STEP C: Vrew 조립
        # ─────────────────────────────────────────────────
        lbl_c = QLabel("[ STEP C ]  최종 Vrew 파일 생성")
        lbl_c.setStyleSheet(
            f"color:{C_HIGHLIGHT}; font-size:12px; font-weight:bold;"
        )
        root.addWidget(lbl_c)

        row_c = QHBoxLayout()
        row_c.setSpacing(10)

        self._vrew_btn = QPushButton("📦  최종 Vrew 파일 생성")
        self._vrew_btn.setEnabled(False)
        self._vrew_btn.clicked.connect(self._on_vrew_click)
        row_c.addWidget(self._vrew_btn)

        self._open_btn = QPushButton("🎞  Vrew 열기")
        self._open_btn.setEnabled(False)
        self._open_btn.clicked.connect(self._on_open_vrew)
        row_c.addWidget(self._open_btn)

        row_c.addStretch()
        root.addLayout(row_c)

        root.addWidget(make_divider())

        # ─────────────────────────────────────────────────
        # STEP D: Gemini API — 기획 지시문 복사
        # ─────────────────────────────────────────────────
        lbl_d = QLabel("[ STEP D ]  AI 기획 지시문 생성 (Gemini API)")
        lbl_d.setStyleSheet(
            f"color:{C_HIGHLIGHT}; font-size:12px; font-weight:bold;"
        )
        root.addWidget(lbl_d)

        api_row = QHBoxLayout()
        api_row.setSpacing(8)

        api_label = QLabel("API Key:")
        api_label.setStyleSheet(f"color:{C_TEXT}; font-size:11px;")
        api_label.setFixedWidth(60)
        api_row.addWidget(api_label)

        self._api_key_input = QLineEdit()
        self._api_key_input.setPlaceholderText(
            "Gemini API Key 입력  (예: AIzaSy...)"
        )
        self._api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_input.setStyleSheet(
            f"background:{C_BG_INPUT}; color:{C_TEXT}; border:1px solid {C_BORDER};"
            "border-radius:4px; padding:4px 8px; font-size:11px;"
        )
        api_row.addWidget(self._api_key_input)

        save_key_btn = QPushButton("💾  저장")
        save_key_btn.setFixedWidth(60)
        save_key_btn.setToolTip("API Key를 config.json에 암호화 없이 저장합니다.")
        save_key_btn.clicked.connect(self._on_save_api_key)
        api_row.addWidget(save_key_btn)

        root.addLayout(api_row)

        directive_row = QHBoxLayout()
        directive_row.setSpacing(10)

        self._directive_btn = QPushButton("✨  기획 지시문 생성 및 클립보드 복사")
        self._directive_btn.setToolTip(
            "2단계에서 생성된 script_body_slide.txt를 Gemini에 전송하여\n"
            "슬라이드별 핵심 키워드 + 연출 분위기 요약을 생성 후 클립보드에 복사합니다."
        )
        self._directive_btn.clicked.connect(self._on_directive_click)
        directive_row.addWidget(self._directive_btn)
        directive_row.addStretch()
        root.addLayout(directive_row)

        root.addWidget(make_divider())

        # ─────────────────────────────────────────────────
        # 내비게이션
        # ─────────────────────────────────────────────────
        nav = QHBoxLayout()
        back_btn = QPushButton("◀  BACK")
        back_btn.clicked.connect(lambda: self._stack.setCurrentIndex(2))
        nav.addWidget(back_btn)
        nav.addStretch()
        root.addLayout(nav)
        root.addStretch()

    # ── 외부 주입 ─────────────────────────────────────────────────────────

    def set_project_dir(self, path: Path | None):
        self._project_dir = path
        self._plan        = None
        self._latest_vrew = None
        self._render_done_count = 0
        self._skip_count        = 0

        self._drop_zone.reset()
        self._log.clear()
        self._preview_btn.setEnabled(False)
        self._render_btn.setEnabled(False)
        self._vrew_btn.setEnabled(False)
        self._open_btn.setEnabled(False)
        self._progress.setVisible(False)

        if path:
            self._log.highlight(f"프로젝트: {path.name}")
            self._log.info(
                "제미나이(웹)에 storyboard.pdf와 fx_catalog.md를 참고하여 만든\n"
                "영상 기획안(remotion_plan.json)을 업로드 하세요."
            )
            self._load_api_key()   # 저장된 API Key 자동 로드

    # ── §A: 기획안 업로드 ────────────────────────────────────────────────

    def _on_upload_click(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "기획안 파일 선택", str(Path.home()), "JSON 파일 (*.json)"
        )
        if path:
            self._on_plan_received(path)

    def _on_plan_received(self, src_path: str):
        src = Path(src_path)

        # ── 하네스: 기본 검증 ──
        if src.suffix.lower() != ".json":
            self._log.error(f"'{src.name}'은(는) .json 파일이 아닙니다.")
            return
        if src.stat().st_size == 0:
            self._log.error(f"'{src.name}' 파일이 비어 있습니다 (0바이트).")
            return
        if self._project_dir is None:
            self._log.error("프로젝트 폴더가 없습니다. 1단계로 돌아가세요.")
            return

        # ── 저장 (파일명 정규화: 항상 remotion_plan.json으로 저장, Overwrite 허용) ──
        asset_dir = self._project_dir / "asset"
        asset_dir.mkdir(parents=True, exist_ok=True)
        dest = asset_dir / "remotion_plan.json"
        try:
            shutil.copy2(str(src), str(dest))
        except Exception as e:
            self._log.error(f"파일 저장 오류:\n{e}")
            return

        if src.name != "remotion_plan.json":
            self._log.info(f"파일명 정규화: '{src.name}'  →  'remotion_plan.json'")

        # ── JSON 파싱 & 검증 ──
        try:
            plan = parse_plan_json(dest)
        except (FileNotFoundError, ValueError) as e:
            self._log.error(str(e))
            self._drop_zone.set_error("JSON 파싱 실패 — 내용을 확인하세요")
            return

        # ── Custom FX 동적 생성 ──
        remotion_dir = self._project_dir / "remotion"
        try:
            plan, generated = _process_custom_fx(plan, remotion_dir)
        except Exception as e:
            self._log.error(f"Custom FX 생성 오류:\n{e}")
            return

        # 역주입된 plan 저장
        dest.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

        # ── Composition 파일 생성 ──
        try:
            generate_compositions(plan, remotion_dir)
        except Exception as e:
            self._log.error(f"Composition 생성 오류:\n{e}")
            return

        self._plan = plan
        effects = plan.get("effects", [])

        self._drop_zone.set_ready(src.name)
        self._log.success(
            f"기획안 파일이 입력되었습니다.\n"
            f"  · effects: {len(effects)}개"
            + (f"\n  · Custom FX 생성: {', '.join(generated)}" if generated else "")
            + "\nRemotion 버튼을 눌러 미리보기 또는 렌더링을 진행하세요."
        )

        if generated:
            self._log.highlight(
                f"fx_catalog.md에 {len(generated)}개 컴포넌트가 자동 등재되었습니다."
            )

        self._preview_btn.setEnabled(True)
        self._render_btn.setEnabled(True)

    # ── §A: FX 카탈로그 갤러리 ────────────────────────────────────────────

    def _on_fx_gallery_click(self):
        """FX 갤러리 팝업 열기 (캐시 있으면 즉시, 없으면 파싱 후 표시)"""
        dlg = FxGalleryDialog(CATALOG_PATH, parent=self)
        dlg.exec()

    # ── §B: 미리보기 ─────────────────────────────────────────────────────

    def _on_preview_click(self):
        if self._project_dir is None:
            return
        remotion_dir = self._project_dir / "remotion"
        self._log.info("Remotion Studio 시작 중... (잠시 후 브라우저가 열립니다)")

        try:
            subprocess.Popen(
                ["npx", "remotion", "studio", "src/index.ts"],
                cwd=str(remotion_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=(
                    subprocess.CREATE_NEW_PROCESS_GROUP
                    if sys.platform == "win32" else 0
                ),
            )
        except Exception as e:
            self._log.error(f"Remotion Studio 실행 실패:\n{e}")
            return

        QTimer.singleShot(2500, lambda: webbrowser.open("http://localhost:3000"))
        self._log.success("Remotion Studio 실행됨. 브라우저에서 미리보기를 확인하세요.")

    # ── §B: 투명 렌더링 ──────────────────────────────────────────────────

    def _on_render_click(self):
        """
        렌더링 버튼 인터셉트 — Pre-flight Check 후 렌더 시작.

        1) effects[] 에서 type=Custom 항목 추출
        2) Custom 없음 → 즉시 렌더 시작
        3) Custom 있음 → PreflightDialog 표시 (Human-in-the-loop)
           - '취소' → 렌더 중단
           - '코딩 완료' → 렌더 시작
        """
        if self._plan is None or self._project_dir is None:
            return

        custom_effects = [
            e for e in self._plan.get("effects", [])
            if e.get("type") == "Custom"
        ]

        if custom_effects:
            self._log.highlight(
                f"Custom FX {len(custom_effects)}개 감지 → Pre-flight Check 팝업을 표시합니다."
            )
            dlg = PreflightDialog(custom_effects, parent=self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                self._log.info("렌더링이 취소되었습니다.")
                return
            self._log.success("코딩 완료 확인. 렌더링을 시작합니다.")

        self._start_render()

    def _start_render(self):
        """Pre-flight Check 통과 후 실제 렌더 워커를 실행한다."""
        remotion_dir = self._project_dir / "remotion"
        renders_dir  = self._project_dir / "asset" / "renders"
        cache_path   = self._project_dir / "asset" / "render_cache.json"

        # 타이밍 & 카운터 초기화
        self._render_start_time  = time.time()
        self._render_done_count  = 0
        self._skip_count         = 0

        self._log.info("렌더링 준비 중 (Diff-Check 실행)...")
        self._render_btn.setEnabled(False)
        self._preview_btn.setEnabled(False)
        self._abort_btn.setEnabled(True)
        self._progress.setVisible(True)
        self._progress.setValue(0)

        self._render_thread = QThread(self)
        self._render_worker = RenderWorker(
            self._plan, remotion_dir, renders_dir, cache_path
        )
        self._render_worker.moveToThread(self._render_thread)

        self._render_thread.started.connect(self._render_worker.run)
        self._render_worker.progress.connect(self._on_render_progress)
        self._render_worker.item_done.connect(self._on_item_done)
        self._render_worker.item_skip.connect(self._on_item_skip)
        self._render_worker.finished.connect(self._on_render_finished)
        self._render_worker.error.connect(self._on_render_error)
        self._render_worker.finished.connect(self._render_thread.quit)
        self._render_worker.error.connect(self._render_thread.quit)

        self._render_thread.start()

    def _on_render_progress(self, cur: int, total: int):
        if total:
            self._progress.setMaximum(total)
            self._progress.setValue(cur)
            self._progress.setFormat(f"렌더링 중...  {cur}/{total}")

    def _on_item_done(self, eid: str, path: str):
        self._render_done_count += 1
        self._log.success(f"렌더 완료: {eid}  →  {Path(path).name}")

    def _on_item_skip(self, eid: str):
        self._skip_count += 1
        self._log.info(f"  [스킵] {eid}  — 변경 없음 (캐시 재사용)")

    def _on_render_finished(self, cache: dict):
        if self._project_dir:
            cache_path = self._project_dir / "asset" / "render_cache.json"
            save_render_cache(cache_path, cache)

        self._progress.setValue(self._progress.maximum())
        self._progress.setFormat("렌더링 완료")
        self._abort_btn.setEnabled(False)
        self._render_btn.setEnabled(True)
        self._preview_btn.setEnabled(True)
        self._vrew_btn.setEnabled(True)

        # ── 최종 리포트 (골드 텍스트) ──
        elapsed = 0.0
        if self._render_start_time is not None:
            elapsed = time.time() - self._render_start_time

        total_fx = self._render_done_count + self._skip_count
        m, s     = divmod(int(elapsed), 60)
        time_str = f"{m}분 {s}초" if m else f"{s}초"

        self._log.highlight(
            "━━━━━━━━  렌더링 완료 리포트  ━━━━━━━━\n"
            f"  ⏱  총 소요 시간   : {time_str}\n"
            f"  🎬  신규 렌더 FX  : {self._render_done_count}개\n"
            f"  ⚡  캐시 재사용   : {self._skip_count}개 (Diff-Check 절약)\n"
            f"  📦  전체 FX 합계  : {total_fx}개\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "'최종 Vrew 파일 생성' 버튼을 눌러 조립을 완료하세요."
        )

    def _on_render_error(self, msg: str):
        self._log.error(f"렌더링 오류:\n{msg}")
        self._abort_btn.setEnabled(False)
        self._render_btn.setEnabled(True)
        self._preview_btn.setEnabled(True)
        self._progress.setFormat("오류 발생")

    def _on_abort_click(self):
        if self._render_worker:
            self._render_worker.abort()
        self._abort_btn.setEnabled(False)
        self._log.highlight("렌더링 중단 요청 전송...")

    # ── §C: Vrew 조립 ────────────────────────────────────────────────────

    def _on_vrew_click(self):
        if self._plan is None or self._project_dir is None:
            return

        asset_dir   = self._project_dir / "asset"
        renders_dir = asset_dir / "renders"
        fps         = self._plan.get("fps", 30)

        self._log.info("최종 Vrew 파일 조립 중...")
        self._vrew_btn.setEnabled(False)

        self._vrew_thread = QThread(self)
        self._vrew_worker = VrewWorker(asset_dir, self._plan, renders_dir, fps)
        self._vrew_worker.moveToThread(self._vrew_thread)

        self._vrew_thread.started.connect(self._vrew_worker.run)
        self._vrew_worker.finished.connect(self._on_vrew_finished)
        self._vrew_worker.error.connect(self._on_vrew_error)
        self._vrew_worker.finished.connect(self._vrew_thread.quit)
        self._vrew_worker.error.connect(self._vrew_thread.quit)

        self._vrew_thread.start()

    def _on_vrew_finished(self, out_path: str):
        self._latest_vrew = Path(out_path)
        self._vrew_btn.setEnabled(True)
        self._open_btn.setEnabled(True)
        self._log.success(
            f"최종 Vrew 파일이 생성되었습니다.\n"
            f"  →  {Path(out_path).name}\n"
            "'Vrew 열기' 버튼으로 파일을 확인하세요."
        )

    def _on_vrew_error(self, msg: str):
        self._log.error(f"Vrew 조립 오류:\n{msg}")
        self._vrew_btn.setEnabled(True)

    # ── §D: Vrew 열기 ────────────────────────────────────────────────────

    def _on_open_vrew(self):
        if self._latest_vrew is None or not self._latest_vrew.exists():
            self._log.error("열 수 있는 Vrew 파일이 없습니다.")
            return
        try:
            if sys.platform == "win32":
                import os
                os.startfile(str(self._latest_vrew))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(self._latest_vrew)])
            else:
                subprocess.Popen(["xdg-open", str(self._latest_vrew)])
            self._log.success(f"Vrew 실행 요청: {self._latest_vrew.name}")
        except Exception as e:
            self._log.error(f"Vrew 열기 실패:\n{e}")

    # ── §E: Gemini API — 기획 지시문 ─────────────────────────────────────

    def _on_save_api_key(self):
        """API Key를 config.json에 저장"""
        key = self._api_key_input.text().strip()
        if not key:
            self._log.error("API Key를 입력하세요.")
            return
        try:
            cfg = {}
            if CONFIG_PATH.exists():
                try:
                    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                except Exception:
                    cfg = {}
            cfg["gemini_api_key"] = key
            CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
            self._log.success("API Key가 저장되었습니다.")
        except Exception as e:
            self._log.error(f"API Key 저장 실패:\n{e}")

    def _load_api_key(self):
        """시작 시 config.json에서 저장된 API Key 자동 로드"""
        try:
            if CONFIG_PATH.exists():
                cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                key = cfg.get("gemini_api_key", "")
                if key:
                    self._api_key_input.setText(key)
        except Exception:
            pass   # 파일 없거나 파싱 실패 시 무시

    def _on_directive_click(self):
        """기획 지시문 생성 + 클립보드 복사"""
        # 사전 조건 검사
        api_key = self._api_key_input.text().strip()
        if not api_key:
            self._log.error("Gemini API Key를 입력해주세요. (STEP D)")
            return

        if self._project_dir is None:
            self._log.error("프로젝트 폴더가 없습니다. 1단계로 돌아가세요.")
            return

        slide_txt = self._project_dir / "input" / "script_body_slide.txt"
        if not slide_txt.exists():
            self._log.error(
                "script_body_slide.txt 파일이 없습니다.\n"
                "2단계 '대본 변환' 버튼을 먼저 실행해주세요."
            )
            return
        if slide_txt.stat().st_size == 0:
            self._log.error("script_body_slide.txt 파일이 비어 있습니다 (0바이트).")
            return

        try:
            script_text = slide_txt.read_text(encoding="utf-8")
        except Exception as e:
            self._log.error(f"파일 읽기 오류:\n{e}")
            return

        self._log.info("Gemini API에 대본 분석 요청 중...\n(네트워크 상태에 따라 수 초 소요)")
        self._directive_btn.setEnabled(False)

        self._gemini_thread = QThread(self)
        self._gemini_worker = GeminiWorker(api_key, script_text)
        self._gemini_worker.moveToThread(self._gemini_thread)

        self._gemini_thread.started.connect(self._gemini_worker.run)
        self._gemini_worker.finished.connect(self._on_directive_done)
        self._gemini_worker.error.connect(self._on_directive_error)
        self._gemini_worker.finished.connect(self._gemini_thread.quit)
        self._gemini_worker.error.connect(self._gemini_thread.quit)

        self._gemini_thread.start()

    def _on_directive_done(self, result_text: str):
        self._directive_btn.setEnabled(True)

        # 클립보드 복사
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(result_text)
            self._log.success(
                "✅  AI 기획 지시문 생성 완료!\n"
                "클립보드에 복사되었습니다. 제미나이(웹)에 바로 붙여넣기 하세요.\n"
                f"  (분석 글자 수: {len(result_text)}자)"
            )
        else:
            self._log.highlight(
                "기획 지시문 생성 완료 (클립보드 접근 실패).\n"
                "결과:\n" + result_text[:500]
            )

    def _on_directive_error(self, msg: str):
        self._directive_btn.setEnabled(True)
        self._log.error(f"기획 지시문 생성 실패:\n{msg}")

    # ── 정리 ─────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        if self._render_worker:
            self._render_worker.abort()
        for t in (self._render_thread, self._vrew_thread, self._gemini_thread):
            if t and t.isRunning():
                t.quit()
                t.wait(2000)
        super().closeEvent(event)
