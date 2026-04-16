from pathlib import Path
from PySide6.QtWidgets import (
    QLabel, QLineEdit, QVBoxLayout, QHBoxLayout, QPushButton,
    QListWidget, QTextEdit, QProgressBar, QFrame, QAbstractItemView,
)
from PySide6.QtCore import Qt
from utils.radar_common import RadarBaseWidget, RadarWorker, make_divider
from vivid_radar.a3_title import TitleGenerator, TitleVerifier

_TEMP_TITLES_PATH = Path(__file__).parent.parent / "vivid_radar" / "temp_titles.txt"

class A3Widget(RadarBaseWidget):
    def __init__(self, parent=None):
        # use_scroll=True를 사용하여 전체 스크롤바 지원
        super().__init__("💡 FindTitle (A3) - 하이브리드 최적화", show_profiles=False, use_scroll=True, parent=parent)
        self._setup_ui_v2()

    def _setup_ui_v2(self):
        """2단계 구조의 UI 레이아웃 구성 (Box Layout 기반)"""
        
        # --- Step 1: 레퍼런스 수집 영역 ---
        self.top_layout.addWidget(QLabel("<b>[Step 1] 레퍼런스 제목 수집</b>"))
        
        # [입력창 + +추가 버튼] 가로 묶음
        input_row = QHBoxLayout()
        self.ref_input = QLineEdit()
        self.ref_input.setPlaceholderText("조회수 대박 난 레퍼런스 제목을 입력하고 Enter...")
        self.ref_input.returnPressed.connect(self.add_reference)
        
        self.add_btn = QPushButton("+ 추가")
        self.add_btn.setFixedWidth(100)
        self.add_btn.clicked.connect(self.add_reference)
        
        input_row.addWidget(self.ref_input)
        input_row.addWidget(self.add_btn)
        self.top_layout.addLayout(input_row)

        # [레퍼런스 리스트박스]
        self.ref_list = QListWidget()
        self.ref_list.setFixedHeight(120)
        self.ref_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.ref_list.installEventFilter(self) 
        self.top_layout.addWidget(self.ref_list)

        # [선택 삭제 버튼]
        self.del_btn = QPushButton("선택 항목 삭제")
        self.del_btn.setFixedWidth(150)
        self.del_btn.clicked.connect(self.delete_reference)
        self.top_layout.addWidget(self.del_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        # [AI 제목 후보 생성 버튼] - 강조 스타일
        self.gen_titles_btn = QPushButton("✨ AI 제목 후보 생성 (100개)")
        self.gen_titles_btn.setObjectName("NextBtn")
        self.gen_titles_btn.setFixedHeight(45)
        self.gen_titles_btn.clicked.connect(self.start_generation)
        self.top_layout.addWidget(self.gen_titles_btn)

        self.top_layout.addWidget(make_divider())

        # --- Step 2: 후보 확인 및 검증 영역 ---
        self.top_layout.addWidget(QLabel("<b>[Step 2] AI 생성 후보 편집 및 시크릿 검증</b>"))
        
        self.candidates_edit = QTextEdit()
        self.candidates_edit.setPlaceholderText("AI가 생성한 100개의 후보가 여기에 표시됩니다. 자유롭게 수정/삭제하세요.")
        self.candidates_edit.setAcceptRichText(False)
        self.candidates_edit.setMinimumHeight(200)
        self.top_layout.addWidget(self.candidates_edit)

        # 프로그레스 바 영역
        progress_row = QHBoxLayout()
        self.pbar = QProgressBar()
        self.pbar.setTextVisible(True)
        self.pbar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pbar.setFixedHeight(20)
        
        self.status_lbl = QLabel("대기 중 (0/0)")
        self.status_lbl.setFixedWidth(120)
        
        progress_row.addWidget(self.pbar)
        progress_row.addWidget(self.status_lbl)
        self.top_layout.addLayout(progress_row)

        # 하단 실행 버튼 (Base 클래스의 run_btn을 시크릿 검증용으로 활용하되 위치 재조정 필요 없음)
        self.run_btn.setText("🔍 시크릿 모드 본격 탐색")
        self.run_btn.setFixedHeight(45)
        self.run_btn.setEnabled(False)

    # --- 이벤트 핸들러 ---
    def add_reference(self):
        text = self.ref_input.text().strip()
        if text:
            self.ref_list.addItem(text)
            self.ref_input.clear()

    def delete_reference(self):
        for item in self.ref_list.selectedItems():
            self.ref_list.takeItem(self.ref_list.row(item))

    def eventFilter(self, source, event):
        if event.type() == event.Type.KeyPress and source is self.ref_list:
            if event.key() == Qt.Key.Key_Delete:
                self.delete_reference()
                return True
        return super().eventFilter(source, event)

    def start_generation(self):
        refs = [self.ref_list.item(i).text() for i in range(self.ref_list.count())]
        if not refs:
            self.logger.error("먼저 레퍼런스 제목을 최소 하나 이상 추가해 주세요.")
            return

        self.gen_titles_btn.setEnabled(False)
        self.logger.info("Gemini 전략 수립 및 Gemma 100개 제목 생성 중...")
        
        self.worker = RadarWorker(TitleGenerator, refs)
        self.worker.log_signal.connect(self.on_log)
        self.worker.finished_signal.connect(self.on_gen_finished)
        self.worker.start()

    def start_task(self):
        raw_text = self.candidates_edit.toPlainText().strip()
        if not raw_text:
            self.logger.error("탐색할 제목 후보가 없습니다.")
            return

        titles = [line.strip() for line in raw_text.split('\n') if line.strip()]
        self.logger.info(f"총 {len(titles)}개의 제목을 15개 단위 배치로 재구성하여 탐색을 시작합니다.")

        self.run_btn.setEnabled(False)
        self.pbar.setMaximum(len(titles))
        self.pbar.setValue(0)
        
        headless, _ = self.get_common_params()

        self.worker = RadarWorker(TitleVerifier, titles, headless=headless)
        self.worker.log_signal.connect(self.on_log)
        self.worker.log_signal.connect(self.update_progress)
        self.worker.finished_signal.connect(self.on_finished)
        self.worker.start()

    def update_progress(self, msg, level):
        if "[PROGRESS]" in msg:
            try:
                parts = msg.replace("[PROGRESS]", "").strip().split()
                count_part = parts[0].split('/')
                current = int(count_part[0])
                total = int(count_part[1])
                
                self.pbar.setValue(current)
                self.status_lbl.setText(f"진행 중 ({current}/{total})")
            except:
                pass

    def on_gen_finished(self):
        if _TEMP_TITLES_PATH.exists():
            self.candidates_edit.setPlainText(_TEMP_TITLES_PATH.read_text(encoding="utf-8"))
        
        self.gen_titles_btn.setEnabled(True)
        self.run_btn.setEnabled(True)
        self.logger.success("제목 후보 생성이 완료되었습니다. 필요시 수정 후 검증을 시작하세요.")
