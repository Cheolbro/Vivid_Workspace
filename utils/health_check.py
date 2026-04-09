"""
utils/health_check.py
환경 자동 진단 (Health Check) 모듈
  - node / ffmpeg / npx remotion 설치 여부 + 버전 백그라운드 체크
  - Project_templete/remotion/node_modules 존재 확인
  - 미설치 시 npm install 자동 실행 버튼 제공
"""

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QObject, Signal, QThread, Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QWidget,
)

from utils.theme import C_BG_MAIN, C_HIGHLIGHT, C_SUCCESS, C_ERROR, C_TEXT, C_BORDER

ROOT_DIR     = Path(__file__).parent.parent
REMOTION_DIR = ROOT_DIR / "Project_templete" / "remotion"

# Windows: 콘솔 창 숨김 플래그
_HIDDEN = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}


# ──────────────────────────────────────────────
# Worker
# ──────────────────────────────────────────────

class HealthCheckWorker(QObject):
    """백그라운드 환경 체크 워커 (QThread에 move)"""

    # (ok, message) dict: key = "node" | "ffmpeg" | "remotion"
    check_done  = Signal(dict)
    npm_done    = Signal(bool, str)   # (success, message)

    TOOLS: dict[str, tuple[list[str], str]] = {
        "node":    (["node", "--version"],          "Node.js"),
        "ffmpeg":  (["ffmpeg", "-version"],         "FFmpeg"),
        "remotion":(["npx", "remotion", "--version"], "Remotion (npx)"),
    }

    def run_check(self):
        results: dict[str, tuple[bool, str]] = {}
        for key, (cmd, label) in self.TOOLS.items():
            try:
                r = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=20,
                    **_HIDDEN,
                )
                if r.returncode == 0:
                    msg = (r.stdout.strip() or r.stderr.strip())[:80]
                    results[key] = (True, msg or "OK")
                else:
                    results[key] = (False, (r.stderr.strip() or r.stdout.strip())[:80])
            except FileNotFoundError:
                results[key] = (False, f"{label} 실행 파일을 찾을 수 없습니다")
            except subprocess.TimeoutExpired:
                results[key] = (False, "시간 초과 (20s)")
            except Exception as e:
                results[key] = (False, str(e)[:80])

        self.check_done.emit(results)

    def run_npm_install(self):
        try:
            proc = subprocess.run(
                ["npm", "install"],
                cwd=str(REMOTION_DIR),
                capture_output=True, text=True, timeout=300,
                **_HIDDEN,
            )
            if proc.returncode == 0:
                self.npm_done.emit(True, "node_modules 설치가 완료되었습니다!")
            else:
                self.npm_done.emit(False, f"npm install 실패:\n{proc.stderr[-400:]}")
        except subprocess.TimeoutExpired:
            self.npm_done.emit(False, "npm install 시간 초과 (5분). 네트워크 상태를 확인하세요.")
        except Exception as e:
            self.npm_done.emit(False, str(e))


# ──────────────────────────────────────────────
# Dialog
# ──────────────────────────────────────────────

