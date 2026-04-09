"""
utils/theme.py
경로 상수 · 테마 컬러 · 전역 QSS (ui_ux_spec.md 기준)
"""

from pathlib import Path

# ──────────────────────────────────────────────
# 경로 상수
# ──────────────────────────────────────────────
ROOT_DIR          = Path(__file__).parent.parent          # Vivid_Workspace/
TEMPLATE_DIR      = ROOT_DIR / "Project_templete"
SHARED_ASSETS_DIR = ROOT_DIR / "shared_assets"           # 채널 공용 에셋 (bumper 등)
SHARED_FX_DIR     = SHARED_ASSETS_DIR / "shared_fx"      # 글로벌 FX 라이브러리 (심볼릭 링크 대상)

# 앱 시작 시 shared_fx 폴더가 없으면 자동 생성
SHARED_FX_DIR.mkdir(parents=True, exist_ok=True)

# ──────────────────────────────────────────────
# 테마 컬러 (ui_ux_spec.md)
# ──────────────────────────────────────────────
C_BG_MAIN   = "#121212"   # 메인 배경 (60%)
C_BG_SUB    = "#1E1E1E"   # 서브 배경 (패널)
C_BG_INPUT  = "#2A2A2A"   # 입력창 배경
C_ACCENT    = "#E02020"   # 강조 레드 (10%)
C_TEXT      = "#FFFFFF"   # 기본 텍스트
C_SUCCESS   = "#4CAF50"   # 성공 녹색
C_ERROR     = "#E02020"   # 에러 레드
C_HIGHLIGHT = "#FDE061"   # 골드 하이라이트
C_BORDER    = "#333333"   # 경계선
C_BTN_HOVER = "#2E2E2E"   # 버튼 호버

# ──────────────────────────────────────────────
# 전역 QSS 스타일시트
# ──────────────────────────────────────────────
GLOBAL_QSS = f"""
/* ── 전역 기본 ── */
QWidget {{
    background-color: {C_BG_MAIN};
    color: {C_TEXT};
    font-family: "Malgun Gothic", "Apple SD Gothic Neo", sans-serif;
    font-size: 13px;
}}

/* ── 메인 창 ── */
QMainWindow {{
    background-color: {C_BG_MAIN};
}}

/* ── 단계 제목 ── */
QLabel#StepTitle {{
    color: {C_HIGHLIGHT};
    font-size: 20px;
    font-weight: bold;
    padding: 12px 0 8px 0;
    border-bottom: 2px solid {C_ACCENT};
    margin-bottom: 8px;
}}

/* ── 상태창 ── */
QTextEdit#StatusBox {{
    background-color: {C_BG_SUB};
    color: {C_TEXT};
    border: 1px solid {C_BORDER};
    border-radius: 6px;
    padding: 10px;
    font-size: 13px;
    line-height: 1.5;
}}

/* ── 일반 입력창 ── */
QLineEdit {{
    background-color: {C_BG_INPUT};
    color: {C_TEXT};
    border: 1px solid {C_BORDER};
    border-radius: 6px;
    padding: 10px 12px;
    font-size: 14px;
    selection-background-color: {C_ACCENT};
}}
QLineEdit:focus {{
    border: 1px solid {C_HIGHLIGHT};
}}
QLineEdit::placeholder {{
    color: #666666;
}}

/* ── 기본 버튼 ── */
QPushButton {{
    background-color: {C_BG_INPUT};
    color: {C_TEXT};
    border: 1px solid {C_BORDER};
    border-radius: 6px;
    padding: 10px 20px;
    font-size: 13px;
    font-weight: bold;
    min-height: 36px;
}}
QPushButton:hover {{
    background-color: {C_BTN_HOVER};
    border-color: {C_HIGHLIGHT};
    color: {C_HIGHLIGHT};
}}
QPushButton:pressed {{
    background-color: #111111;
}}
QPushButton:disabled {{
    background-color: #1A1A1A;
    color: #555555;
    border-color: #2A2A2A;
}}

/* ── NEXT 버튼 (강조) ── */
QPushButton#NextBtn {{
    background-color: {C_ACCENT};
    color: {C_TEXT};
    border: none;
    border-radius: 6px;
    padding: 12px 36px;
    font-size: 14px;
    font-weight: bold;
    min-width: 120px;
}}
QPushButton#NextBtn:hover {{
    background-color: #FF3333;
    color: {C_TEXT};
    border: none;
}}
QPushButton#NextBtn:disabled {{
    background-color: #4A1010;
    color: #888888;
    border: none;
}}

/* ── Watchdog 토글 버튼 (활성) ── */
QPushButton#WatchdogActive {{
    background-color: #1A3A1A;
    color: {C_SUCCESS};
    border: 1px solid {C_SUCCESS};
    border-radius: 6px;
    padding: 10px 20px;
    font-size: 13px;
    font-weight: bold;
    min-height: 36px;
}}
QPushButton#WatchdogActive:hover {{
    background-color: #224422;
}}

/* ── 구분선 ── */
QFrame#Divider {{
    background-color: {C_BORDER};
    max-height: 1px;
}}

/* ── 드롭존 (기본 상태) ── */
QWidget#DropZone {{
    background-color: #181818;
    border: 2px dashed {C_BORDER};
    border-radius: 8px;
}}

/* ── 드롭존 레이블 ── */
QLabel#DropZoneLabel {{
    color: #555555;
    font-size: 13px;
    background: transparent;
    border: none;
}}
"""
