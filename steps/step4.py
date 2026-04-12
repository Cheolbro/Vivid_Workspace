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
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QStackedWidget, QFileDialog,
    QProgressBar, QApplication,
    QDialog, QTextEdit, QFrame, QScrollArea,
)

from utils.theme import C_HIGHLIGHT, C_SUCCESS, C_ERROR, C_BG_INPUT, C_BORDER, C_TEXT, SHARED_FX_DIR
from utils.widgets import (
    make_title, make_divider, make_status_box,
    StatusLogger, DropZone,
)
from utils.backend_ext import generate_compositions, save_render_cache
from utils.fx_gallery import FxGalleryDialog
from utils.step4_workers import (
    ROOT_DIR, CATALOG_PATH, CONFIG_PATH, _NPX, _NPM,
    parse_plan_json, detect_custom_fx,
    RenderWorker, VrewWorker, GeminiWorker, SemanticMatchWorker,
)


def _find_free_port(start: int, end: int) -> int:
    import socket
    for p in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('127.0.0.1', p))
                return p
            except OSError:
                continue
    return start


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
            "기획안에 포함된 아래 Custom 효과들을 글로벌 공유 폴더(shared_assets/shared_fx/)에 "
            "TSX 컴포넌트로 코딩해 줘. 이 효과들은 모든 프로젝트가 심볼릭 링크로 공유하는 공용 자산이야.\n\n"
            "* 다른 프로젝트에서도 범용적으로 쓸 수 있게 commonProps와 specificProps의 기본값을 정교하게 세팅해 줘.\n"
            "* 코딩 완료 후 **루트의 fx_catalog.txt**에 카탈로그 정보를 최신화해 줘.\n"
            "* (참고) 현재 프로젝트의 src/components/fx/는 글로벌 폴더와 심볼릭 링크로 연결되어 있으니 경로 참조에 유의해.\n",
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
        self._match_thread:  QThread | None = None
        self._match_worker:  "SemanticMatchWorker | None" = None

        # 타이밍 추적 (최종 리포트용)
        self._render_start_time: float | None = None
        self._render_done_count: int = 0
        self._skip_count:        int = 0

        self._latest_vrew: Path | None = None

        # Remotion Studio 프로세스 (중복 실행 방지)
        self._studio_proc: subprocess.Popen | None = None
        self._studio_port: int = 3000

        # VIVID Studio 에디터 서버 (FastAPI daemon thread)
        self._editor_thread: threading.Thread | None = None
        self._editor_port: int = 8000

        # VIVID Studio Vite dev 서버 프로세스
        self._vite_proc: subprocess.Popen | None = None
        self._vite_port: int = 4000

        self._build_ui()

    # ── UI 구성 ──────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 고정 헤더: 제목 + 상태창 ──────────────────────────────────
        header = QWidget()
        hdr = QVBoxLayout(header)
        hdr.setContentsMargins(32, 24, 32, 8)
        hdr.setSpacing(8)
        hdr.addWidget(make_title("4. 영상 기획안 및 조립"))
        self._status_box = make_status_box()
        hdr.addWidget(self._status_box)
        self._log = StatusLogger(self._status_box)
        root.addWidget(header)

        # ── 스크롤 영역: STEP A ~ 내비게이션 ─────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
            "QScrollBar:vertical { background: #1E1E1E; width: 8px; border-radius: 4px; }"
            "QScrollBar::handle:vertical { background: #444; border-radius: 4px; }"
        )
        body = QWidget()
        body_lyt = QVBoxLayout(body)
        body_lyt.setContentsMargins(32, 8, 32, 24)
        body_lyt.setSpacing(12)
        scroll.setWidget(body)
        root.addWidget(scroll)

        # 이하 모든 STEP A~D 위젯은 body_lyt 에 추가
        # (가독성을 위해 root → body_lyt 변수명은 동일하게 유지)
        root = body_lyt  # noqa: F841  (섀도잉 의도적)

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

        self._open_input_btn = QPushButton("📂  프로젝트 폴더 열기")
        self._open_input_btn.setToolTip("프로젝트 input/ 폴더를 파일 탐색기로 엽니다.")
        self._open_input_btn.clicked.connect(self._on_open_input_folder)
        row_a.addWidget(self._open_input_btn)

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
        lbl_b = QLabel("[ STEP B ]  Remotion 렌더링 / VIVID Studio")
        lbl_b.setStyleSheet(
            f"color:{C_HIGHLIGHT}; font-size:12px; font-weight:bold;"
        )
        root.addWidget(lbl_b)

        row_b = QHBoxLayout()
        row_b.setSpacing(10)

        self._render_btn = QPushButton("🎬  Remotion 투명 렌더링")
        self._render_btn.setEnabled(False)
        self._render_btn.setToolTip(
            "배경 투명 .webm 파일 생성 (변경된 FX만 재렌더링 — Diff Check)"
        )
        self._render_btn.clicked.connect(self._on_render_click)
        row_b.addWidget(self._render_btn)

        self._studio_btn = QPushButton("▶🖊  미리보기 + VIVID Studio")
        self._studio_btn.setEnabled(False)
        self._studio_btn.setToolTip(
            "Custom FX 매칭 → Remotion Studio(미리보기) + VIVID Studio(편집) 동시 실행"
        )
        self._studio_btn.clicked.connect(self._on_vivid_studio_click)
        row_b.addWidget(self._studio_btn)

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
        # STEP D: AI 기획 지시문 생성 (Google OAuth)
        # ─────────────────────────────────────────────────
        lbl_d = QLabel("[ STEP D ]  AI 기획 지시문 생성")
        lbl_d.setStyleSheet(
            f"color:{C_HIGHLIGHT}; font-size:12px; font-weight:bold;"
        )
        root.addWidget(lbl_d)

        # OAuth 인증 상태 표시 (앱 시작 시점 기준 — 변경 시 재시작 필요)
        _oauth_active = (ROOT_DIR / "client_secret.json").exists()
        oauth_info = QLabel(
            "🔐  Google OAuth 인증 모드  (client_secret.json 감지됨)"
            if _oauth_active else
            "⚠️  client_secret.json 없음 — Google OAuth 파일을 루트에 배치하세요"
        )
        oauth_info.setStyleSheet(
            f"color:{'#4CAF50' if _oauth_active else '#FF5252'}; font-size:10px;"
        )
        oauth_info.setWordWrap(True)
        root.addWidget(oauth_info)

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

        # 프로젝트 변경 시 기존 Studio 프로세스 종료
        if self._studio_proc is not None and self._studio_proc.poll() is None:
            self._studio_proc.terminate()
        self._studio_proc = None
        self._studio_port = 3000

        # 프로젝트 변경 시 Vite 프로세스 종료 (FastAPI는 daemon이라 자동 종료)
        if self._vite_proc is not None and self._vite_proc.poll() is None:
            self._vite_proc.terminate()
        self._vite_proc = None

        self._drop_zone.reset()
        self._log.clear()
        self._render_btn.setEnabled(False)
        self._studio_btn.setEnabled(False)
        self._vrew_btn.setEnabled(False)
        self._open_btn.setEnabled(False)
        self._progress.setVisible(False)

        if path:
            self._log.highlight(f"프로젝트: {path.name}")
            # ── 기존 파일 복원 ──────────────────────────────────
            plan = path / "asset" / "remotion_plan.json"
            if plan.exists():
                try:
                    self._plan = parse_plan_json(plan)
                    self._drop_zone.set_ready("remotion_plan.json")
                    self._render_btn.setEnabled(True)
                    self._studio_btn.setEnabled(True)
                    self._log.success("기획안 파일이 확인되었습니다.")
                    self._log.info("Remotion 실행 또는 렌더링 버튼을 눌러주세요.")
                except Exception:
                    self._log.info(
                        "제미나이(웹)에 storyboard.pdf와 fx_catalog.txt를 참고하여 만든\n"
                        "영상 기획안(remotion_plan.json)을 업로드 하세요."
                    )
            else:
                self._log.info(
                    "제미나이(웹)에 storyboard.pdf와 fx_catalog.txt를 참고하여 만든\n"
                    "영상 기획안(remotion_plan.json)을 업로드 하세요."
                )

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

        # ── Composition 파일 생성 (슬라이드 기반) ──
        remotion_dir  = self._project_dir / "remotion"
        timeline_path = self._project_dir / "asset" / "base_timeline.json"
        try:
            generate_compositions(plan, remotion_dir, timeline_path=timeline_path)
        except Exception as e:
            self._log.error(f"Composition 생성 오류:\n{e}")
            return

        self._plan = plan
        effects    = plan.get("effects", [])

        # ── Custom 항목 분류 ────────────────────────────────────────────────
        # ① type="Custom"                    → 신규 효과 필요 → PreflightDialog
        # ② type=컴포넌트명 & TSX 존재        → 기등록 효과 → 바로 사용
        # ③ type=컴포넌트명 & TSX 미존재      → 신규 효과 필요 → PreflightDialog
        _known_builtin = {"Popup", "Video", "TextPopup"}

        def _is_new_custom(eff: dict) -> bool:
            t = eff.get("type", "")
            if t in _known_builtin:
                return False
            if t == "Custom":
                return True           # 명시적 신규 요청
            # 컴포넌트명으로 지정됐지만 파일이 없는 경우
            return not (SHARED_FX_DIR / f"{t}.tsx").exists()

        truly_new   = [e for e in effects if _is_new_custom(e)]
        named_known = [
            e for e in effects
            if e.get("type") not in _known_builtin
            and e.get("type") != "Custom"
            and (SHARED_FX_DIR / f"{e.get('type','')}.tsx").exists()
        ]

        self._drop_zone.set_ready("remotion_plan.json")
        self._log.success(
            f"기획안 파일이 입력되었습니다.  ·  effects: {len(effects)}개"
        )

        # 기등록 컴포넌트 바로 사용 안내
        if named_known:
            self._log.info(
                f"기등록 FX {len(named_known)}개 감지 — "
                f"({', '.join(e.get('type','') for e in named_known)}) "
                "TSX 파일 확인됨. 즉시 사용 가능합니다."
            )

        # ── 진짜 신규 Custom 항목만 PreflightDialog ────────────────────────
        if truly_new:
            self._log.highlight(
                f"신규 Custom 시각 효과 {len(truly_new)}개가 감지되었습니다.\n"
                "코딩 지시 팝업을 확인하고, Claude Code에서 TSX를 작성한 후 진행하세요."
            )
            dlg = PreflightDialog(truly_new, parent=self)
            if dlg.exec() == PreflightDialog.DialogCode.Accepted:
                self._log.success("Custom FX 코딩 완료. 미리보기 또는 렌더링을 진행하세요.")
                self._render_btn.setEnabled(True)
                self._studio_btn.setEnabled(True)
            else:
                self._log.info("Custom FX 코딩이 취소되었습니다. 준비 후 다시 업로드하세요.")
                self._drop_zone.reset()
                self._plan = None
        else:
            self._log.info("미리보기 또는 렌더링 버튼을 눌러주세요.")
            self._render_btn.setEnabled(True)
            self._studio_btn.setEnabled(True)

    # ── §A: 프로젝트 input 폴더 열기 ────────────────────────────────────────

    def _on_open_input_folder(self):
        """프로젝트 input/ 폴더를 파일 탐색기로 열기"""
        if self._project_dir is None:
            return
        folder = self._project_dir / "input"
        folder.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            subprocess.Popen(["explorer", str(folder)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)])

    # ── §A: FX 카탈로그 갤러리 ────────────────────────────────────────────

    def _on_fx_gallery_click(self):
        """FX 갤러리 팝업 열기 (캐시 있으면 즉시, 없으면 파싱 후 표시)"""
        dlg = FxGalleryDialog(CATALOG_PATH, parent=self)
        dlg.exec()

    # ── §B: VIVID Studio 인터랙티브 에디터 ──────────────────────────────────

    def _on_vivid_studio_click(self):
        """
        Remotion Studio(미리보기) + VIVID Studio(편집) 일괄 실행:
          1. Custom FX 시맨틱 매칭 (필요시)
          2. Remotion Studio 실행
          3. FastAPI 브릿지 서버 시작
          4. Vite dev 서버 시작
        """
        if self._project_dir is None:
            self._log.error("프로젝트 폴더가 없습니다. 1단계로 돌아가세요.")
            return

        # ── 이미 모두 실행 중이면 브라우저 두 개 모두 오픈 ──────────────────
        vite_alive = (
            self._vite_proc is not None and self._vite_proc.poll() is None
        )
        api_alive = (
            self._editor_thread is not None and self._editor_thread.is_alive()
        )
        studio_alive = (
            self._studio_proc is not None and self._studio_proc.poll() is None
        )

        if vite_alive and api_alive and studio_alive:
            vite_url = f"http://127.0.0.1:{self._vite_port}"
            studio_url = f"http://localhost:{self._studio_port}"
            self._log.info("모든 서비스가 이미 실행 중입니다.")
            webbrowser.open(studio_url)
            webbrowser.open(vite_url)
            return

        if self._plan is None:
            self._log.error("기획안(remotion_plan.json)을 먼저 로드하세요.")
            return

        # Custom FX 감지
        custom_effs = detect_custom_fx(self._plan)

        if custom_effs:
            # ① PreflightDialog — Claude에게 코딩 요청
            dlg = PreflightDialog(custom_effs, parent=self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return   # 사용자가 취소

            # ② FX 파일 동기화 (심볼릭 링크 / 복사)
            self._sync_fx_files(self._project_dir / "remotion")

            # ③ fx_catalog.txt 읽기
            if not CATALOG_PATH.exists():
                self._log.error("fx_catalog.txt 파일이 없습니다. FX 카탈로그를 확인하세요.")
                return
            catalog_text = CATALOG_PATH.read_text(encoding="utf-8")

            # ④ SemanticMatchWorker 실행 (Gemini 일괄 매칭)
            self._log.info(
                f"Gemini로 Custom FX {len(custom_effs)}개 시맨틱 매칭 중...\n"
                "(첫 실행 시 브라우저 OAuth 로그인 창이 열립니다)"
            )
            self._match_thread = QThread(self)
            self._match_worker = SemanticMatchWorker(custom_effs, catalog_text)
            self._match_worker.moveToThread(self._match_thread)
            self._match_thread.started.connect(self._match_worker.run)
            self._match_worker.finished.connect(self._on_match_done)
            self._match_worker.error.connect(self._on_match_error)
            self._match_worker.finished.connect(self._match_thread.quit)
            self._match_worker.error.connect(self._match_thread.quit)
            self._match_thread.start()
        else:
            # Custom FX 없으면 즉시 일괄 실행
            self._launch_both()

    def _poll_editor_ready(
        self,
        api_port: int,
        vite_port: int,
        vite_url: str,
        attempts: int,
    ) -> None:
        """FastAPI + Vite 서버가 모두 응답할 때까지 폴링 (최대 60회 = 12초)"""
        import socket
        MAX_ATTEMPTS = 60
        INTERVAL_MS  = 200

        def _port_open(p: int) -> bool:
            try:
                with socket.create_connection(("127.0.0.1", p), timeout=0.2):
                    return True
            except OSError:
                return False

        if _port_open(api_port) and _port_open(vite_port):
            self._log.success(
                f"VIVID Studio 준비 완료 → 브라우저 오픈\n{vite_url}"
            )
            webbrowser.open(vite_url)
            return

        if attempts >= MAX_ATTEMPTS:
            self._log.error(
                "VIVID Studio 서버 시작 시간 초과.\n"
                f"  FastAPI: http://127.0.0.1:{api_port}/api/status\n"
                f"  Vite:    {vite_url}"
            )
            return

        QTimer.singleShot(
            INTERVAL_MS,
            lambda: self._poll_editor_ready(api_port, vite_port, vite_url, attempts + 1),
        )

    # ── §B: 미리보기 ─────────────────────────────────────────────────────

    def _sync_fx_files(self, remotion_dir: Path) -> None:
        """
        심볼릭 링크가 실패(Windows 권한 부족 등)한 경우를 대비해
        SHARED_FX_DIR의 최신 TSX 파일을 프로젝트 fx/ 폴더에 직접 동기화.
        심볼릭 링크가 정상이면 아무것도 하지 않는다.
        """
        fx_dir = remotion_dir / "src" / "components" / "fx"
        if fx_dir.is_symlink() and fx_dir.exists():
            return  # 심볼릭 링크 유효 → 동기화 불필요

        fx_dir.mkdir(parents=True, exist_ok=True)
        updated = 0
        for tsx in SHARED_FX_DIR.glob("*.tsx"):
            dest = fx_dir / tsx.name
            if not dest.exists() or dest.stat().st_mtime < tsx.stat().st_mtime:
                shutil.copy2(str(tsx), str(dest))
                updated += 1
        if updated:
            self._log.info(
                f"FX 파일 {updated}개 동기화 완료 "
                "(심볼릭 링크 미작동 → 직접 복사 모드)"
            )

    def _poll_studio_ready(self, port: int, url: str, attempts: int) -> None:
        """
        Remotion Studio가 포트에서 응답할 때까지 500ms마다 재확인.
        최대 60초(120회) 대기 후 타임아웃.
        """
        import socket as _socket
        try:
            with _socket.create_connection(("localhost", port), timeout=0.3):
                webbrowser.open(url)
                self._log.success(
                    f"Remotion Studio 준비 완료 ({url})  "
                    "— 브라우저에서 미리보기를 확인하세요."
                )
                return
        except OSError:
            pass

        if attempts >= 120:  # 60초 타임아웃
            self._log.error(
                "Remotion Studio가 60초 내에 응답하지 않았습니다. "
                "터미널에서 오류를 확인하거나 브라우저를 수동으로 열어주세요."
            )
            webbrowser.open(url)
            return

        # 5초마다 진행 알림
        if attempts > 0 and attempts % 10 == 0:
            elapsed = attempts // 2
            self._log.info(
                f"Remotion Studio 컴파일/번들링 중… ({elapsed}초 경과)"
            )

        QTimer.singleShot(
            500,
            lambda: self._poll_studio_ready(port, url, attempts + 1),
        )

    def _on_match_done(self, matches: dict):
        """SemanticMatchWorker 완료 — 매칭 결과를 plan에 역주입 후 미리보기 실행"""
        applied = []
        unmatched = []

        for eff in self._plan["effects"]:
            eid = eff.get("id", "")
            if eff.get("type") != "Custom":
                continue
            if eid in matches:
                comp_name = matches[eid]
                # type을 실제 컴포넌트명으로 교체 →
                # _build_slide_tsx()의 named-component 브랜치(SHARED_FX_DIR 존재 확인)가
                # 자동으로 처리하므로 별도 _componentName 의존 불필요
                eff["type"] = comp_name
                eff["_componentName"] = comp_name        # 메타데이터용 보존
                eff["_componentFile"] = f"{comp_name}.tsx"
                applied.append(f"  ✅ [{eid}] → {comp_name}")
            else:
                unmatched.append(f"  ⚠️ [{eid}] 매칭 결과 없음 — 렌더링 시 건너뜀")

        report = "\n".join(applied + unmatched)
        self._log.success(f"시맨틱 매칭 완료:\n{report}")

        self._launch_both()

    def _on_match_error(self, msg: str):
        """SemanticMatchWorker 실패"""
        self._log.error(f"FX 시맨틱 매칭 실패:\n{msg}\n\n매칭 없이 일괄 실행을 계속합니다.")
        # 매칭 실패해도 실행은 계속 (Custom FX는 건너뜀)
        self._launch_both()

    def _launch_preview(self):
        """Composition 재생성 + Remotion Studio 실행"""
        if self._project_dir is None:
            return

        remotion_dir  = self._project_dir / "remotion"
        timeline_path = self._project_dir / "asset" / "base_timeline.json"

        # ── Composition 재생성 ─────────────────────────────────────────
        # 매칭 후 type이 업데이트된 self._plan으로 TSX를 항상 최신 상태로 재생성.
        # (업로드 시점의 generate_compositions 호출은 매칭 전이라 Custom FX 스킵됨)
        try:
            generate_compositions(self._plan, remotion_dir, timeline_path=timeline_path)
        except Exception as e:
            self._log.error(f"Composition 생성 오류:\n{e}")
            return

        # ── 기존 프로세스 살아있으면 재사용 (새 탭 방지) ──────────────
        # Remotion Studio는 파일 변경을 감지해 자동 핫리로드하므로
        # 위에서 TSX를 재생성하면 브라우저도 자동 갱신됨.
        if self._studio_proc is not None and self._studio_proc.poll() is None:
            url = f"http://localhost:{self._studio_port}"
            self._log.info(f"Remotion Studio 이미 실행 중 → 재생성된 Composition 핫리로드 대기 ({url})")
            webbrowser.open(url)
            return

        remotion_dir = self._project_dir / "remotion"

        # ── FX 파일 동기화 (심볼릭 링크 오류 방지) ───────────────────
        self._sync_fx_files(remotion_dir)

        # ── 사용 가능한 포트 탐색 ─────────────────────────────────────
        port = _find_free_port(3000, 3100)

        self._log.info(
            f"Remotion Studio 시작 중 (포트 {port})… "
            "컴파일이 완료되면 브라우저가 자동으로 열립니다."
        )

        try:
            proc = subprocess.Popen(
                [_NPX, "remotion", "studio", "src/index.ts", "--port", str(port)],
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

        self._studio_proc = proc
        self._studio_port = port
        url = f"http://localhost:{port}"

        # ── 고정 딜레이 대신 포트 응답 폴링 후 브라우저 오픈 ──────────
        self._poll_studio_ready(port, url, attempts=0)

    def _launch_both(self):
        """Remotion Studio + VIVID Studio(FastAPI, Vite) 일괄 실행"""
        # 1. Remotion Studio 실행
        self._launch_preview()

        import socket
        vite_url = f"http://127.0.0.1:{self._vite_port}"

        # ── 2. FastAPI 서버 시작 ─────────────────────────────────────────
        api_alive = (
            self._editor_thread is not None and self._editor_thread.is_alive()
        )
        if not api_alive:
            try:
                from utils.editor_server import start_server
            except ImportError as e:
                self._log.error(
                    f"editor_server 임포트 실패:\n{e}\n"
                    "fastapi/uvicorn 설치 여부를 확인하세요."
                )
                return

            api_port = _find_free_port(8000, 8100)
            self._editor_port = api_port

            t = threading.Thread(
                target=start_server,
                args=(self._project_dir, api_port),
                daemon=True,
            )
            t.start()
            self._editor_thread = t
            self._log.info(f"FastAPI 브릿지 서버 시작 중 (port {api_port})…")

        # ── 3. Vite dev 서버 시작 ────────────────────────────────────────
        vite_alive = (
            self._vite_proc is not None and self._vite_proc.poll() is None
        )
        if not vite_alive:
            from utils.step4_workers import ROOT_DIR
            vivid_studio_dir = ROOT_DIR / "vivid_studio"

            if not vivid_studio_dir.exists():
                self._log.error(
                    f"vivid_studio/ 폴더가 없습니다: {vivid_studio_dir}\n"
                    "워크스페이스 루트에 vivid_studio/ 폴더가 있는지 확인하세요."
                )
                return
            if not (vivid_studio_dir / "node_modules").exists():
                self._log.error(
                    "vivid_studio/node_modules 없음. 터미널에서:\n"
                    f"  cd {vivid_studio_dir}\n  npm install"
                )
                return

            # 빈 포트 스캔 (4000~4100)
            vite_port = _find_free_port(4000, 4100)
            self._vite_port = vite_port
            vite_url = f"http://127.0.0.1:{self._vite_port}"

            try:
                self._vite_proc = subprocess.Popen(
                    [_NPM, "run", "dev", "--", "--port", str(vite_port)],
                    cwd=str(vivid_studio_dir),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=(
                        subprocess.CREATE_NEW_PROCESS_GROUP
                        if sys.platform == "win32" else 0
                    ),
                )
                self._log.info(
                    f"Vite dev 서버 시작 중 (port {self._vite_port})…"
                )
            except Exception as e:
                self._log.error(f"Vite 서버 시작 실패:\n{e}")
                return

        # ── 4. 양쪽 준비 완료 후 브라우저 오픈 ──────────────────────────
        self._poll_editor_ready(
            api_port=self._editor_port,
            vite_port=self._vite_port,
            vite_url=vite_url,
            attempts=0,
        )

    # ── §B: 투명 렌더링 ──────────────────────────────────────────────────

    def _on_render_click(self):
        """
        렌더링 버튼 클릭 — Custom FX 검사는 업로드 시점에 이미 완료되었으므로 바로 렌더 시작.
        """
        if self._plan is None or self._project_dir is None:
            return
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

    # ── §E: AI 기획 지시문 (Google OAuth) ───────────────────────────────

    def _on_directive_click(self):
        """기획 지시문 생성 + 클립보드 복사"""
        # OAuth 인증 파일 확인
        if not (ROOT_DIR / "client_secret.json").exists():
            self._log.error(
                "client_secret.json 파일이 없습니다.\n"
                "Google Cloud Console에서 OAuth 클라이언트 ID를 발급받아\n"
                f"아래 경로에 저장하세요:\n  {ROOT_DIR / 'client_secret.json'}"
            )
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

        self._log.info("Google OAuth로 Gemini에 대본 분석 요청 중...\n(첫 실행 시 브라우저 로그인 창이 열립니다)")
        self._directive_btn.setEnabled(False)

        self._gemini_thread = QThread(self)
        self._gemini_worker = GeminiWorker(script_text=script_text)
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
        for t in (self._render_thread, self._vrew_thread, self._gemini_thread, self._match_thread):
            if t and t.isRunning():
                t.quit()
                t.wait(2000)
        super().closeEvent(event)
