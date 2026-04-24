"""
steps/step3.py
3단계 — 소스 제작 및 Vrew 데이터 추출
  ① Watchdog : Downloads 폴더 감시 → asset/ 자동 이동·넘버링
  ② PDF 생성 : image_N.jpeg → storyboard.pdf (Pillow)
  ③ 파일 업로드 : 원본.vrew / TTS.mp3 / Subtitle.srt
  ④ 타임라인 JSON : Subtitle.srt → base_timeline.json
"""

import shutil
import time
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QStackedWidget, QFileDialog,
    QDialog, QTabWidget, QSpinBox, QComboBox,
    QListWidget, QFrame,
)

from utils.theme import (
    C_HIGHLIGHT, C_SUCCESS, C_ERROR,
    C_BG_INPUT, C_BORDER, C_TEXT,
)
from utils.widgets import (
    make_title, make_divider, make_status_box,
    StatusLogger, DropZone,
)
from utils.backend import generate_storyboard_pdf, generate_timeline_json


# ══════════════════════════════════════════════
# Watchdog 워커 (QThread 기반 — UI 블로킹 방지)
# ══════════════════════════════════════════════

class WatchdogWorker(QObject):
    """
    Downloads 폴더를 0.8초 간격으로 폴링하여
    새 이미지/영상 파일을 감지하면 asset/ 폴더로 이동·넘버링.
    """

    # ── 시그널 ───────────────────────────────
    file_detected  = Signal(str, str)   # (원본파일명, 저장된파일명)
    count_updated  = Signal(int, int)   # (image_count, intro_count)
    error_occurred = Signal(str)

    # ── 허용 확장자 ──────────────────────────
    IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    VIDEO_EXT = {".mp4", ".mov", ".avi", ".mkv"}

    # 다운로드 중 임시 확장자 (감지 제외)
    TEMP_EXT  = {".crdownload", ".part", ".tmp", ".download"}

    def __init__(self, downloads_dir: Path, asset_dir: Path, parent=None):
        super().__init__(parent)
        self._downloads_dir = downloads_dir
        self._asset_dir     = asset_dir
        self._running       = False
        self._seen: set[str] = set()   # 이미 처리한 파일명
        self._img_count  = 0
        self._vid_count  = 0

    def start_watch(self):
        """워커 진입점 (QThread.started 시그널에 연결)"""
        self._running = True
        # 시작 시점의 파일 + 폴더 스냅샷 (이미 존재하는 것은 무시)
        self._seen      = {f.name for f in self._downloads_dir.iterdir() if f.is_file()}
        self._seen_dirs: set[str] = {
            d.name for d in self._downloads_dir.iterdir() if d.is_dir()
        }
        self._watched_subdirs: set[Path] = set()   # 감시 중인 하위 폴더

        while self._running:
            try:
                self._scan()
                self._scan_new_subdirs()
            except Exception as e:
                self.error_occurred.emit(str(e))
            time.sleep(0.8)

    def stop(self):
        self._running = False

    def set_counts(self, img: int, vid: int) -> None:
        """
        수동 에셋 조작 후 카운터를 외부에서 동기화.
        Python GIL로 int 대입은 원자적이므로 별도 Lock 불필요.
        """
        self._img_count = img
        self._vid_count = vid

    def _scan(self):
        """다운로드 폴더(루트)에서 신규 파일 감지 및 이동"""
        self._scan_dir(self._downloads_dir, self._seen)

    def _scan_new_subdirs(self):
        """Watchdog 활성화 이후 새로 생긴 하위 폴더를 감지하여 감시 추가"""
        for item in self._downloads_dir.iterdir():
            if not item.is_dir():
                continue
            if item.name in self._seen_dirs:
                continue
            # 새 폴더 발견 → 감시 목록에 추가
            self._seen_dirs.add(item.name)
            self._watched_subdirs.add(item)
            self.error_occurred.emit(f"[Watchdog] 새 폴더 감지 — '{item.name}' 내부도 감시합니다.")

        # 이미 감시 중인 하위 폴더 내부도 스캔
        for sub in list(self._watched_subdirs):
            if not sub.exists():
                self._watched_subdirs.discard(sub)
                continue
            seen_key = f"__sub__{sub.name}"
            if seen_key not in self.__dict__:
                self.__dict__[seen_key] = {
                    f.name for f in sub.iterdir() if f.is_file()
                }
            self._scan_dir(sub, self.__dict__[seen_key])

    def _scan_dir(self, directory: Path, seen: set):
        """지정 디렉토리에서 신규 이미지/영상 파일 감지 및 이동 (공통 로직)"""
        for f in directory.iterdir():
            if not f.is_file():
                continue
            if f.suffix.lower() in self.TEMP_EXT:
                continue
            if f.name in seen:
                continue

            # 파일 쓰기가 완료됐는지 안정화 대기
            if not self._is_stable(f):
                continue

            seen.add(f.name)
            ext = f.suffix.lower()

            if ext in self.IMAGE_EXT:
                self._img_count += 1
                dest_name = f"image_{self._img_count}.jpeg"
                dest = self._asset_dir / dest_name
                try:
                    shutil.move(str(f), str(dest))
                    self.file_detected.emit(f.name, dest_name)
                    self.count_updated.emit(self._img_count, self._vid_count)
                except Exception as e:
                    self.error_occurred.emit(f"이미지 이동 실패: {e}")
                    self._img_count -= 1

            elif ext in self.VIDEO_EXT:
                self._vid_count += 1
                dest_name = f"intro_{self._vid_count}.mp4"
                dest = self._asset_dir / dest_name
                try:
                    shutil.move(str(f), str(dest))
                    self.file_detected.emit(f.name, dest_name)
                    self.count_updated.emit(self._img_count, self._vid_count)
                except Exception as e:
                    self.error_occurred.emit(f"영상 이동 실패: {e}")
                    self._vid_count -= 1

    @staticmethod
    def _is_stable(path: Path, wait: float = 0.5) -> bool:
        """파일 크기가 wait초 후에도 동일하면 쓰기 완료로 판단"""
        try:
            size1 = path.stat().st_size
            time.sleep(wait)
            size2 = path.stat().st_size
            return size1 == size2 and size1 > 0
        except OSError:
            return False


