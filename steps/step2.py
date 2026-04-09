"""
steps/step2.py
2단계 — 대본 기획
  - script.txt Drag & Drop / 파일 업로드
  - 대본 변환 (script_intro / body / body_slide 3종 생성)
  - NEXT → 3단계
"""

import re
import shutil
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QStackedWidget, QFileDialog,
)

from utils.theme import C_HIGHLIGHT
from utils.widgets import (
    make_title, make_divider, make_status_box,
    StatusLogger, DropZone,
)
from utils.backend import convert_script


class Step2Widget(QWidget):

    def __init__(self, stack: QStackedWidget, parent=None):
        super().__init__(parent)
        self._stack = stack
        self._project_dir: Path | None = None
        self._build_ui()

    # ── UI 구성 ──────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 32, 24)
        root.setSpacing(14)

        root.addWidget(make_title("2. 대본 기획"))

        self._status_box = make_status_box()
        root.addWidget(self._status_box)
        self._log = StatusLogger(self._status_box)

        root.addWidget(make_divider())

        # ── Drag & Drop 영역 ──
        lbl = QLabel("대본 파일 업로드 (.txt)")
        lbl.setStyleSheet(
            f"color:{C_HIGHLIGHT}; font-size:12px; font-weight:bold;"
        )
        root.addWidget(lbl)

        self._drop_zone = DropZone(
            label="script.txt 파일을 여기에 끌어다 놓으세요\n(또는 아래 버튼으로 선택)",
            accepted_ext=".txt",
        )
        self._drop_zone.file_dropped.connect(self._on_file_received)
        root.addWidget(self._drop_zone)

        # ── 액션 버튼 행 ──
        action_row = QHBoxLayout()
        action_row.setSpacing(10)

        self._upload_btn = QPushButton("📁  대본 업로드")
        self._upload_btn.clicked.connect(self._on_upload_click)
        action_row.addWidget(self._upload_btn)

        self._convert_btn = QPushButton("⚙  대본 변환")
        self._convert_btn.setEnabled(False)
        self._convert_btn.clicked.connect(self._on_convert_click)
        action_row.addWidget(self._convert_btn)

        action_row.addStretch()
        root.addLayout(action_row)

        root.addWidget(make_divider())

        # ── 내비게이션 버튼 행 ──
        nav_row = QHBoxLayout()
        nav_row.setSpacing(12)

        back_btn = QPushButton("◀  BACK")
        back_btn.clicked.connect(lambda: self._stack.setCurrentIndex(0))
        nav_row.addWidget(back_btn)

        nav_row.addStretch()

        self._next_btn = QPushButton("NEXT  ▶")
        self._next_btn.setObjectName("NextBtn")
        self._next_btn.setEnabled(False)
        self._next_btn.clicked.connect(self._go_next)
        nav_row.addWidget(self._next_btn)

        root.addLayout(nav_row)
        root.addStretch()

    # ── 외부 주입 ─────────────────────────────────────────────

    def set_project_dir(self, path: Path | None):
        self._project_dir = path
        self._convert_btn.setEnabled(False)
        self._next_btn.setEnabled(False)
        self._drop_zone.reset()
        self._log.clear()
        if path:
            self._log.highlight(f"프로젝트: {path.name}")
            self._log.info("대본 파일(script.txt)을 입력하세요.")

    # ── 슬롯 ─────────────────────────────────────────────────

    def _on_upload_click(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "대본 파일 선택", str(Path.home()), "텍스트 파일 (*.txt)"
        )
        if path:
            self._on_file_received(path)

    def _on_file_received(self, src_path: str):
        src = Path(src_path)

        # ── 하네스: 확장자 ──
        if src.suffix.lower() != ".txt":
            self._log.error(f"'{src.name}'은(는) .txt 파일이 아닙니다.")
            return

        # ── 하네스: 0바이트 ──
        if src.stat().st_size == 0:
            self._log.error(f"'{src.name}' 파일이 비어 있습니다 (0바이트).")
            return

        if self._project_dir is None:
            self._log.error("프로젝트 폴더가 설정되지 않았습니다. 1단계로 돌아가세요.")
            return

        dest_dir = self._project_dir / "input"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / "script.txt"

        try:
            shutil.copy2(str(src), str(dest))
        except Exception as e:
            self._log.error(f"파일 저장 중 오류:\n{e}")
            return

        self._drop_zone.set_ready(src.name)
        self._log.success(f"대본 파일이 저장되었습니다.  →  {dest}")
        self._convert_btn.setEnabled(True)

    def _on_convert_click(self):
        if self._project_dir is None:
            self._log.error("프로젝트 폴더가 없습니다.")
            return

        self._log.info("대본 변환을 시작합니다...")

        try:
            result = convert_script(self._project_dir / "input")
        except (FileNotFoundError, ValueError) as e:
            self._log.error(str(e))
            return
        except Exception as e:
            self._log.error(f"예상치 못한 오류:\n{e}")
            return

        slide_text  = result["slide"].read_text(encoding="utf-8")
        slide_count = len(re.findall(r'^\[슬라이드 \d+\]', slide_text, re.MULTILINE))

        self._log.success(
            f"대본 변환이 완료되었습니다.\n"
            f"  · script_intro.txt\n"
            f"  · script_body.txt\n"
            f"  · script_body_slide.txt  ({slide_count}개 슬라이드)\n"
            "다음 단계로 넘어가세요."
        )
        self._next_btn.setEnabled(True)
        self._convert_btn.setEnabled(False)

    def _go_next(self):
        step3 = self._stack.widget(2)
        step3.set_project_dir(self._project_dir)
        self._stack.setCurrentIndex(2)
