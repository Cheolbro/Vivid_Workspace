"""
steps/step1.py
1단계 — 프로그램 생성
  - 프로젝트 폴더명 입력 → Project_templete 복제
  - 기존 프로젝트 열기 → 진행 단계 자동 감지 후 해당 단계로 이동
  - NEXT 버튼 → 2단계 이동
"""

import os
import re
import shutil
from datetime import date
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QStackedWidget,
    QFileDialog, QFrame,
)

from utils.theme import ROOT_DIR, TEMPLATE_DIR, SHARED_FX_DIR, C_HIGHLIGHT, C_TEXT, C_BG_INPUT, C_BORDER
from utils.widgets import make_title, make_divider, make_status_box, StatusLogger


# ── 진행 단계 감지 ──────────────────────────────────────────────────────

def detect_stage(project_dir: Path) -> int:
    """
    프로젝트 폴더 내 파일 존재 여부로 마지막 완료 단계를 감지.
    반환값: 이동해야 할 스택 인덱스 (0=1단계, 1=2단계, 2=3단계, 3=4단계)

    감지 기준:
      4단계: asset/remotion_plan.json 존재
      3단계: asset/base_timeline.json 존재
      2단계: input/script_body_slide.txt 존재
      1단계: 그 외 (방금 생성된 프로젝트)
    """
    if (project_dir / "asset" / "remotion_plan.json").exists() or \
       (project_dir / "asset" / "hyperframes_compositions.json").exists():
        return 3   # 4단계로 이동
    if (project_dir / "asset" / "base_timeline.json").exists():
        return 2   # 3단계로 이동 (타임라인까지 완료 → 3단계 화면)
    if (project_dir / "asset" / "script_body_slide.txt").exists():
        return 1   # 2단계로 이동 (대본 변환 완료 → 2단계 화면)
    return 0       # 1단계 유지 (NEXT 활성화만)


def is_valid_project(folder: Path) -> bool:
    """Vivid 프로젝트 폴더인지 확인 (remotion 또는 hyperframes package.json 존재)"""
    has_remotion    = (folder / "remotion"    / "package.json").exists()
    has_hyperframes = (folder / "hyperframes" / "package.json").exists()
    return has_remotion or has_hyperframes