# ══════════════════════════════════════════════
# AssetManagerDialog — 수동 에셋 추가 / 번호 교체
# ══════════════════════════════════════════════

class AssetManagerDialog(QDialog):
    """
    Watchdog 외 수동 에셋 제어 팝업.

    탭 A — 수동 추가 (Add)
      · 다중 파일 선택 → asset/ 내 최대 번호 이후로 순차 저장
      · 이미지: image_{n}.jpeg  /  영상: intro_{n}.mp4

    탭 B — 번호 교체 (Replace)
      · 타입(이미지/영상) + 교체 번호 입력
      · 선택한 파일로 해당 번호 파일을 덮어씌움(Overwrite)

    하네스:
      · 0바이트 파일 업로드 시 에러 처리
      · 확장자 통일: 이미지→.jpeg, 영상→.mp4
    """

    IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
    VIDEO_EXT = {".mp4", ".mov", ".avi", ".mkv", ".webm"}

    def __init__(self, asset_dir: Path, parent=None):
        super().__init__(parent)
        self._asset_dir = asset_dir
        self._asset_dir.mkdir(parents=True, exist_ok=True)

        self.setWindowTitle("📁  에셋 관리자")
        self.setMinimumSize(580, 420)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setStyleSheet(
            f"QDialog  {{ background:{C_BG_INPUT}; color:{C_TEXT}; }}"
            f"QLabel   {{ color:{C_TEXT}; }}"
            f"QTabWidget::pane {{ border: 1px solid {C_BORDER}; }}"
            f"QTabBar::tab {{ background:#2A2A2A; color:{C_TEXT}; padding:6px 18px; }}"
            f"QTabBar::tab:selected {{ background:{C_HIGHLIGHT}; color:#000; font-weight:bold; }}"
        )
        self._build_ui()

    # ── 현재 최대 번호 스캔 (동기, 빠름) ─────────────────────────────────

    def _scan_max(self) -> tuple[int, int]:
        """asset/ 폴더의 image_N.jpeg, intro_N.mp4 최대 번호 반환"""
        img_max = 0
        for f in self._asset_dir.glob("image_*.jpeg"):
            try:
                n = int(f.stem.split("_", 1)[1])
                img_max = max(img_max, n)
            except (ValueError, IndexError):
                pass

        vid_max = 0
        for f in self._asset_dir.glob("intro_*.mp4"):
            try:
                n = int(f.stem.split("_", 1)[1])
                vid_max = max(vid_max, n)
            except (ValueError, IndexError):
                pass

        return img_max, vid_max

    # ── UI 구성 ──────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(10)

        title = QLabel("📁  에셋 관리자  —  수동 업로드 및 교체")
        title.setStyleSheet(
            f"color:{C_HIGHLIGHT}; font-size:13px; font-weight:bold;"
        )
        root.addWidget(title)

        # 현황 레이블 (갱신 가능)
        self._status_lbl = QLabel()
        self._status_lbl.setStyleSheet("color:#AAAAAA; font-size:11px;")
        self._refresh_status_lbl()
        root.addWidget(self._status_lbl)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet(f"color:{C_BORDER};")
        root.addWidget(divider)

        # ── 탭 위젯 ──
        tabs = QTabWidget()
        root.addWidget(tabs)

        # ── 탭 A: 수동 추가 ──
        tab_add = QWidget()
        tab_add.setStyleSheet(f"background:{C_BG_INPUT};")
        self._build_tab_add(tab_add)
        tabs.addTab(tab_add, "➕  수동 추가 (Add)")

        # ── 탭 B: 번호 교체 ──
        tab_rep = QWidget()
        tab_rep.setStyleSheet(f"background:{C_BG_INPUT};")
        self._build_tab_replace(tab_rep)
        tabs.addTab(tab_rep, "🔄  번호 교체 (Replace)")

        # ── 닫기 버튼 ──
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("닫기")
        close_btn.setFixedWidth(80)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

    # ── 탭 A: 수동 추가 ──────────────────────────────────────────────────

    def _build_tab_add(self, parent: QWidget):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        guide = QLabel(
            "이미지(.jpg/.jpeg/.png 등) 또는 영상(.mp4/.mov 등) 파일을 선택하면\n"
            "기존 최대 번호 다음부터 순차적으로 저장합니다."
        )
        guide.setStyleSheet("color:#AAAAAA; font-size:11px;")
        guide.setWordWrap(True)
        layout.addWidget(guide)

        # 파일 목록
        self._add_list = QListWidget()
        self._add_list.setStyleSheet(
            f"background:#111111; color:{C_TEXT}; border:1px solid {C_BORDER};"
            "font-size:11px;"
        )
        self._add_list.setFixedHeight(120)
        layout.addWidget(self._add_list)

        # 버튼 행
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        select_btn = QPushButton("📂  파일 선택 (다중)")
        select_btn.clicked.connect(self._on_add_select)
        btn_row.addWidget(select_btn)

        clear_btn = QPushButton("목록 초기화")
        clear_btn.setFixedWidth(90)
        clear_btn.clicked.connect(self._add_list.clear)
        btn_row.addWidget(clear_btn)

        btn_row.addStretch()

        self._add_execute_btn = QPushButton("✅  추가 실행")
        self._add_execute_btn.setStyleSheet(
            f"background:{C_SUCCESS}; color:#000; font-weight:bold;"
            "padding:5px 16px; border-radius:4px;"
        )
        self._add_execute_btn.clicked.connect(self._on_add_execute)
        btn_row.addWidget(self._add_execute_btn)

        layout.addLayout(btn_row)

        # 결과 레이블
        self._add_result_lbl = QLabel("")
        self._add_result_lbl.setStyleSheet("font-size:11px;")
        self._add_result_lbl.setWordWrap(True)
        layout.addWidget(self._add_result_lbl)
        layout.addStretch()

        # 선택한 파일 경로 보관
        self._add_files: list[Path] = []

    def _on_add_select(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "추가할 에셋 파일 선택 (다중 선택 가능)",
            str(Path.home()),
            "이미지/영상 파일 (*.jpg *.jpeg *.png *.webp *.gif *.bmp *.mp4 *.mov *.avi *.mkv *.webm)",
        )
        self._add_files = [Path(p) for p in paths]
        self._add_list.clear()
        for p in self._add_files:
            self._add_list.addItem(f"  {p.name}")

    def _on_add_execute(self):
        if not self._add_files:
            self._add_result_lbl.setText("⚠  파일을 먼저 선택해주세요.")
            self._add_result_lbl.setStyleSheet(f"color:{C_ERROR}; font-size:11px;")
            return

        img_max, vid_max = self._scan_max()
        saved_msgs: list[str] = []
        error_msgs: list[str] = []

        for src in self._add_files:
            ext = src.suffix.lower()

            # 0바이트 하네스
            try:
                if src.stat().st_size == 0:
                    error_msgs.append(f"✗ {src.name}  [0바이트 — 건너뜀]")
                    continue
            except OSError as e:
                error_msgs.append(f"✗ {src.name}  [{e}]")
                continue

            if ext in self.IMAGE_EXT:
                img_max += 1
                dest = self._asset_dir / f"image_{img_max}.jpeg"
            elif ext in self.VIDEO_EXT:
                vid_max += 1
                dest = self._asset_dir / f"intro_{vid_max}.mp4"
            else:
                error_msgs.append(f"✗ {src.name}  [지원하지 않는 형식]")
                continue

            try:
                shutil.copy2(str(src), str(dest))
                saved_msgs.append(f"✔ {src.name}  →  {dest.name}")
            except Exception as e:
                error_msgs.append(f"✗ {src.name}  [{e}]")
                # 실패 시 번호 되돌림
                if ext in self.IMAGE_EXT:
                    img_max -= 1
                else:
                    vid_max -= 1

        lines = saved_msgs + error_msgs
        result_text = "\n".join(lines) if lines else "처리된 파일이 없습니다."
        color = C_SUCCESS if not error_msgs else (C_ERROR if not saved_msgs else C_HIGHLIGHT)
        self._add_result_lbl.setText(result_text)
        self._add_result_lbl.setStyleSheet(f"color:{color}; font-size:11px;")

        self._add_files.clear()
        self._add_list.clear()
        self._refresh_status_lbl()

    # ── 탭 B: 번호 교체 ──────────────────────────────────────────────────

    def _build_tab_replace(self, parent: QWidget):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        guide = QLabel(
            "교체할 파일의 종류와 번호를 지정한 뒤, 새 파일을 선택하면\n"
            "해당 번호 파일을 강제로 덮어씌웁니다."
        )
        guide.setStyleSheet("color:#AAAAAA; font-size:11px;")
        guide.setWordWrap(True)
        layout.addWidget(guide)

        # 설정 행
        cfg_row = QHBoxLayout()
        cfg_row.setSpacing(12)

        # 타입 선택
        type_lbl = QLabel("파일 종류:")
        type_lbl.setFixedWidth(70)
        cfg_row.addWidget(type_lbl)

        self._rep_type = QComboBox()
        self._rep_type.addItems(["이미지 (image_N.jpeg)", "영상 (intro_N.mp4)"])
        self._rep_type.setStyleSheet(
            f"background:#2A2A2A; color:{C_TEXT}; border:1px solid {C_BORDER};"
            "padding:4px 8px; border-radius:4px;"
        )
        self._rep_type.setFixedWidth(200)
        cfg_row.addWidget(self._rep_type)

        # 번호 입력
        num_lbl = QLabel("교체 번호:")
        num_lbl.setFixedWidth(70)
        cfg_row.addWidget(num_lbl)

        self._rep_num = QSpinBox()
        self._rep_num.setRange(1, 9999)
        self._rep_num.setValue(1)
        self._rep_num.setFixedWidth(80)
        self._rep_num.setStyleSheet(
            f"background:#2A2A2A; color:{C_TEXT}; border:1px solid {C_BORDER};"
            "padding:4px; border-radius:4px;"
        )
        cfg_row.addWidget(self._rep_num)
        cfg_row.addStretch()
        layout.addLayout(cfg_row)

        # 파일 선택 + 결과 행
        file_row = QHBoxLayout()
        file_row.setSpacing(8)

        self._rep_file_lbl = QLabel("선택된 파일: 없음")
        self._rep_file_lbl.setStyleSheet("color:#888888; font-size:11px;")
        file_row.addWidget(self._rep_file_lbl)
        file_row.addStretch()

        select_btn = QPushButton("📂  파일 선택")
        select_btn.clicked.connect(self._on_rep_select)
        file_row.addWidget(select_btn)

        layout.addLayout(file_row)

        # 교체 실행 버튼
        exec_row = QHBoxLayout()
        exec_row.addStretch()

        self._rep_execute_btn = QPushButton("🔄  교체 실행 (Overwrite)")
        self._rep_execute_btn.setStyleSheet(
            f"background:#C0392B; color:#FFFFFF; font-weight:bold;"
            "padding:5px 20px; border-radius:4px;"
        )
        self._rep_execute_btn.clicked.connect(self._on_rep_execute)
        exec_row.addWidget(self._rep_execute_btn)
        layout.addLayout(exec_row)

        # 결과 레이블
        self._rep_result_lbl = QLabel("")
        self._rep_result_lbl.setStyleSheet("font-size:11px;")
        self._rep_result_lbl.setWordWrap(True)
        layout.addWidget(self._rep_result_lbl)
        layout.addStretch()

        self._rep_file: Path | None = None

    def _on_rep_select(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "교체할 파일 선택",
            str(Path.home()),
            "이미지/영상 파일 (*.jpg *.jpeg *.png *.webp *.gif *.bmp *.mp4 *.mov *.avi *.mkv *.webm)",
        )
        if path:
            self._rep_file = Path(path)
            self._rep_file_lbl.setText(f"선택된 파일: {self._rep_file.name}")
            self._rep_file_lbl.setStyleSheet(f"color:{C_SUCCESS}; font-size:11px;")

    def _on_rep_execute(self):
        if self._rep_file is None:
            self._rep_result_lbl.setText("⚠  파일을 먼저 선택해주세요.")
            self._rep_result_lbl.setStyleSheet(f"color:{C_ERROR}; font-size:11px;")
            return

        src = self._rep_file
        num = self._rep_num.value()
        is_image = self._rep_type.currentIndex() == 0

        # 0바이트 하네스
        try:
            if src.stat().st_size == 0:
                self._rep_result_lbl.setText(f"✗ 파일이 비어 있습니다 (0바이트): {src.name}")
                self._rep_result_lbl.setStyleSheet(f"color:{C_ERROR}; font-size:11px;")
                return
        except OSError as e:
            self._rep_result_lbl.setText(f"✗ 파일 접근 오류: {e}")
            self._rep_result_lbl.setStyleSheet(f"color:{C_ERROR}; font-size:11px;")
            return

        # 확장자 검증
        ext = src.suffix.lower()
        if is_image and ext not in self.IMAGE_EXT:
            self._rep_result_lbl.setText(f"✗ '{src.name}'은(는) 이미지 파일이 아닙니다.")
            self._rep_result_lbl.setStyleSheet(f"color:{C_ERROR}; font-size:11px;")
            return
        if not is_image and ext not in self.VIDEO_EXT:
            self._rep_result_lbl.setText(f"✗ '{src.name}'은(는) 영상 파일이 아닙니다.")
            self._rep_result_lbl.setStyleSheet(f"color:{C_ERROR}; font-size:11px;")
            return

        # 대상 파일 경로 (확장자 통일)
        if is_image:
            dest = self._asset_dir / f"image_{num}.jpeg"
        else:
            dest = self._asset_dir / f"intro_{num}.mp4"

        try:
            shutil.copy2(str(src), str(dest))
            self._rep_result_lbl.setText(
                f"✔  교체 완료:\n  {src.name}  →  {dest.name}"
            )
            self._rep_result_lbl.setStyleSheet(f"color:{C_SUCCESS}; font-size:11px;")
            self._rep_file = None
            self._rep_file_lbl.setText("선택된 파일: 없음")
            self._rep_file_lbl.setStyleSheet("color:#888888; font-size:11px;")
        except Exception as e:
            self._rep_result_lbl.setText(f"✗ 교체 실패: {e}")
            self._rep_result_lbl.setStyleSheet(f"color:{C_ERROR}; font-size:11px;")

        self._refresh_status_lbl()

    # ── 공통 헬퍼 ───────────────────────────────────────────────────────

    def _refresh_status_lbl(self):
        img_max, vid_max = self._scan_max()
        self._status_lbl.setText(
            f"현재 에셋 현황 —  이미지: {img_max}장 (image_1 ~ image_{img_max})  "
            f"|  영상: {vid_max}개 (intro_1 ~ intro_{vid_max})"
        )


