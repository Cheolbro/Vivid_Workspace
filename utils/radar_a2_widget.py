from PySide6.QtWidgets import QLabel, QRadioButton, QVBoxLayout, QButtonGroup, QHBoxLayout
from utils.radar_common import RadarBaseWidget, RadarWorker
from vivid_radar.a2_topic import TopicDiscovery

class A2Widget(RadarBaseWidget):
    def __init__(self, parent=None):
        super().__init__("🔥 HotTopic (A2)", show_profiles=True, parent=parent)
        
        # 옵션 선택
        self.top_layout.addWidget(QLabel("탐색 방식을 선택하세요:"))
        
        self.btn_group = QButtonGroup(self)
        
        self.opt_a = QRadioButton("방식 A: 내가 구독한 채널 탐색")
        self.opt_b = QRadioButton("방식 B: 메인 피드 탐색")
        self.opt_b.setChecked(True) # 기본값
        
        self.btn_group.addButton(self.opt_a)
        self.btn_group.addButton(self.opt_b)
        
        opt_layout = QHBoxLayout()
        opt_layout.addWidget(self.opt_a)
        opt_layout.addWidget(self.opt_b)
        opt_layout.addStretch()
        
        self.top_layout.addLayout(opt_layout)

    def start_task(self):
        mode = "B" if self.opt_b.isChecked() else "A"
        headless, profile_path = self.get_common_params()
        
        self.run_btn.setEnabled(False)
        self.run_btn.setText("실행 중...")
        self.logger.clear()
        self.logger.info(f"방식 {mode}로 핫한 주제 탐색을 시작합니다... (Profile: {profile_path if profile_path else 'Incognito'}, Headless: {headless})")

        # 워커 실행
        self.worker = RadarWorker(TopicDiscovery, mode=mode, user_data_dir=profile_path, headless=headless)
        self.worker.log_signal.connect(self.on_log)
        self.worker.finished_signal.connect(self.on_finished)
        self.worker.start()