class HealthCheckDialog(QDialog):
    """
    앱 시작 시 1회 실행되는 환경 진단 다이얼로그.

    표시 항목:
      - Node.js / FFmpeg / Remotion(npx) 설치 여부 + 버전
      - node_modules 존재 여부 (없으면 npm install 버튼 표시)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("환경 진단 — Vivid Health Check")
        self.setMinimumWidth(540)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setStyleSheet(
            f"QDialog {{ background:{C_BG_MAIN}; color:{C_TEXT}; }}"
            f"QLabel  {{ color:{C_TEXT}; }}"
        )

        # 워커 / 스레드
        self._worker       = HealthCheckWorker()
        self._thread       = QThread(self)
        self._npm_thread: QThread | None = None
        self._npm_worker:  HealthCheckWorker | None = None

        self._worker.moveToThread(self._thread)
        self._worker.check_done.connect(self._on_check_done)
        self._thread.started.connect(self._worker.run_check)

        # UI 레퍼런스
        self._row_labels:  dict[str, QLabel] = {}
        self._nm_status:   QLabel
        self._npm_btn:     QPushButton
        self._close_btn:   QPushButton

        self._build_ui()
        self._thread.start()

    # ── UI ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 22)
        layout.setSpacing(12)

        # 제목
        title = QLabel("🔍  Vivid 환경 자동 진단")
        title.setStyleSheet(
            f"color:{C_HIGHLIGHT}; font-size:15px; font-weight:bold;"
        )
        layout.addWidget(title)

        sub = QLabel("아래 항목이 모두 ✅ 이어야 정상 작동합니다.")
        sub.setStyleSheet("color:#888888; font-size:11px;")
        layout.addWidget(sub)

        layout.addWidget(self._divider())

        # 도구별 상태 행
        tool_rows = [
            ("node",     "Node.js"),
            ("ffmpeg",   "FFmpeg"),
            ("remotion", "Remotion (npx)"),
        ]
        for key, label in tool_rows:
            row = QHBoxLayout()
            name_lbl = QLabel(f"  {label}")
            name_lbl.setFixedWidth(200)
            name_lbl.setStyleSheet("font-size:12px;")
            status_lbl = QLabel("⏳ 확인 중...")
            status_lbl.setStyleSheet("color:#888888; font-size:12px;")
            row.addWidget(name_lbl)
            row.addWidget(status_lbl)
            row.addStretch()
            layout.addLayout(row)
            self._row_labels[key] = status_lbl

        layout.addWidget(self._divider())

        # node_modules 행
        nm_row = QHBoxLayout()
        nm_name = QLabel("  node_modules (Remotion 의존성)")
        nm_name.setFixedWidth(230)
        nm_name.setStyleSheet("font-size:12px;")
        self._nm_status = QLabel("⏳ 확인 중...")
        self._nm_status.setStyleSheet("color:#888888; font-size:12px;")
        nm_row.addWidget(nm_name)
        nm_row.addWidget(self._nm_status)
        nm_row.addStretch()

        self._npm_btn = QPushButton("📦  npm install 실행")
        self._npm_btn.setVisible(False)
        self._npm_btn.setFixedWidth(160)
        self._npm_btn.setStyleSheet(
            f"background:{C_HIGHLIGHT}; color:#000; font-weight:bold;"
            "border-radius:4px; padding:4px 8px;"
        )
        self._npm_btn.clicked.connect(self._on_npm_click)
        nm_row.addWidget(self._npm_btn)
        layout.addLayout(nm_row)

        layout.addWidget(self._divider())

        # 닫기 버튼
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._close_btn = QPushButton("확인 후 시작")
        self._close_btn.setFixedWidth(110)
        self._close_btn.setDefault(True)
        self._close_btn.clicked.connect(self.accept)
        btn_row.addWidget(self._close_btn)
        layout.addLayout(btn_row)

    @staticmethod
    def _divider() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color:{C_BORDER}; margin:2px 0;")
        return line

    # ── 콜백 ───────────────────────────────────────────────────────────

    def _on_check_done(self, results: dict):
        self._thread.quit()

        for key, (ok, msg) in results.items():
            lbl = self._row_labels.get(key)
            if lbl is None:
                continue
            if ok:
                lbl.setText(f"✅  {msg}")
                lbl.setStyleSheet(f"color:{C_SUCCESS}; font-size:11px;")
            else:
                lbl.setText(f"❌  {msg}")
                lbl.setStyleSheet(f"color:{C_ERROR}; font-size:11px;")

        # node_modules 체크 (동기, 파일 존재 여부)
        nm_path = REMOTION_DIR / "node_modules"
        if nm_path.exists() and nm_path.is_dir():
            self._nm_status.setText("✅  설치됨")
            self._nm_status.setStyleSheet(f"color:{C_SUCCESS}; font-size:11px;")
        else:
            self._nm_status.setText("⚠️  미설치 — Remotion 실행 전 npm install이 필요합니다")
            self._nm_status.setStyleSheet(f"color:{C_HIGHLIGHT}; font-size:11px;")
            self._npm_btn.setVisible(True)

    def _on_npm_click(self):
        self._npm_btn.setEnabled(False)
        self._npm_btn.setText("⏳ 설치 중...")
        self._nm_status.setText("npm install 실행 중... (수 분 소요될 수 있습니다)")
        self._nm_status.setStyleSheet(f"color:{C_HIGHLIGHT}; font-size:11px;")

        self._npm_worker = HealthCheckWorker()
        self._npm_thread = QThread(self)
        self._npm_worker.moveToThread(self._npm_thread)
        self._npm_worker.npm_done.connect(self._on_npm_done)
        self._npm_thread.started.connect(self._npm_worker.run_npm_install)
        self._npm_thread.start()

    def _on_npm_done(self, success: bool, msg: str):
        if self._npm_thread:
            self._npm_thread.quit()

        if success:
            self._nm_status.setText(f"✅  {msg}")
            self._nm_status.setStyleSheet(f"color:{C_SUCCESS}; font-size:11px;")
            self._npm_btn.setVisible(False)
        else:
            self._nm_status.setText(f"❌  {msg[:120]}")
            self._nm_status.setStyleSheet(f"color:{C_ERROR}; font-size:11px;")
            self._npm_btn.setEnabled(True)
            self._npm_btn.setText("📦  npm install 재시도")

    # ── 정리 ────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        for t in (self._thread, self._npm_thread):
            if t and t.isRunning():
                t.quit()
                t.wait(1500)
        super().closeEvent(event)
