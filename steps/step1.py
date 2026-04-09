"""
steps/step1.py
1단계 — 프로그램 생성
  - 프로젝트 폴더명 입력 → Project_templete 복제
  - NEXT 버튼 → 2단계 이동
"""

import re
import shutil
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QStackedWidget,
)

from utils.theme import ROOT_DIR, TEMPLATE_DIR, C_HIGHLIGHT
from utils.widgets import make_title, make_divider, make_status_box, StatusLogger


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

        lbl = QLabel("프로젝트 폴더명 (영문만 입력)")
        lbl.setStyleSheet(
            f"color:{C_HIGHLIGHT}; font-size:12px; font-weight:bold;"
        )
        root.addWidget(lbl)

        self._folder_input = QLineEdit()
        self._folder_input.setPlaceholderText("예: EcoNomics_EP01")
        self._folder_input.returnPressed.connect(self._on_create)
        root.addWidget(self._folder_input)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self._create_btn = QPushButton("폴더 생성")
        self._create_btn.clicked.connect(self._on_create)
        btn_row.addWidget(self._create_btn)

        btn_row.addStretch()

        self._next_btn = QPushButton("NEXT  ▶")
        self._next_btn.setObjectName("NextBtn")
        self._next_btn.setEnabled(False)
        self._next_btn.clicked.connect(self._go_next)
        btn_row.addWidget(self._next_btn)

        root.addLayout(btn_row)
        root.addStretch()

        self._log.highlight("프로젝트 폴더명(영문)을 입력하세요.")

    # ── 슬롯 ─────────────────────────────────────────────────

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

        target = ROOT_DIR / raw
        if target.exists():
            self._log.error(f"'{raw}' 폴더가 이미 존재합니다. 다른 이름을 사용하세요.")
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

        self._project_dir = target
        self._log.success(
            f"프로젝트 폴더가 생성되었습니다.\n"
            f"경로: {target}\n"
            "다음 단계로 넘어가세요."
        )
        self._next_btn.setEnabled(True)
        self._folder_input.setEnabled(False)
        self._create_btn.setEnabled(False)

    def _go_next(self):
        step2 = self._stack.widget(1)
        step2.set_project_dir(self._project_dir)
        self._stack.setCurrentIndex(1)

    # ── 공개 접근자 ──────────────────────────────────────────

    def get_project_dir(self) -> Path | None:
        return self._project_dir
