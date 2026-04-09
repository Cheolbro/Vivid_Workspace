"""
utils/widgets.py
공통 재사용 UI 컴포넌트
  - StatusLogger  : 색상 지원 상태창 출력 헬퍼
  - DropZone      : Drag & Drop 파일 입력 위젯
  - make_title()  : 단계 제목 레이블 팩토리
  - make_divider(): 수평 구분선 팩토리
  - make_status_box(): 상태창 QTextEdit 팩토리
"""

from pathlib import Path

from PySide6.QtWidgets import (
    QLabel, QFrame, QTextEdit, QWidget, QVBoxLayout, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent

from utils.theme import (
    C_BG_SUB, C_TEXT, C_SUCCESS, C_ERROR, C_HIGHLIGHT, C_BORDER,
)

# ──────────────────────────────────────────────
# 팩토리 함수
# ──────────────────────────────────────────────

def make_title(text: str) -> QLabel:
    """골드 하이라이트 단계 제목 레이블"""
    lbl = QLabel(text)
    lbl.setObjectName("StepTitle")
    return lbl


def make_divider() -> QFrame:
    """1px 수평 구분선"""
    line = QFrame()
    line.setObjectName("Divider")
    line.setFrameShape(QFrame.Shape.HLine)
    return line


def make_status_box() -> QTextEdit:
    """읽기 전용 상태창 (고정 높이 130px)"""
    box = QTextEdit()
    box.setObjectName("StatusBox")
    box.setReadOnly(True)
    box.setFixedHeight(130)
    return box


# ──────────────────────────────────────────────
# StatusLogger
# ──────────────────────────────────────────────

class StatusLogger:
    """
    QTextEdit 상태창에 색상 HTML을 append하는 헬퍼.
    info / success / error / highlight 4가지 레벨 지원.
    """

    def __init__(self, box: QTextEdit):
        self._box = box

    def _append(self, html: str):
        self._box.append(html)
        self._box.verticalScrollBar().setValue(
            self._box.verticalScrollBar().maximum()
        )

    def info(self, msg: str):
        self._append(f'<span style="color:{C_TEXT};">{msg}</span>')

    def success(self, msg: str):
        self._append(f'<span style="color:{C_SUCCESS};"><b>&#10004; {msg}</b></span>')

    def error(self, msg: str):
        self._append(f'<span style="color:{C_ERROR};"><b>&#10006; {msg}</b></span>')

    def highlight(self, msg: str):
        self._append(f'<span style="color:{C_HIGHLIGHT};"><b>{msg}</b></span>')

    def clear(self):
        self._box.clear()


# ──────────────────────────────────────────────
# DropZone
# ──────────────────────────────────────────────

class DropZone(QWidget):
    """
    파일 Drag & Drop 수신 위젯.

    Parameters
    ----------
    label        : 기본 안내 텍스트
    accepted_ext : 허용 확장자. 문자열 하나 or 튜플.
                   예) ".txt"  or  (".srt", ".mp3", ".vrew")
    multi        : True이면 드롭된 파일을 모두 emit (복수 파일 수신)
    """

    file_dropped = Signal(str)    # 파일 경로 1개씩 emit

    # ── 스타일 상수 ──
    _STYLE_NORMAL = (
        f"background-color:#181818;"
        f"border:2px dashed {C_BORDER};"
        f"border-radius:8px;"
    )
    _STYLE_HOVER = (
        f"background-color:#1A2E1A;"
        f"border:2px dashed {C_SUCCESS};"
        f"border-radius:8px;"
    )
    _STYLE_READY = (
        f"background-color:#1A241A;"
        f"border:2px solid {C_SUCCESS};"
        f"border-radius:8px;"
    )
    _STYLE_ERROR = (
        f"background-color:#2A1010;"
        f"border:2px dashed {C_ERROR};"
        f"border-radius:8px;"
    )

    def __init__(
        self,
        label: str = "파일을 여기에 끌어다 놓으세요",
        accepted_ext: "str | tuple" = ".txt",
        multi: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(90)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._accepted_ext: tuple = (
            accepted_ext if isinstance(accepted_ext, tuple) else (accepted_ext,)
        )
        self._default_label = label
        self._multi = multi

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(4)

        self._icon_lbl = QLabel("📂")
        self._icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_lbl.setStyleSheet(
            "font-size:26px; background:transparent; border:none;"
        )
        layout.addWidget(self._icon_lbl)

        self._text_lbl = QLabel(label)
        self._text_lbl.setObjectName("DropZoneLabel")
        self._text_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._text_lbl.setWordWrap(True)
        layout.addWidget(self._text_lbl)

        self._set_style(self._STYLE_NORMAL)

    # ── 스타일 헬퍼 ──────────────────────────

    def _set_style(self, css: str):
        self.setStyleSheet(f"QWidget#DropZone{{{css}}}")

    def set_ready(self, text: str):
        """수신 완료 상태 (초록 실선)"""
        self._icon_lbl.setText("✅")
        self._text_lbl.setText(text)
        self._text_lbl.setStyleSheet(
            f"color:{C_SUCCESS}; font-size:12px; font-weight:bold;"
            f"background:transparent; border:none;"
        )
        self._set_style(self._STYLE_READY)

    def set_error(self, text: str):
        """오류 상태 (빨간 점선)"""
        self._icon_lbl.setText("❌")
        self._text_lbl.setText(text)
        self._text_lbl.setStyleSheet(
            f"color:{C_ERROR}; font-size:12px; font-weight:bold;"
            f"background:transparent; border:none;"
        )
        self._set_style(self._STYLE_ERROR)

    def reset(self):
        """초기 상태로 복원"""
        self._icon_lbl.setText("📂")
        self._text_lbl.setText(self._default_label)
        self._text_lbl.setStyleSheet(
            f"color:#555555; font-size:13px;"
            f"background:transparent; border:none;"
        )
        self._set_style(self._STYLE_NORMAL)

    # ── 유효성 검사 ──────────────────────────

    def _is_valid(self, path: str) -> bool:
        return Path(path).suffix.lower() in self._accepted_ext

    def _valid_paths(self, mime) -> list[str]:
        if not mime.hasUrls():
            return []
        return [
            u.toLocalFile()
            for u in mime.urls()
            if self._is_valid(u.toLocalFile())
        ]

    # ── Drag & Drop 이벤트 ───────────────────

    def dragEnterEvent(self, event: QDragEnterEvent):
        if self._valid_paths(event.mimeData()):
            event.acceptProposedAction()
            self._set_style(self._STYLE_HOVER)
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._set_style(self._STYLE_NORMAL)

    def dropEvent(self, event: QDropEvent):
        self._set_style(self._STYLE_NORMAL)
        paths = self._valid_paths(event.mimeData())
        if not paths:
            event.ignore()
            return
        targets = paths if self._multi else [paths[0]]
        for p in targets:
            self.file_dropped.emit(p)
        event.acceptProposedAction()
