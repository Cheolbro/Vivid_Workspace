import sys
import asyncio
import logging
from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit, QFrame, QCheckBox, QComboBox, QScrollArea,
)
from utils.theme import C_HIGHLIGHT, C_ACCENT, C_TEXT, C_BORDER
from utils.widgets import StatusLogger, make_status_box, make_title
from vivid_radar.vivid_core.config_loader import config

class RadarWorker(QThread):
    """
    Radar 모듈(A1, A2, A3)을 비동기로 실행하고 로그를 GUI로 전달하는 워커.
    """
    log_signal = Signal(str, str)  # (message, level)
    finished_signal = Signal()

    def __init__(self, module_class, *args, **kwargs):
        super().__init__()
        self.module_class = module_class
        self.args = args
        self.kwargs = kwargs

    def run(self):
        from vivid_radar.vivid_core.logger import logger
        
        def qt_log_callback(level, message):
            self.log_signal.emit(message, level.lower())

        logger.add_callback(qt_log_callback)

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            instance = self.module_class(*self.args, **self.kwargs)
            loop.run_until_complete(instance.run())
        except Exception as e:
            self.log_signal.emit(f"Error: {str(e)}", "error")
        finally:
            if qt_log_callback in logger._callbacks:
                logger._callbacks.remove(qt_log_callback)
            self.finished_signal.emit()

class RadarBaseWidget(QWidget):
    """
    Radar 모듈 위젯의 공통 기반 클래스.
    - use_scroll=True 시 내부 콘텐츠를 스크롤 가능하게 만듭니다.
    """
    def __init__(self, title_text, show_profiles=True, use_scroll=False, parent=None):
        super().__init__(parent)
        
        # 최상위 레이아웃
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        
        if use_scroll:
            self.scroll_area = QScrollArea()
            self.scroll_area.setWidgetResizable(True)
            self.scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")
            
            self.container = QWidget()
            self.layout = QVBoxLayout(self.container)
            self.scroll_area.setWidget(self.container)
            self.main_layout.addWidget(self.scroll_area)
        else:
            self.layout = QVBoxLayout()
            self.main_layout.addLayout(self.layout)

        self.layout.setContentsMargins(30, 30, 30, 30)
        self.layout.setSpacing(15)

        # 제목
        self.title = make_title(title_text)
        self.layout.addWidget(self.title)

        # ── 상단 제어바 (프로필, 헤드리스) ──
        ctrl_layout = QHBoxLayout()
        # ... (중략: 기존 ctrl_layout 로직 동일)
        
        if show_profiles:
            ctrl_layout.addWidget(QLabel("구글 프로필:"))
            self.profile_combo = QComboBox()
            self.profile_combo.addItem("익명 모드 (시크릿)", None)
            
            profiles = config.get("profiles", {})
            for name, path in profiles.items():
                self.profile_combo.addItem(name, path)
            
            self.profile_combo.setFixedWidth(200)
            ctrl_layout.addWidget(self.profile_combo)
        else:
            self.profile_combo = None
            ctrl_layout.addWidget(QLabel("※ A3 모드는 항상 익명 모드로 작동합니다."))

        ctrl_layout.addStretch()

        self.headless_check = QCheckBox("Headless (백그라운드 실행)")
        self.headless_check.setChecked(config.get("headless", True))
        ctrl_layout.addWidget(self.headless_check)

        self.layout.addLayout(ctrl_layout)
        self.layout.addWidget(make_divider())

        # 상단 입력부 (자식 클래스에서 구현)
        self.top_layout = QVBoxLayout()
        self.layout.addLayout(self.top_layout)

        # 실행 버튼
        self.run_btn = QPushButton("실행")
        self.run_btn.setObjectName("NextBtn")
        self.run_btn.setFixedWidth(120)
        self.layout.addWidget(self.run_btn, alignment=Qt.AlignmentFlag.AlignRight)

        # 상태창
        self.status_box = make_status_box()
        self.status_box.setFixedHeight(300)
        self.layout.addWidget(self.status_box)
        
        self.logger = StatusLogger(self.status_box)
        self.worker = None

        self.run_btn.clicked.connect(self.start_task)

    def get_common_params(self):
        """헤드리스 여부와 프로필 경로를 반환"""
        headless = self.headless_check.isChecked()
        profile_path = None
        if self.profile_combo:
            profile_path = self.profile_combo.currentData()
        return headless, profile_path

    def start_task(self):
        pass

    def on_log(self, msg, level):
        if level == "info": self.logger.info(msg)
        elif level == "success": self.logger.success(msg)
        elif level in ["error", "critical"]: self.logger.error(msg)
        elif level == "warning": self.logger.highlight(f"⚠️ {msg}")
        else: self.logger.info(msg)

    def on_finished(self):
        self.run_btn.setEnabled(True)
        self.run_btn.setText("실행")
        self.logger.highlight("작업이 완료되었습니다.")

def make_divider():
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet(f"background-color: {C_BORDER}; max-height: 1px;")
    return line
