"""
main.py — Vivid 유튜브 영상편집 자동화 GUI 대통합
- 사이드바 네비게이션 추가 (HotChannel, HotTopic, FindTitle, Studio)
- VIVID Radar 모듈 통합
- 기존 Studio 기능 보존 (Wrapping 방식)
"""

import sys
import os
from pathlib import Path

# VIVID Radar 모듈 경로 등록 (vivid_core 임포트 에러 해결)
RADAR_PATH = str(Path(__file__).parent / "vivid_radar")
if RADAR_PATH not in sys.path:
    sys.path.append(RADAR_PATH)

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QLabel, QStackedWidget,
    QPushButton, QFrame
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPalette

from utils.theme import (
    C_BG_MAIN, C_BG_SUB, C_TEXT, C_HIGHLIGHT, C_SUCCESS, C_BORDER, 
    C_ACCENT, GLOBAL_QSS
)
from utils.health_check import HealthCheckDialog
from steps.step1 import Step1Widget
from steps.step2 import Step2Widget
from steps.step3 import Step3Widget
from steps.step4 import Step4Widget

from utils.radar_a1_widget import A1Widget
from utils.radar_a2_widget import A2Widget
from utils.radar_a3_widget import A3Widget


# ──────────────────────────────────────────────
# Studio 통합 위젯 (기존 1~4단계 래핑)
# ──────────────────────────────────────────────

class StepIndicator(QWidget):
    """상단 진행 단계 표시 바 (1→2→3→4)"""
    LABELS = ["프로그램 생성", "대본 기획", "소스 제작", "기획안 조립"]

    def __init__(self, total: int = 4, parent=None):
        super().__init__(parent)
        self._total = total
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


class StudioWidget(QWidget):
    """기존 VIVID 시스템(1~4단계)을 통째로 담는 위젯"""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 단계 인디케이터
        self.indicator = StepIndicator(total=4)
        layout.addWidget(self.indicator)

        # 스택 위젯
        self.stack = QStackedWidget()
        self.step1 = Step1Widget(self.stack)
        self.step2 = Step2Widget(self.stack)
        self.step3 = Step3Widget(self.stack)
        self.step4 = Step4Widget(self.stack)

        self.stack.addWidget(self.step1)   # index 0
        self.stack.addWidget(self.step2)   # index 1
        self.stack.addWidget(self.step3)   # index 2
        self.stack.addWidget(self.step4)   # index 3

        self.stack.currentChanged.connect(self.indicator.set_current)
        layout.addWidget(self.stack)

    def reset_to_first_step(self):
        """항상 1단계부터 시작하도록 리셋"""
        self.stack.setCurrentIndex(0)


# ──────────────────────────────────────────────
# 사이드바 네비게이션
# ──────────────────────────────────────────────

class SidebarButton(QPushButton):
    def __init__(self, text, icon_text, parent=None):
        super().__init__(f"{icon_text}  {text}", parent)
        self.setCheckable(True)
        self.setFixedHeight(50)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: #BBBBBB;
                border: none;
                border-left: 4px solid transparent;
                text-align: left;
                padding-left: 20px;
                font-size: 14px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: #222222;
                color: {C_HIGHLIGHT};
            }}
            QPushButton:checked {{
                background-color: #2A2A2A;
                color: {C_HIGHLIGHT};
                border-left: 4px solid {C_HIGHLIGHT};
                font-weight: bold;
            }}
        """)

class Sidebar(QWidget):
    menu_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(200)
        self.setStyleSheet(f"background-color: #121212; border-right: 1px solid {C_BORDER};")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 20, 0, 20)
        layout.setSpacing(5)

        # 로고 영역
        logo_lbl = QLabel("VIVID")
        logo_lbl.setStyleSheet(f"color: {C_HIGHLIGHT}; font-size: 24px; font-weight: 900; margin: 10px 20px 30px 20px; letter-spacing: 2px;")
        layout.addWidget(logo_lbl)

        # 메뉴 버튼들
        self.btn_a1 = SidebarButton("HotChannel", "📡")
        self.btn_a2 = SidebarButton("HotTopic", "🔥")
        self.btn_a3 = SidebarButton("FindTitle", "💡")
        self.btn_studio = SidebarButton("Studio", "🎬")

        self.buttons = [self.btn_a1, self.btn_a2, self.btn_a3, self.btn_studio]
        for btn in self.buttons:
            layout.addWidget(btn)
            btn.clicked.connect(self._on_btn_clicked)

        layout.addStretch()

        # 버전 표시
        version_lbl = QLabel("v0.8.0-radar")
        version_lbl.setStyleSheet("color: #444444; font-size: 10px; margin-left: 20px;")
        layout.addWidget(version_lbl)

        # 기본 선택
        self.btn_studio.setChecked(True)

    def _on_btn_clicked(self):
        clicked_btn = self.sender()
        for i, btn in enumerate(self.buttons):
            if btn == clicked_btn:
                btn.setChecked(True)
                self.menu_changed.emit(i)
            else:
                btn.setChecked(False)


# ──────────────────────────────────────────────
# 메인 윈도우
# ──────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Vivid — 유튜브 영상편집 자동화")
        self.setMinimumSize(1100, 750)
        self.resize(1200, 800)
        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── 사이드바 ──
        self.sidebar = Sidebar()
        main_layout.addWidget(self.sidebar)

        # ── 메인 콘텐츠 영역 (스택) ──
        self.main_stack = QStackedWidget()
        main_layout.addWidget(self.main_stack)

        # 각 모듈 위젯 생성
        self.widget_a1 = A1Widget()
        self.widget_a2 = A2Widget()
        self.widget_a3 = A3Widget()
        self.widget_studio = StudioWidget()

        self.main_stack.addWidget(self.widget_a1)     # index 0
        self.main_stack.addWidget(self.widget_a2)     # index 1
        self.main_stack.addWidget(self.widget_a3)     # index 2
        self.main_stack.addWidget(self.widget_studio) # index 3

        # 사이드바 클릭 시 스택 전환
        self.sidebar.menu_changed.connect(self._on_menu_changed)

        # 초기 화면: Studio
        self.main_stack.setCurrentIndex(3)

    def _on_menu_changed(self, index):
        if index == 3: # Studio 진입 시
            self.widget_studio.reset_to_first_step()
        self.main_stack.setCurrentIndex(index)


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
    from PySide6.QtCore import QTimer
    def _show_health_check():
        dlg = HealthCheckDialog(parent=win)
        dlg.exec()

    QTimer.singleShot(300, _show_health_check)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
