from PySide6.QtWidgets import QLabel, QLineEdit, QVBoxLayout
from utils.radar_common import RadarBaseWidget, RadarWorker
from vivid_radar.a1_channel import ChannelScout

class A1Widget(RadarBaseWidget):
    def __init__(self, parent=None):
        super().__init__("📡 HotChannel (A1)", show_profiles=True, parent=parent)
        
        # 입력 가이드
        self.top_layout.addWidget(QLabel("발굴할 타겟 채널의 키워드를 입력하세요:"))
        
        # 키워드 입력
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("예: 이란전쟁, 주식 전망, 경제 위기...")
        self.top_layout.addWidget(self.input_edit)

    def start_task(self):
        keyword = self.input_edit.text().strip()
        if not keyword:
            self.logger.error("키워드를 입력해 주세요.")
            return

        headless, profile_path = self.get_common_params()

        self.run_btn.setEnabled(False)
        self.run_btn.setText("실행 중...")
        self.logger.clear()
        self.logger.info(f"'{keyword}' 키워드로 채널 분석을 시작합니다... (Headless: {headless})")

        # 워커 실행
        self.worker = RadarWorker(ChannelScout, keyword, user_data_dir=profile_path, headless=headless)
        self.worker.log_signal.connect(self.on_log)
        self.worker.finished_signal.connect(self.on_finished)
        self.worker.start()