class Step1Widget(QWidget):

    def __init__(self, stack: QStackedWidget, parent=None):
        super().__init__(parent)
        self._stack = stack
        self._project_dir: Path | None = None
        self._build_ui()

    # ── UI 구성 ──────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 32, 24)
        root.setSpacing(16)

        root.addWidget(make_title("1. 프로그램 생성"))

        self._status_box = make_status_box()
        root.addWidget(self._status_box)
        self._log = StatusLogger(self._status_box)

        root.addWidget(make_divider())

        # ── 신규 프로젝트 섹션 ─────────────────────────────
        new_lbl = QLabel("새 프로젝트 생성")
        new_lbl.setStyleSheet(
            f"color:{C_HIGHLIGHT}; font-size:12px; font-weight:bold;"
        )
        root.addWidget(new_lbl)

        self._folder_input = QLineEdit()
        self._folder_input.setPlaceholderText("예: EcoNomics_EP01  (영문·숫자·하이픈·언더스코어)")
        self._folder_input.returnPressed.connect(self._on_create)
        root.addWidget(self._folder_input)

        create_row = QHBoxLayout()
        create_row.setSpacing(12)
        self._create_btn = QPushButton("📁  폴더 생성")
        self._create_btn.clicked.connect(self._on_create)
        create_row.addWidget(self._create_btn)
        create_row.addStretch()
        root.addLayout(create_row)

        # ── 구분선 ────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color:{C_BORDER};")
        root.addWidget(sep)

        # ── 기존 프로젝트 섹션 ─────────────────────────────
        open_lbl = QLabel("기존 프로젝트 열기")
        open_lbl.setStyleSheet(
            f"color:{C_HIGHLIGHT}; font-size:12px; font-weight:bold;"
        )
        root.addWidget(open_lbl)

        open_row = QHBoxLayout()
        open_row.setSpacing(12)

        self._open_btn = QPushButton("🔓  프로젝트 폴더 선택")
        self._open_btn.clicked.connect(self._on_open)
        open_row.addWidget(self._open_btn)
        open_row.addStretch()
        root.addLayout(open_row)

        # ── 하단 NEXT 버튼 ────────────────────────────────
        root.addStretch()

        next_row = QHBoxLayout()
        next_row.addStretch()
        self._next_btn = QPushButton("NEXT  ▶")
        self._next_btn.setObjectName("NextBtn")
        self._next_btn.setEnabled(False)
        self._next_btn.clicked.connect(self._go_next)
        next_row.addWidget(self._next_btn)
        root.addLayout(next_row)

        self._log.highlight("새 프로젝트를 생성하거나, 기존 프로젝트 폴더를 선택하세요.")

    # ── 슬롯: 신규 생성 ──────────────────────────────────────

    def _on_create(self):
        raw = self._folder_input.text().strip()

        if not raw:
            self._log.error("폴더명이 비어 있습니다. 영문으로 입력하세요.")
            return

        if not re.fullmatch(r"[A-Za-z0-9_\-]+", raw):
            self._log.error(
                f"허용되지 않는 문자가 포함됩니다: '{raw}'\n"
                "영문자 · 숫자 · 하이픈(-) · 언더스코어(_)만 사용 가능합니다."
            )
            return

        # 날짜_프로젝트명 형식으로 자동 조합
        today  = date.today().strftime("%Y%m%d")
        folder = f"{today}_{raw}"
        target = ROOT_DIR / folder
        if target.exists():
            self._log.error(f"'{folder}' 폴더가 이미 존재합니다. 다른 이름을 사용하거나 '기존 프로젝트 열기'를 사용하세요.")
            return

        if not TEMPLATE_DIR.exists():
            self._log.error(
                f"템플릿 폴더를 찾을 수 없습니다: {TEMPLATE_DIR}\n"
                "'Project_templete' 폴더가 Vivid_Workspace 안에 있는지 확인하세요."
            )
            return

        try:
            shutil.copytree(str(TEMPLATE_DIR), str(target))
        except Exception as e:
            self._log.error(f"폴더 생성 중 오류:\n{e}")
            return

        # 글로벌 FX 심볼릭 링크 구축 (Remotion 프로젝트에만 적용)
        if (target / "remotion" / "package.json").exists():
            self._setup_fx_symlink(target)

        self._project_dir = target
        self._log.success(
            f"프로젝트 폴더가 생성되었습니다.\n"
            f"폴더명: {folder}\n"
            f"경로: {target}\n"
            "NEXT 버튼을 눌러 다음 단계로 넘어가세요."
        )
        self._next_btn.setEnabled(True)
        self._folder_input.setEnabled(False)
        self._create_btn.setEnabled(False)

    # ── 슬롯: 기존 프로젝트 열기 ─────────────────────────────

    def _on_open(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "기존 프로젝트 폴더 선택",
            str(ROOT_DIR),
        )
        if not folder:
            return

        project_dir = Path(folder)

        if not is_valid_project(project_dir):
            self._log.error(
                f"'{project_dir.name}' 은 유효한 Vivid 프로젝트 폴더가 아닙니다.\n"
                "remotion/package.json 또는 hyperframes/package.json 파일이 있는 폴더를 선택하세요."
            )
            return

        self._project_dir = project_dir

        # 진행 단계 감지
        stage_idx = detect_stage(project_dir)
        stage_names = {0: "1단계 (프로그램 생성)", 1: "2단계 (대본 기획)",
                       2: "3단계 (소스 제작)",     3: "4단계 (기획안 조립)"}
        stage_label = stage_names[stage_idx]

        self._log.success(
            f"프로젝트를 불러왔습니다: {project_dir.name}\n"
            f"마지막 진행 단계: {stage_label}\n"
            f"해당 단계로 이동합니다..."
        )

        if stage_idx == 0:
            # 1단계: NEXT 버튼만 활성화
            self._next_btn.setEnabled(True)
        else:
            # 2단계 이상: 모든 이전 단계에 project_dir 주입 후 바로 이동
            self._jump_to_stage(stage_idx)

    def _jump_to_stage(self, target_idx: int):
        """project_dir을 모든 중간 단계에 주입하고 target_idx 화면으로 이동."""
        for i in range(1, target_idx + 1):
            widget = self._stack.widget(i)
            if hasattr(widget, "set_project_dir"):
                widget.set_project_dir(self._project_dir)
        self._stack.setCurrentIndex(target_idx)

    # ── 슬롯: NEXT (신규 생성 후 2단계 이동) ────────────────

    def _go_next(self):
        step2 = self._stack.widget(1)
        step2.set_project_dir(self._project_dir)
        self._stack.setCurrentIndex(1)

    # ── 글로벌 FX 심볼릭 링크 ────────────────────────────────

    def _setup_fx_symlink(self, project_dir: Path):
        """
        프로젝트 내 remotion/src/components/fx/ 폴더를 삭제하고
        글로벌 shared_assets/shared_fx/ 를 가리키는 심볼릭 링크로 대체.

        Windows 주의사항:
          - 심볼릭 링크 생성은 관리자 권한 또는 개발자 모드 활성화가 필요.
          - 권한 오류(OSError) 발생 시 기존 복사본을 유지하고 안내 메시지 출력.
        """
        fx_dir      = project_dir / "remotion" / "src" / "components" / "fx"
        link_target = SHARED_FX_DIR

        link_target.mkdir(parents=True, exist_ok=True)

        if fx_dir.exists() or fx_dir.is_symlink():
            try:
                if fx_dir.is_symlink():
                    fx_dir.unlink()
                else:
                    shutil.rmtree(str(fx_dir))
            except Exception as e:
                self._log.error(f"[FX 링크] 기존 fx/ 폴더 삭제 실패:\n{e}")
                return

        try:
            os.symlink(str(link_target), str(fx_dir), target_is_directory=True)
            self._log.info(
                f"[FX 링크] 글로벌 FX 라이브러리 연결 완료\n"
                f"  {fx_dir}\n  → {link_target}"
            )
        except OSError as e:
            self._log.warning(
                f"[FX 링크] 심볼릭 링크 생성 실패 (권한 부족).\n"
                f"  오류: {e}\n"
                "  해결 방법: Windows '개발자 모드'를 활성화하거나\n"
                "  PowerShell을 관리자 권한으로 실행하세요.\n"
                "  이번 프로젝트는 복사본 방식으로 진행됩니다."
            )
            try:
                if any(link_target.iterdir()):
                    shutil.copytree(str(link_target), str(fx_dir))
                else:
                    fx_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                fx_dir.mkdir(parents=True, exist_ok=True)

    # ── 공개 접근자 ──────────────────────────────────────────

    def get_project_dir(self) -> Path | None:
        return self._project_dir
