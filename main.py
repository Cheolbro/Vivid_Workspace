"""
main.py — Vivid 유튜브 영상편집 자동화 GUI
엔트리 포인트: MainWindow + StepIndicator 조립 및 앱 실행.

구조:
  utils/theme.py      — 색상 상수 & 전역 QSS
  utils/widgets.py    — 공통 UI 컴포넌트 (StatusLogger, DropZone, …)
  utils/backend.py    — 파이썬 백엔드 로직 §1-§4 (파싱, PDF, SRT 등)
  utils/backend_ext.py— 파이썬 백엔드 §5-§7 (FX생성, Diff렌더, Vrew조립)
  steps/step1.py      — 1단계: 프로그램 생성
  steps/step2.py      — 2단계: 대본 기획
  steps/step3.py      — 3단계: 소스 제작 (Watchdog, PDF, 타임라인)
  steps/step4.py      — 4단계: 영상 기획안 & Remotion 렌더링 & Vrew 조립
"""

import sys

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QLabel, QStackedWidget,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette

from utils.theme import C_BG_MAIN, C_TEXT, C_HIGHLIGHT, C_SUCCESS, C_BORDER, GLOBAL_QSS
from utils.health_check import HealthCheckDialog
from steps.step1 import Step1Widget
from steps.step2 import Step2Widget
from steps.step3 import Step3Widget
from steps.step4 import Step4Widget as _Step4Real


# ──────────────────────────────────────────────
# 단계 인디케이터
# ──────────────────────────────────────────────

class StepIndicator(QWidget):
    """상단 진행 단계 표시 바 (1→2→3→4)"""

    LABELS = ["프로그램 생성", "대본 기획", "소스 제작", "기획안 조립"]

    def __init__(self, total: int = 4, parent=None):
        super().__init__(parent)
        self._total   = total
        self._current = 0
        self.setFixedHeight(44)
        self._labels: list[QLabel] = []
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 0, 24, 0)
        layout.setSpacing(0)

        for i in range(self._total):
            lbl = QLabel(f"  {i + 1}. {self.LABELS[i]}  ")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setFixedHeight(40)
            self._labels.append(lbl)
            layout.addWidget(lbl)

            if i < self._total - 1:
                arrow = QLabel("›")
                arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
                arrow.setStyleSheet("color:#444444; font-size:18px;")
                arrow.setFixedWidth(20)
                layout.addWidget(arrow)

        self._refresh()

    def set_current(self, idx: int):
        self._current = idx
        self._refresh()

    def _refresh(self):
        for i, lbl in enumerate(self._labels):
            if i == self._current:
                lbl.setStyleSheet(
                    f"color:{C_BG_MAIN}; background:{C_HIGHLIGHT};"
                    f"font-weight:bold; border-radius:4px; font-size:12px;"
                )
            elif i < self._current:
                lbl.setStyleSheet(
                    f"color:{C_SUCCESS}; font-weight:bold; font-size:12px;"
                )
            else:
                lbl.setStyleSheet("color:#555555; font-size:12px;")


# 4단계는 steps/step4.py 의 완전 구현체를 사용
Step4Widget = _Step4Real


# ──────────────────────────────────────────────
# 메인 윈도우
# ──────────────────────────────────────────────

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Vivid — 유튜브 영상편집 자동화")
        self.setMinimumSize(860, 600)
        self.resize(960, 660)
        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 헤더 바 ──
        header = QWidget()
        header.setFixedHeight(48)
        header.setStyleSheet(
            f"background-color:#0A0A0A; border-bottom:1px solid {C_BORDER};"
        )
        h_row = QHBoxLayout(header)
        h_row.setContentsMargins(24, 0, 24, 0)

        logo = QLabel("VIVID")
        logo.setStyleSheet(
            f"color:{C_HIGHLIGHT}; font-size:18px;"
            f"font-weight:900; letter-spacing:4px;"
        )
        h_row.addWidget(logo)
        h_row.addStretch()

        subtitle = QLabel("YouTube Production Automation")
        subtitle.setStyleSheet("color:#555555; font-size:11px;")
        h_row.addWidget(subtitle)

        root.addWidget(header)

        # ── 단계 인디케이터 ──
        self._indicator = StepIndicator(total=4)
        root.addWidget(self._indicator)

        # ── 스택 위젯 ──
        self._stack = QStackedWidget()
        self._step1 = Step1Widget(self._stack)
        self._step2 = Step2Widget(self._stack)
        self._step3 = Step3Widget(self._stack)
        self._step4 = Step4Widget(self._stack)

        self._stack.addWidget(self._step1)   # index 0
        self._stack.addWidget(self._step2)   # index 1
        self._stack.addWidget(self._step3)   # index 2
        self._stack.addWidget(self._step4)   # index 3

        self._stack.currentChanged.connect(self._indicator.set_current)
        root.addWidget(self._stack)


# ──────────────────────────────────────────────
# 진입점
# ──────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(GLOBAL_QSS)

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window,     QColor(C_BG_MAIN))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(C_TEXT))
    app.setPalette(palette)

    win = MainWindow()
    win.show()

    # ── 환경 자동 진단 (앱 시작 직후 1회 실행) ──
    # QTimer를 이용해 메인 윈도우가 완전히 렌더링된 후 다이얼로그 표시
    from PySide6.QtCore import QTimer
    def _show_health_check():
        dlg = HealthCheckDialog(parent=win)
        dlg.exec()   # 모달 — 사용자가 '확인 후 시작' 클릭 시 종료

    QTimer.singleShot(300, _show_health_check)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