# ══════════════════════════════════════════════
# Step3Widget
# ══════════════════════════════════════════════

class Step3Widget(QWidget):

    def __init__(self, stack: QStackedWidget, parent=None):
        super().__init__(parent)
        self._stack        = stack
        self._project_dir: Path | None = None

        # Watchdog 상태
        self._wd_thread:  QThread | None       = None
        self._wd_worker:  WatchdogWorker | None = None
        self._wd_running  = False
        self._img_count   = 0
        self._vid_count   = 0

        # 업로드된 파일 추적 {ext: Path}
        self._uploaded: dict[str, Path] = {}

        self._build_ui()

    # ── UI 구성 ──────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 32, 24)
        root.setSpacing(12)

        root.addWidget(make_title("3. 소스 제작"))

        # 상태창
        self._status_box = make_status_box()
        root.addWidget(self._status_box)
        self._log = StatusLogger(self._status_box)

        root.addWidget(make_divider())

        # ── 섹션 A: Watchdog + PDF ──────────────────────────
        sec_a_lbl = QLabel("[ STEP A ]  스토리보드 이미지 & 인트로 영상 수집")
        sec_a_lbl.setStyleSheet(
            f"color:{C_HIGHLIGHT}; font-size:12px; font-weight:bold;"
        )
        root.addWidget(sec_a_lbl)

        row_a = QHBoxLayout()
        row_a.setSpacing(10)

        # Watchdog 토글 버튼
        self._wd_btn = QPushButton("🔴  Watchdog 실행")
        self._wd_btn.setCheckable(False)
        self._wd_btn.clicked.connect(self._on_watchdog_toggle)
        row_a.addWidget(self._wd_btn)

        # 에셋 관리자 버튼
        self._asset_mgr_btn = QPushButton("📁  에셋 관리")
        self._asset_mgr_btn.setToolTip(
            "수동으로 에셋을 추가하거나 특정 번호 파일을 교체합니다."
        )
        self._asset_mgr_btn.clicked.connect(self._on_asset_manager_click)
        row_a.addWidget(self._asset_mgr_btn)

        # PDF 생성 버튼
        self._pdf_btn = QPushButton("📄  스토리보드 PDF 생성")
        self._pdf_btn.clicked.connect(self._on_pdf_click)
        row_a.addWidget(self._pdf_btn)

        row_a.addStretch()
        root.addLayout(row_a)

        # Watchdog 카운터 레이블
        self._wd_status_lbl = QLabel("🔴  대기 중")
        self._wd_status_lbl.setStyleSheet("color:#555555; font-size:12px;")
        root.addWidget(self._wd_status_lbl)

        root.addWidget(make_divider())

        # ── 섹션 B: 파일 업로드 (vrew / mp3 / srt) ──────────
        sec_b_lbl = QLabel(
            "[ STEP B ]  원본.vrew  /  TTS.mp3  /  Subtitle.srt  /  intro_cue.txt  업로드"
        )
        sec_b_lbl.setStyleSheet(
            f"color:{C_HIGHLIGHT}; font-size:12px; font-weight:bold;"
        )
        root.addWidget(sec_b_lbl)

        self._drop_zone = DropZone(
            label=(
                "원본.vrew · TTS.mp3 · Subtitle.srt · intro_cue.txt\n"
                "파일을 한꺼번에 끌어다 놓으세요\n"
                "(또는 아래 버튼으로 선택)"
            ),
            accepted_ext=(".vrew", ".mp3", ".srt", ".txt"),
            multi=True,
        )
        self._drop_zone.file_dropped.connect(self._on_file_received)
        root.addWidget(self._drop_zone)

        # 업로드 버튼 + 타임라인 JSON 버튼
        row_b = QHBoxLayout()
        row_b.setSpacing(10)

        self._upload_btn = QPushButton("📁  파일 업로드")
        self._upload_btn.setToolTip("원본.vrew / TTS.mp3 / Subtitle.srt / intro_cue.txt")
        self._upload_btn.clicked.connect(self._on_upload_click)
        row_b.addWidget(self._upload_btn)

        self._timeline_btn = QPushButton("🗂  타임라인 JSON 생성")
        self._timeline_btn.setEnabled(False)
        self._timeline_btn.clicked.connect(self._on_timeline_click)
        row_b.addWidget(self._timeline_btn)

        row_b.addStretch()
        root.addLayout(row_b)

        # 업로드 현황 레이블
        self._upload_status_lbl = QLabel("업로드 현황:  vrew ✗  /  mp3 ✗  /  srt ✗  /  cue ✗")
        self._upload_status_lbl.setStyleSheet("color:#555555; font-size:12px;")
        root.addWidget(self._upload_status_lbl)

        # 파일명 정규화 안내
        norm_hint = QLabel(
            "※ 업로드 시 파일명에 상관없이 "
            "원본.vrew · TTS.mp3 · Subtitle.srt · intro_cue.txt 로 자동 변환되어 저장됩니다."
        )
        norm_hint.setStyleSheet(
            f"color:{C_HIGHLIGHT}; font-size:11px;"
        )
        norm_hint.setWordWrap(True)
        root.addWidget(norm_hint)

        root.addWidget(make_divider())

        # ── 내비게이션 ────────────────────────────────────────
        nav_row = QHBoxLayout()
        nav_row.setSpacing(12)

        back_btn = QPushButton("◀  BACK")
        back_btn.clicked.connect(self._on_back)
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
        self._stop_watchdog()
        self._project_dir = path
        self._img_count   = 0
        self._vid_count   = 0
        self._uploaded    = {}
        self._next_btn.setEnabled(False)
        self._timeline_btn.setEnabled(False)
        self._drop_zone.reset()
        self._log.clear()
        self._refresh_wd_label()
        self._refresh_upload_label()
        if path:
            self._log.highlight(f"프로젝트: {path.name}")
            # ── 기존 파일 복원 ──────────────────────────────────
            asset_dir    = path / "asset"
            timeline     = asset_dir / "base_timeline.json"
            tts          = asset_dir / "TTS.mp3"
            srt          = asset_dir / "Subtitle.srt"

            if timeline.exists():
                # 타임라인까지 완료 → NEXT 활성화
                existing = []
                if tts.exists(): existing.append("TTS.mp3")
                if srt.exists(): existing.append("Subtitle.srt")
                if existing:
                    self._drop_zone.set_ready(", ".join(existing))
                    for f in existing:
                        self._uploaded[f.split(".")[1].lower()] = True
                self._timeline_btn.setEnabled(False)
                self._next_btn.setEnabled(True)
                self._log.success("타임라인 JSON이 이미 생성된 프로젝트입니다.")
                self._log.info("NEXT 버튼으로 다음 단계로 넘어가세요.")
            elif tts.exists() or srt.exists():
                # 파일 업로드는 됐으나 타임라인 미생성
                existing = []
                if tts.exists(): existing.append("TTS.mp3")
                if srt.exists(): existing.append("Subtitle.srt")
                self._drop_zone.set_ready(", ".join(existing))
                for f in existing:
                    self._uploaded[f.split(".")[1].lower()] = True
                if tts.exists() and srt.exists():
                    self._timeline_btn.setEnabled(True)
                self._log.success(f"업로드된 파일 확인: {', '.join(existing)}")
                self._log.info("'타임라인 JSON 생성' 버튼을 눌러주세요.")
            else:
                self._log.info(
                    "Flow 웹사이트에서 인트로 이미지를 생성 후 Watchdog을 활성화 하세요."
                )
            # 에셋 카운터 동기화
            self._sync_counts()

    # ── §A: Watchdog ────────────────────────────────────────

    def _on_watchdog_toggle(self):
        if self._wd_running:
            self._stop_watchdog()
        else:
            self._start_watchdog()

    def _start_watchdog(self):
        if self._project_dir is None:
            self._log.error("프로젝트 폴더가 없습니다. 1단계로 돌아가세요.")
            return

        asset_dir = self._project_dir / "asset"
        asset_dir.mkdir(parents=True, exist_ok=True)
        downloads_dir = Path.home() / "Downloads"

        if not downloads_dir.exists():
            self._log.error(f"다운로드 폴더를 찾을 수 없습니다: {downloads_dir}")
            return

        self._wd_thread = QThread(self)
        self._wd_worker = WatchdogWorker(downloads_dir, asset_dir)
        self._wd_worker.moveToThread(self._wd_thread)

        # 시그널 연결
        self._wd_thread.started.connect(self._wd_worker.start_watch)
        self._wd_worker.file_detected.connect(self._on_file_detected)
        self._wd_worker.count_updated.connect(self._on_count_updated)
        self._wd_worker.error_occurred.connect(
            lambda msg: self._log.error(f"[Watchdog] {msg}")
        )

        self._wd_running = True
        self._wd_thread.start()

        self._refresh_wd_label()
        self._wd_btn.setText("🟢  Watchdog 중지")
        self._wd_btn.setObjectName("WatchdogActive")
        self._wd_btn.setStyleSheet(
            f"background-color:#1A3A1A; color:{C_SUCCESS};"
            f"border:1px solid {C_SUCCESS}; border-radius:6px;"
            f"padding:10px 20px; font-size:13px; font-weight:bold;"
        )

        self._log.success(
            "Watchdog 시작됨. Downloads 폴더를 감시 중입니다.\n"
            "스토리보드 이미지와 인트로 영상을 다운받으세요."
        )

    def _stop_watchdog(self):
        if self._wd_worker:
            self._wd_worker.stop()
        if self._wd_thread:
            self._wd_thread.quit()
            self._wd_thread.wait(2000)
        self._wd_thread  = None
        self._wd_worker  = None
        self._wd_running = False

        self._wd_btn.setText("🔴  Watchdog 실행")
        self._wd_btn.setObjectName("")
        self._wd_btn.setStyleSheet("")   # GLOBAL_QSS 복원
        self._refresh_wd_label()

        if self._img_count > 0 or self._vid_count > 0:
            self._log.info("Watchdog 중지됨.")

    def _on_file_detected(self, original: str, saved: str):
        self._log.info(f"  [감지] {original}  →  {saved}")

    def _on_count_updated(self, img: int, vid: int):
        self._img_count = img
        self._vid_count = vid
        self._refresh_wd_label()
        self._log.highlight(
            f"[🟢 파일 감지 중]  "
            f"스토리보드 이미지 {img}장 / 인트로 영상 {vid}개 확인되었습니다."
        )

    def _refresh_wd_label(self):
        if self._wd_running:
            self._wd_status_lbl.setText(
                f"🟢  파일 감지 중  |  이미지 {self._img_count}장  "
                f"|  영상 {self._vid_count}개"
            )
            self._wd_status_lbl.setStyleSheet(f"color:{C_SUCCESS}; font-size:12px;")
        else:
            self._wd_status_lbl.setText("🔴  대기 중")
            self._wd_status_lbl.setStyleSheet("color:#555555; font-size:12px;")

    # ── §A-2: 에셋 관리자 팝업 ──────────────────────────────────────────

    def _on_asset_manager_click(self):
        if self._project_dir is None:
            self._log.error("프로젝트 폴더가 없습니다. 1단계로 돌아가세요.")
            return

        asset_dir = self._project_dir / "asset"
        dlg = AssetManagerDialog(asset_dir, parent=self)
        dlg.exec()

        # 팝업이 닫히면 반드시 카운터 동기화
        self._sync_counts()
        self._log.info(
            f"에셋 관리자 작업 완료 — "
            f"이미지 {self._img_count}장 / 영상 {self._vid_count}개"
        )

    def _sync_counts(self) -> None:
        """
        asset/ 폴더를 스캔하여 _img_count, _vid_count를 실제 파일 기준으로 최신화.
        Watchdog이 실행 중이면 워커 내부 카운터도 동기화하여 번호 충돌을 방지.
        """
        if self._project_dir is None:
            return

        asset_dir = self._project_dir / "asset"

        # image_N.jpeg 최대 번호
        img_max = 0
        for f in asset_dir.glob("image_*.jpeg"):
            try:
                n = int(f.stem.split("_", 1)[1])
                img_max = max(img_max, n)
            except (ValueError, IndexError):
                pass

        # intro_N.mp4 최대 번호
        vid_max = 0
        for f in asset_dir.glob("intro_*.mp4"):
            try:
                n = int(f.stem.split("_", 1)[1])
                vid_max = max(vid_max, n)
            except (ValueError, IndexError):
                pass

        self._img_count = img_max
        self._vid_count = vid_max

        # Watchdog 워커가 살아 있으면 동기화
        if self._wd_worker is not None:
            self._wd_worker.set_counts(img_max, vid_max)

        self._refresh_wd_label()

    # ── §B: PDF 생성 ─────────────────────────────────────────

    def _on_pdf_click(self):
        if self._project_dir is None:
            self._log.error("프로젝트 폴더가 없습니다.")
            return

        asset_dir = self._project_dir / "asset"
        self._log.info("스토리보드 PDF 생성 중...")

        try:
            out = generate_storyboard_pdf(asset_dir)
        except (ValueError, ImportError) as e:
            self._log.error(str(e))
            return
        except Exception as e:
            self._log.error(f"PDF 생성 오류:\n{e}")
            return

        self._log.success(
            f"PDF 생성 완료  →  {out.name}\n"
            "Vrew에서 대본을 붙여넣고 초안을 만든 뒤,\n"
            "[원본.vrew]  [TTS.mp3]  [Subtitle.srt] 3개 파일을 업로드하세요."
        )

    # ── §C: 파일 업로드 (vrew / mp3 / srt) ──────────────────

    def _on_upload_click(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "파일 선택 (원본.vrew / TTS.mp3 / Subtitle.srt / intro_cue.txt)",
            str(Path.home()),
            "지원 파일 (*.vrew *.mp3 *.srt *.txt)",
        )
        for p in paths:
            self._on_file_received(p)

    def _on_file_received(self, src_path: str):
        src = Path(src_path)
        ext = src.suffix.lower()

        # .txt 는 intro_cue.txt 만 허용
        if ext == ".txt" and src.stem.lower() != "intro_cue":
            self._log.error(
                f"'{src.name}'은(는) 허용되지 않는 txt 파일입니다.\n"
                "'intro_cue.txt' 파일만 업로드 가능합니다."
            )
            return

        if ext not in (".vrew", ".mp3", ".srt", ".txt"):
            self._log.error(f"'{src.name}'은(는) 지원되지 않는 파일 형식입니다.")
            return

        # ── 하네스: 0바이트 ──
        if src.stat().st_size == 0:
            self._log.error(f"'{src.name}' 파일이 비어 있습니다 (0바이트).")
            return

        if self._project_dir is None:
            self._log.error("프로젝트 폴더가 없습니다.")
            return

        asset_dir = self._project_dir / "asset"
        asset_dir.mkdir(parents=True, exist_ok=True)
        input_dir = self._project_dir / "input"
        input_dir.mkdir(parents=True, exist_ok=True)

        # 표준화된 저장 이름 결정 (파일명에 상관없이 표준명으로 정규화)
        # .txt(intro_cue)는 사용자 원본이므로 input/ 저장, 나머지 제작 에셋은 asset/ 저장
        name_map = {
            ".vrew": (asset_dir, "원본.vrew"),
            ".mp3":  (asset_dir, "TTS.mp3"),
            ".srt":  (asset_dir, "Subtitle.srt"),
            ".txt":  (input_dir, "intro_cue.txt"),
        }
        dest_dir, dest_name = name_map[ext]
        dest = dest_dir / dest_name

        try:
            shutil.copy2(str(src), str(dest))
        except Exception as e:
            self._log.error(f"파일 저장 중 오류:\n{e}")
            return

        self._uploaded[ext] = dest
        if src.name != dest.name:
            self._log.info(f"파일명 정규화: '{src.name}'  →  '{dest.name}'")
        self._log.success(f"저장됨: {dest.name}")
        self._refresh_upload_label()
        self._check_all_uploaded()

    def _refresh_upload_label(self):
        def mark(ext: str) -> str:
            return (
                f'<span style="color:{C_SUCCESS};">&#10004;</span>'
                if ext in self._uploaded
                else f'<span style="color:#555555;">✗</span>'
            )

        self._upload_status_lbl.setText(
            f"업로드 현황:&nbsp;&nbsp;"
            f"vrew {mark('.vrew')}&nbsp;&nbsp;/&nbsp;&nbsp;"
            f"mp3 {mark('.mp3')}&nbsp;&nbsp;/&nbsp;&nbsp;"
            f"srt {mark('.srt')}&nbsp;&nbsp;/&nbsp;&nbsp;"
            f"cue {mark('.txt')}"
        )
        self._upload_status_lbl.setTextFormat(Qt.TextFormat.RichText)

    def _check_all_uploaded(self):
        # srt 필수, 나머지는 선택 — srt 있으면 타임라인 생성 가능
        if ".srt" in self._uploaded and ".mp3" in self._uploaded:
            ready_names = []
            if ".vrew" in self._uploaded: ready_names.append("원본.vrew")
            ready_names += ["TTS.mp3", "Subtitle.srt"]
            if ".txt" in self._uploaded:  ready_names.append("intro_cue.txt")
            self._drop_zone.set_ready("  /  ".join(ready_names))
            self._log.success(
                f"{len(ready_names)}개 파일 확인되었습니다. 타임라인을 생성해주세요."
            )
            self._timeline_btn.setEnabled(True)

    # ── §D: 타임라인 JSON 생성 ───────────────────────────────

    def _on_timeline_click(self):
        if self._project_dir is None:
            self._log.error("프로젝트 폴더가 없습니다.")
            return

        asset_dir = self._project_dir / "asset"
        self._log.info("SRT 파싱 및 타임라인 JSON 생성 중...")

        try:
            out = generate_timeline_json(asset_dir)
        except (FileNotFoundError, ValueError) as e:
            self._log.error(str(e))
            return
        except Exception as e:
            self._log.error(f"타임라인 생성 오류:\n{e}")
            return

        self._log.success(
            f"타임라인이 생성되었습니다.  →  {out.name}\n"
            "다음 단계로 넘어가세요."
        )
        self._next_btn.setEnabled(True)
        self._timeline_btn.setEnabled(False)

    # ── 내비게이션 ───────────────────────────────────────────

    def _on_back(self):
        self._stop_watchdog()
        self._stack.setCurrentIndex(1)

    def _go_next(self):
        self._stop_watchdog()
        step4 = self._stack.widget(3)
        step4.set_project_dir(self._project_dir)
        self._stack.setCurrentIndex(3)

    # ── 위젯 소멸 시 Watchdog 정리 ──────────────────────────

    def closeEvent(self, event):
        self._stop_watchdog()
        super().closeEvent(event)
