"""
steps/step4.py
4단계 — 영상 기획안 및 조립

① 기획안 업로드  : remotion_plan.json 파싱 + Custom FX 동적 생성 + 역주입
② Remotion 미리보기 : npx remotion studio (브라우저 자동 오픈)
③ Remotion 투명 렌더링 : Diff-Check 기반 부분 렌더 (QThread 비동기)
                         렌더 완료 시 소요시간/렌더 수/캐시 수 골드 리포트 출력
④ 최종 Vrew 생성 : 원본.vrew + webm → 최종_vN.vrew (QThread 비동기)
⑤ Vrew 열기     : subprocess로 Vrew 프로그램 실행
⑥ FX 카탈로그 보기 : 갤러리 팝업 (★ 즐겨찾기 / 메모리 캐시)
⑦ 기획 지시문 복사 : Gemini API → 슬라이드별 요약 → 클립보드 복사

Vrew 구조 (실물 분석):
  .vrew = ZIP(project.json + media/)
  project.json: files[] / transcript.clips[] / props.tracks{} / props.assets{}
"""

import json
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

from PySide6.QtCore import Qt, QObject, QThread, QTimer, QUrl, Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QStackedWidget, QFileDialog,
    QProgressBar, QApplication, QColorDialog,
    QDialog, QTextEdit, QFrame, QScrollArea, QTabWidget,
    QDoubleSpinBox, QSpinBox, QSlider, QLineEdit, QStyle,
    QSizePolicy,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEngineScript

from utils.theme import C_HIGHLIGHT, C_SUCCESS, C_ERROR, C_BG_INPUT, C_BORDER, C_TEXT, SHARED_FX_DIR
from utils.widgets import (
    make_title, make_divider, make_status_box,
    StatusLogger, DropZone,
)
from utils.backend_ext import generate_compositions, save_render_cache
from utils.fx_gallery import FxGalleryDialog
from utils.step4_workers import (
    ROOT_DIR, CATALOG_PATH, CONFIG_PATH, _NPX, _NPM,
    parse_plan_json, detect_custom_fx,
    RenderWorker, VrewWorker, GeminiWorker, SemanticMatchWorker,
    N8nLaunchWorker,
)


import re as _re

# ── HyperFrames 편집 UI 상수 ──────────────────────────────────────────────
_HF_PREVIEW_W = 854
_HF_PREVIEW_H = 480
_HF_ZOOM      = _HF_PREVIEW_W / 1920   # ≈ 0.4448

_EDITOR_JS = r"""
(function () {
    // ── Step 1: CSS class for editor visibility ───────────────────────────────────
    // Using a CSS class (not inline !important) avoids touching GSAP's own
    // inline-style cache.  Removing the class on play() leaves GSAP state intact.
    var _st = document.createElement('style');
    _st.innerHTML = [
        '.hf-editor-visible { opacity: 1 !important; visibility: visible !important; }',
        '.hf-rh {',
        '  position: fixed; width: 20px; height: 20px;',
        '  background: #FFD700; border: 2px solid #333; border-radius: 3px;',
        '  z-index: 99999; transform: translate(-50%, -50%);',
        '  box-sizing: border-box; pointer-events: all;',
        '}'
    ].join('\n');
    document.head.appendChild(_st);

    // ── Step 2: Locate the actual child timeline, not gsap.globalTimeline ────────
    // `const tl` in the slide's inline <script> lives in that script's lexical scope
    // and is NOT reachable via typeof/window from runJavaScript injection.
    // gsap.globalTimeline also doesn't work: its clock starts at page-load, so
    // seek(t) would not align with the child tl's local t=0.
    // Solution: extract the first direct-child Timeline from globalTimeline.
    function _getMainTl() {
        if (typeof gsap === 'undefined') return null;
        var direct = gsap.globalTimeline.getChildren(false, false, true);
        if (direct.length) return direct[0];
        var all = gsap.globalTimeline.getChildren(true, false, true);
        return all.length ? all[0] : null;
    }

    var _mainTl = _getMainTl();
    if (_mainTl) { _mainTl.pause(); window.__timelines = { main: _mainTl }; }

    function _forceVisible() {
        var c = document.getElementById('composition');
        if (!c) { setTimeout(_forceVisible, 30); return; }
        Array.from(c.children).forEach(function (el) { el.classList.add('hf-editor-visible'); });
    }
    _forceVisible();

    var _handles = [], _resizing = false, _resizeDir = null;
    var _resizeStartX, _resizeStartY, _resizeStartFontSize;

    function _removeHandles() {
        _handles.forEach(function (h) { if (h.parentNode) h.parentNode.removeChild(h); });
        _handles = [];
    }
    function _addHandles(el) {
        _removeHandles();
        if (!el.classList.contains('text-common')) return;
        var rect = el.getBoundingClientRect();
        [['nw', rect.left,  rect.top   ],
         ['ne', rect.right, rect.top   ],
         ['sw', rect.left,  rect.bottom],
         ['se', rect.right, rect.bottom]].forEach(function (c) {
            var h = document.createElement('div');
            h.className = 'hf-rh';
            h.style.left   = c[1] + 'px';
            h.style.top    = c[2] + 'px';
            h.style.cursor = c[0] + '-resize';
            (function (dir) {
                h.addEventListener('mousedown', function (e) {
                    e.stopPropagation(); e.preventDefault();
                    _resizing = true; _resizeDir = dir;
                    _resizeStartX = e.clientX; _resizeStartY = e.clientY;
                    _resizeStartFontSize = parseFloat(window.getComputedStyle(el).fontSize) || 80;
                });
            })(c[0]);
            document.body.appendChild(h);
            _handles.push(h);
        });
    }

    function init() {
        if (!window.QWebChannel || !window.qt || !window.qt.webChannelTransport) {
            setTimeout(init, 50); return;
        }
        new QWebChannel(window.qt.webChannelTransport, function (channel) {
            var bridge = channel.objects.bridge;
            var sel = null, dragging = false;
            var dragSX, dragSY, elemSX, elemSY;

            // Re-acquire in case timeline wasn't ready at outer init time
            if (!window.__timelines) {
                var tl2 = _getMainTl();
                if (tl2) { tl2.pause(); window.__timelines = { main: tl2 }; }
            }

            function getSel(el) {
                var classes = Array.from(el.classList).filter(function (c) {
                    return c !== 'text-common' && c !== 'hf-editor-visible';
                });
                return classes.length ? '.' + classes[0] : (el.id ? '#' + el.id : el.tagName.toLowerCase());
            }
            function getProps(el) {
                var cs = window.getComputedStyle(el);
                return JSON.stringify({
                    x: el.offsetLeft - 960, y: el.offsetTop - 540,
                    fontSize: cs.fontSize, color: cs.color,
                    text: el.innerText || ''
                });
            }
            function choose(el) {
                if (sel && sel !== el) sel.style.outline = '';
                sel = el;
                el.style.outline = '2px solid #FFD700';
                el.style.outlineOffset = '4px';
                _addHandles(el);
                bridge.on_select(getSel(el), getProps(el));
            }
            function clear() {
                if (sel) { sel.style.outline = ''; sel = null; }
                _removeHandles();
            }

            var comp = document.getElementById('composition');
            if (comp) {
                Array.from(comp.children).forEach(function (child) {
                    child.style.cursor = 'move';
                    child.addEventListener('mousedown', function (e) {
                        if (e.button !== 0 || _resizing) return;
                        dragging = true;
                        dragSX = e.clientX; dragSY = e.clientY;
                        elemSX = e.currentTarget.offsetLeft;
                        elemSY = e.currentTarget.offsetTop;
                        choose(e.currentTarget);
                        e.preventDefault();
                    });
                    child.addEventListener('click', function (e) { e.stopPropagation(); });
                });
                comp.addEventListener('click', function (e) { if (e.target === comp) clear(); });
            }

            document.addEventListener('mousemove', function (e) {
                if (dragging && sel && !_resizing) {
                    // setZoomFactor maps Qt widget px to CSS px internally — no zoom division
                    var newLeft = elemSX + (e.clientX - dragSX);
                    var newTop  = elemSY + (e.clientY - dragSY);
                    sel.style.left = 'calc(50% + ' + (newLeft - 960) + 'px)';
                    sel.style.top  = 'calc(50% + ' + (newTop  - 540) + 'px)';
                    _removeHandles(); _addHandles(sel);
                }
                if (_resizing && sel) {
                    var dx = e.clientX - _resizeStartX;
                    var dy = e.clientY - _resizeStartY;
                    var signX = (_resizeDir === 'ne' || _resizeDir === 'se') ? 1 : -1;
                    var signY = (_resizeDir === 'sw' || _resizeDir === 'se') ? 1 : -1;
                    var delta = Math.abs(dx) >= Math.abs(dy) ? dx * signX : dy * signY;
                    sel.style.fontSize = Math.max(12, _resizeStartFontSize + delta * 0.5) + 'px';
                    _removeHandles(); _addHandles(sel);
                }
            });
            document.addEventListener('mouseup', function (e) {
                if (dragging && !_resizing) {
                    dragging = false;
                    if (sel) {
                        bridge.on_move(getSel(sel), sel.offsetLeft - 960, sel.offsetTop - 540);
                        _removeHandles(); _addHandles(sel);
                    }
                }
                if (_resizing) {
                    _resizing = false;
                    if (sel) {
                        var newFs = window.getComputedStyle(sel).fontSize;
                        bridge.on_prop_change(getSel(sel), 'fontSize', newFs);
                        _removeHandles(); _addHandles(sel);
                    }
                }
            });

            window.__editor = {
                scrub: function (t) {
                    Object.values(window.__timelines || {}).forEach(function (tl) {
                        tl.seek(t); tl.pause();
                    });
                    _forceVisible();
                },
                play: function () {
                    // Remove class — GSAP's own inline-style state is preserved intact
                    var c = document.getElementById('composition');
                    if (c) Array.from(c.children).forEach(function (el) {
                        el.classList.remove('hf-editor-visible');
                    });
                    Object.values(window.__timelines || {}).forEach(function (tl) {
                        if (tl.progress() >= 0.99) tl.restart();
                        else tl.play();
                    });
                },
                pause: function () {
                    Object.values(window.__timelines || {}).forEach(function (tl) { tl.pause(); });
                    _forceVisible();
                },
                getCurrentTime: function () {
                    var tls = Object.values(window.__timelines || {});
                    return tls.length ? tls[0].time() : 0;
                },
                getDuration: function () {
                    var comp = document.getElementById('composition');
                    if (comp && comp.dataset.duration) return parseFloat(comp.dataset.duration);
                    var tls = Object.values(window.__timelines || {});
                    return tls.length ? tls[0].duration() : 10;
                },
                setProperty: function (selector, prop, value) {
                    var el = document.querySelector(selector);
                    if (!el) return;
                    if (prop === 'x') el.style.left = 'calc(50% + ' + value + 'px)';
                    else if (prop === 'y') el.style.top = 'calc(50% + ' + value + 'px)';
                    else if (prop === 'fontSize') el.style.fontSize = (typeof value === 'number') ? value + 'px' : value;
                    else if (prop === 'color') el.style.color = value;
                    else if (prop === 'text') el.innerText = value;
                }
            };

            bridge.on_ready(window.__editor.getDuration());
        });
    }
    init();
})();
"""


def _lint_hf_json(data: object) -> tuple[bool, str, str]:
    """
    hyperframes_compositions.json 구조 검증 (E-18).
    Returns: (ok, severity, detail_message)
    severity: "" | "light" | "severe"
    """
    if not isinstance(data, dict) or not data:
        return False, "severe", "딕셔너리 형식이 아니거나 비어 있습니다."

    total     = len(data)
    bad_keys  = [k for k in data if not _re.match(r"^slide_\d+$", k)]
    bad_html  = [
        k for k, v in data.items()
        if not isinstance(v, str) or "<!DOCTYPE" not in v[:200]
    ]

    if len(bad_html) == total:
        sample = ", ".join(bad_html[:3])
        return False, "severe", f"모든 슬라이드 HTML이 유효하지 않습니다. Opal에서 재생성해주세요.\n오류 슬라이드: {sample}"

    issues: list[str] = []
    if bad_keys:
        issues.append(f"키 형식 오류 ({len(bad_keys)}개): {', '.join(bad_keys[:3])}")
    if bad_html:
        issues.append(f"HTML 누락 ({len(bad_html)}개): {', '.join(bad_html[:3])}")

    if issues:
        return False, "light", "\n".join(issues)

    return True, "", f"슬라이드 {total}장 모두 정상"


def _find_free_port(start: int, end: int) -> int:
    import socket
    for p in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('127.0.0.1', p))
                return p
            except OSError:
                continue
    return start


# ══════════════════════════════════════════════
# PreflightDialog  — Custom FX 사전 검수 팝업
# ══════════════════════════════════════════════

class PreflightDialog(QDialog):
    """
    렌더링 직전 Custom FX 항목을 일괄 검출하여 표시하는 Human-in-the-loop 팝업.

    흐름:
      1) _on_render_click() 이 effects[] 에서 type=Custom 항목을 추출
      2) Custom 항목이 있으면 이 다이얼로그를 exec() (모달)
      3) 파이썬이 통합 지시문 프롬프트를 자동 조합하여 QTextEdit에 표시
      4) 사용자가 프롬프트를 복사 → 터미널 Claude Code 에 전달 → 코딩 완료
      5) '코딩 완료 (렌더링 계속)' 클릭 → accept() → 렌더링 재개
    """

    def __init__(self, custom_effects: list[dict], parent=None):
        super().__init__(parent)
        self._custom_effects = custom_effects
        self._prompt_text    = self._build_prompt(custom_effects)

        self.setWindowTitle("⚙️  Custom FX 사전 검수 (Pre-flight Check)")
        self.setMinimumSize(700, 440)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setStyleSheet(
            f"QDialog {{ background:{C_BG_INPUT}; color:{C_TEXT}; }}"
            f"QLabel  {{ color:{C_TEXT}; }}"
        )
        self._build_ui()

    # ── 프롬프트 자동 조합 ──────────────────────────────────────────────

    @staticmethod
    def _build_prompt(effects: list[dict]) -> str:
        lines = [
            "기획안에 포함된 아래 Custom 효과들을 글로벌 공유 폴더(shared_assets/shared_fx/)에 "
            "TSX 컴포넌트로 코딩해 줘. 이 효과들은 모든 프로젝트가 심볼릭 링크로 공유하는 공용 자산이야.\n\n"
            "* 다른 프로젝트에서도 범용적으로 쓸 수 있게 commonProps와 specificProps의 기본값을 정교하게 세팅해 줘.\n"
            "* 코딩 완료 후 **루트의 fx_catalog.txt**에 카탈로그 정보를 최신화해 줘.\n"
            "* (참고) 현재 프로젝트의 src/components/fx/는 글로벌 폴더와 심볼릭 링크로 연결되어 있으니 경로 참조에 유의해.\n",
        ]
        for eff in effects:
            eid  = eff.get("id", "(id없음)")
            desc = eff.get("description", "(설명없음)")
            lines.append(f"- [id: {eid}] 연출 설명: {desc}")
        return "\n".join(lines)

    # ── UI 구성 ─────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        # 경고 배너
        banner = QLabel(
            f"🚧  새로운 Custom 시각 효과 코딩이 필요합니다  "
            f"({len(self._custom_effects)}개 항목)"
        )
        banner.setStyleSheet(
            f"background:{C_HIGHLIGHT}; color:#000000; font-size:13px;"
            "font-weight:bold; padding:8px 12px; border-radius:4px;"
        )
        banner.setWordWrap(True)
        root.addWidget(banner)

        # 안내문
        guide = QLabel(
            "아래 프롬프트를 복사하여 터미널의 Claude Code에 전달하세요.\n"
            "Claude가 TSX 컴포넌트 코딩을 완료하면 '코딩 완료' 버튼을 클릭하여 렌더링을 계속하세요."
        )
        guide.setStyleSheet("color:#AAAAAA; font-size:11px;")
        guide.setWordWrap(True)
        root.addWidget(guide)

        # 항목 목록 요약 (골드)
        items_label = QLabel(
            "  •  " + "\n  •  ".join(
                f"[{e.get('id','?')}]  {e.get('description','')[:60]}"
                for e in self._custom_effects
            )
        )
        items_label.setStyleSheet(
            f"color:{C_HIGHLIGHT}; font-size:11px;"
            f"background:#1A1A1A; border:1px solid {C_BORDER};"
            "border-radius:4px; padding:8px 12px;"
        )
        items_label.setWordWrap(True)
        root.addWidget(items_label)

        # 구분선
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet(f"color:{C_BORDER};")
        root.addWidget(div)

        # 통합 지시문 프롬프트 텍스트 박스
        prompt_label = QLabel("📋  Claude Code 전달용 통합 지시문 프롬프트")
        prompt_label.setStyleSheet(
            f"color:{C_TEXT}; font-size:11px; font-weight:bold;"
        )
        root.addWidget(prompt_label)

        self._prompt_box = QTextEdit()
        self._prompt_box.setReadOnly(True)
        self._prompt_box.setPlainText(self._prompt_text)
        self._prompt_box.setStyleSheet(
            f"background:#111111; color:#DDDDDD; font-family:Consolas,monospace;"
            f"font-size:11px; border:1px solid {C_BORDER}; border-radius:4px;"
            "padding:8px;"
        )
        self._prompt_box.setFixedHeight(140)
        root.addWidget(self._prompt_box)

        # 버튼 행
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        copy_btn = QPushButton("📋  프롬프트 복사")
        copy_btn.setStyleSheet(
            f"background:#2A2A2A; color:{C_TEXT}; border:1px solid {C_BORDER};"
            "padding:6px 16px; border-radius:4px;"
        )
        copy_btn.clicked.connect(self._on_copy)
        btn_row.addWidget(copy_btn)

        btn_row.addStretch()

        cancel_btn = QPushButton("취소")
        cancel_btn.setFixedWidth(70)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        confirm_btn = QPushButton("✅  코딩 완료 (렌더링 계속)")
        confirm_btn.setStyleSheet(
            f"background:{C_SUCCESS}; color:#000000; font-weight:bold;"
            "padding:6px 20px; border-radius:4px;"
        )
        confirm_btn.setDefault(True)
        confirm_btn.clicked.connect(self._on_confirm)
        btn_row.addWidget(confirm_btn)

        root.addLayout(btn_row)

    # ── 핸들러 ──────────────────────────────────────────────────────────

    def _on_copy(self):
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(self._prompt_text)
            # 복사 버튼 일시적 피드백
            sender = self.sender()
            if isinstance(sender, QPushButton):
                sender.setText("✔  복사됨!")
                QTimer.singleShot(1800, lambda: sender.setText("📋  프롬프트 복사"))

    def _on_confirm(self):
        self.accept()


# ══════════════════════════════════════════════
# HfBridge  — QWebChannel JS↔Python 브리지
# ══════════════════════════════════════════════

class HfBridge(QObject):
    element_selected   = Signal(str, str)           # selector, props_json
    element_moved      = Signal(str, float, float)  # selector, x, y
    editor_ready       = Signal(float)              # duration
    element_prop_changed = Signal(str, str, str)    # selector, prop, value

    @Slot(str, str)
    def on_select(self, selector: str, props_json: str):
        self.element_selected.emit(selector, props_json)

    @Slot(str, float, float)
    def on_move(self, selector: str, x: float, y: float):
        self.element_moved.emit(selector, x, y)

    @Slot(float)
    def on_ready(self, duration: float):
        self.editor_ready.emit(duration)

    @Slot(str, str, str)
    def on_prop_change(self, selector: str, prop: str, value: str):
        self.element_prop_changed.emit(selector, prop, value)


# ══════════════════════════════════════════════
# HfEditorPanel  — 슬라이드 미리보기/편집 위젯
# ══════════════════════════════════════════════

class HfEditorPanel(QWidget):
    delta_changed = Signal(str, dict)   # slide_key, delta

    def __init__(self, parent=None):
        super().__init__(parent)
        self._slide_keys:  list[str] = []
        self._slide_idx:   int = 0
        self._comps_dir:   Path | None = None
        self._deltas:      dict[str, dict] = {}
        self._undo_stack:  list[tuple[str, dict]] = []
        self._redo_stack:  list[tuple[str, dict]] = []
        self._sel_selector: str | None = None
        self._duration:    float = 10.0
        self._build_ui()
        self._setup_channel()
        self._play_timer = QTimer(self)
        self._play_timer.setInterval(50)
        self._play_timer.timeout.connect(self._on_play_tick)

    # ── UI ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        # 슬라이드 네비게이션 바
        nav = QHBoxLayout()
        _style = self.style()
        self._prev_btn = QPushButton()
        self._prev_btn.setIcon(_style.standardIcon(QStyle.StandardPixmap.SP_ArrowLeft))
        self._prev_btn.setToolTip("이전 슬라이드")
        self._prev_btn.setFixedWidth(36)
        self._prev_btn.clicked.connect(self._prev_slide)
        self._slide_lbl = QLabel("슬라이드 없음")
        self._slide_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._slide_lbl.setStyleSheet("color:#aaa; font-size:12px;")
        self._next_btn = QPushButton()
        self._next_btn.setIcon(_style.standardIcon(QStyle.StandardPixmap.SP_ArrowRight))
        self._next_btn.setToolTip("다음 슬라이드")
        self._next_btn.setFixedWidth(36)
        self._next_btn.clicked.connect(self._next_slide)
        self._undo_btn = QPushButton()
        self._undo_btn.setIcon(_style.standardIcon(QStyle.StandardPixmap.SP_ArrowBack))
        self._undo_btn.setText("  되돌리기")
        self._undo_btn.setToolTip("Undo (되돌리기)")
        self._undo_btn.setEnabled(False)
        self._undo_btn.clicked.connect(self._undo)
        self._redo_btn = QPushButton()
        self._redo_btn.setIcon(_style.standardIcon(QStyle.StandardPixmap.SP_ArrowForward))
        self._redo_btn.setText("  다시하기")
        self._redo_btn.setToolTip("Redo (다시하기)")
        self._redo_btn.setEnabled(False)
        self._redo_btn.clicked.connect(self._redo)
        nav.addWidget(self._prev_btn)
        nav.addWidget(self._slide_lbl, 1)
        nav.addWidget(self._next_btn)
        nav.addSpacing(12)
        nav.addWidget(self._undo_btn)
        nav.addWidget(self._redo_btn)
        root.addLayout(nav)

        # 메인 영역: WebView + 속성 패널
        main = QHBoxLayout()
        main.setSpacing(8)

        self._view = QWebEngineView()
        self._view.setFixedSize(_HF_PREVIEW_W, _HF_PREVIEW_H)
        main.addWidget(self._view)

        # 속성 패널
        prop = QWidget()
        prop.setFixedWidth(190)
        pl = QVBoxLayout(prop)
        pl.setContentsMargins(6, 0, 0, 0)
        pl.setSpacing(4)

        self._sel_lbl = QLabel("요소를 클릭하여 선택")
        self._sel_lbl.setStyleSheet("color:#888; font-size:11px;")
        self._sel_lbl.setWordWrap(True)
        pl.addWidget(self._sel_lbl)

        def _lbl(t):
            l = QLabel(t)
            l.setStyleSheet("color:#aaa; font-size:11px; margin-top:4px;")
            return l

        pl.addWidget(_lbl("X (px, 중앙기준)"))
        self._prop_x = QDoubleSpinBox()
        self._prop_x.setRange(-960, 960); self._prop_x.setDecimals(0)
        self._prop_x.valueChanged.connect(lambda v: self._set_prop("x", v))
        pl.addWidget(self._prop_x)

        pl.addWidget(_lbl("Y (px, 중앙기준)"))
        self._prop_y = QDoubleSpinBox()
        self._prop_y.setRange(-540, 540); self._prop_y.setDecimals(0)
        self._prop_y.valueChanged.connect(lambda v: self._set_prop("y", v))
        pl.addWidget(self._prop_y)

        pl.addWidget(_lbl("Font Size"))
        self._prop_fs = QSpinBox()
        self._prop_fs.setRange(8, 300); self._prop_fs.setSuffix(" px")
        self._prop_fs.valueChanged.connect(lambda v: self._set_prop("fontSize", f"{v}px"))
        pl.addWidget(self._prop_fs)

        pl.addWidget(_lbl("Color"))
        self._prop_color_btn = QPushButton("■  색상 선택")
        self._prop_color_btn.clicked.connect(self._pick_color)
        pl.addWidget(self._prop_color_btn)

        pl.addWidget(_lbl("텍스트"))
        self._prop_text = QLineEdit()
        self._prop_text.editingFinished.connect(
            lambda: self._set_prop("text", self._prop_text.text())
        )
        pl.addWidget(self._prop_text)

        pl.addWidget(_lbl("등장 시각 (초)"))
        self._prop_gsap = QDoubleSpinBox()
        self._prop_gsap.setRange(0, 300); self._prop_gsap.setDecimals(2)
        self._prop_gsap.setSingleStep(0.1)
        self._prop_gsap.valueChanged.connect(lambda v: self._set_prop("gsap_start", v))
        pl.addWidget(self._prop_gsap)

        pl.addStretch()
        self._set_props_enabled(False)
        main.addWidget(prop)
        root.addLayout(main)

        # 타임라인 스크러버
        scrub = QHBoxLayout()
        self._play_btn = QPushButton()
        self._play_btn.setIcon(_style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self._play_btn.setToolTip("재생 / 일시정지")
        self._play_btn.setFixedWidth(36)
        self._play_btn.setCheckable(True)
        self._play_btn.clicked.connect(self._toggle_play)
        self._scrubber = QSlider(Qt.Orientation.Horizontal)
        self._scrubber.setRange(0, 1000)
        self._scrubber.setValue(0)
        self._scrubber.sliderMoved.connect(self._on_scrub)
        self._time_lbl = QLabel("0.0 s")
        self._time_lbl.setFixedWidth(52)
        self._time_lbl.setStyleSheet("color:#888; font-size:11px;")
        scrub.addWidget(self._play_btn)
        scrub.addWidget(self._scrubber, 1)
        scrub.addWidget(self._time_lbl)
        root.addLayout(scrub)

    def _setup_channel(self):
        self._bridge  = HfBridge()
        self._channel = QWebChannel(self._view.page())
        self._channel.registerObject("bridge", self._bridge)
        self._view.page().setWebChannel(self._channel)

        # qwebchannel.js를 DocumentCreation 시점에 자동 주입
        qwc = QWebEngineScript()
        qwc.setName("qwebchannel-js")
        qwc.setSourceUrl(QUrl("qrc:///qtwebchannel/qwebchannel.js"))
        qwc.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        qwc.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        self._view.page().scripts().insert(qwc)

        self._bridge.element_selected.connect(self._on_element_selected)
        self._bridge.element_moved.connect(self._on_element_moved)
        self._bridge.editor_ready.connect(self._on_editor_ready)
        self._bridge.element_prop_changed.connect(self._on_element_prop_changed)
        self._view.loadFinished.connect(self._on_load_finished)
        self._view.page().setZoomFactor(_HF_ZOOM)

    # ── Public API ────────────────────────────────────────────────────────

    def load_compositions(self, comps_dir: Path, slide_keys: list[str]):
        self._comps_dir  = comps_dir
        self._slide_keys = slide_keys
        self._slide_idx  = 0
        self._deltas     = {}
        self._undo_stack = []
        self._redo_stack = []
        self._undo_btn.setEnabled(False)
        self._redo_btn.setEnabled(False)
        self._load_slide()

    def unload(self):
        self._slide_keys   = []
        self._slide_idx    = 0
        self._comps_dir    = None
        self._deltas       = {}
        self._undo_stack   = []
        self._redo_stack   = []
        self._sel_selector = None
        self._undo_btn.setEnabled(False)
        self._redo_btn.setEnabled(False)
        self._slide_lbl.setText("슬라이드 없음")
        self._sel_lbl.setText("요소를 클릭하여 선택")
        self._set_props_enabled(False)
        self._scrubber.setValue(0)
        self._time_lbl.setText("0.0 s")
        self._play_timer.stop()
        self._view.setHtml("")

    # ── 슬라이드 네비게이션 ───────────────────────────────────────────────

    def _load_slide(self):
        if not self._slide_keys or not self._comps_dir:
            return
        key   = self._current_key()
        n     = self._slide_idx + 1
        total = len(self._slide_keys)
        self._slide_lbl.setText(f"Slide {n:02d} / {total:02d}  ({key})")
        self._sel_selector = None
        self._sel_lbl.setText("요소를 클릭하여 선택")
        self._set_props_enabled(False)
        self._scrubber.setValue(0)
        self._time_lbl.setText("0.0 s")
        self._play_timer.stop()
        if self._play_btn.isChecked():
            self._play_btn.setChecked(False)
            self._play_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))

        html_path = self._comps_dir / f"{key}.html"
        if html_path.exists():
            self._view.load(QUrl.fromLocalFile(str(html_path)))

        if key not in self._deltas:
            delta_path = self._comps_dir / f"{key}_delta.json"
            if delta_path.exists():
                try:
                    self._deltas[key] = json.loads(delta_path.read_text(encoding="utf-8"))
                except Exception:
                    self._deltas[key] = {}
            else:
                self._deltas[key] = {}

    def _prev_slide(self):
        if self._slide_idx > 0:
            self._slide_idx -= 1
            self._load_slide()

    def _next_slide(self):
        if self._slide_idx < len(self._slide_keys) - 1:
            self._slide_idx += 1
            self._load_slide()

    # ── WebEngine 콜백 ───────────────────────────────────────────────────

    def _on_load_finished(self, ok: bool):
        if not ok:
            return
        self._view.page().runJavaScript(f"window.__hfZoom = {_HF_ZOOM};")
        self._view.page().runJavaScript(_EDITOR_JS)

    def _on_editor_ready(self, duration: float):
        self._duration = max(float(duration), 1.0)

    def _on_element_selected(self, selector: str, props_json: str):
        try:
            props = json.loads(props_json)
        except Exception:
            return
        self._sel_selector = selector
        self._sel_lbl.setText(f"선택: {selector}")
        self._set_props_enabled(True)
        self._block_signals(True)

        fs_raw = props.get("fontSize", "16px").replace("px", "").strip()
        try:
            fs_val = int(float(fs_raw))
        except Exception:
            fs_val = 16

        self._prop_x.setValue(props.get("x", 0))
        self._prop_y.setValue(props.get("y", 0))
        self._prop_fs.setValue(fs_val)
        self._prop_text.setText(props.get("text", ""))

        key  = self._current_key()
        gsap = (self._deltas.get(key, {})
                    .get("elements", {})
                    .get(selector, {})
                    .get("gsap_start", 0.0))
        self._prop_gsap.setValue(gsap)

        color_str = props.get("color", "rgb(255,255,255)")
        self._prop_color_btn.setStyleSheet(
            f"background:{color_str}; color:#000; padding:3px;"
        )
        self._block_signals(False)

    def _on_element_moved(self, selector: str, x: float, y: float):
        self._push_undo()
        key  = self._current_key()
        elem = self._deltas.setdefault(key, {}).setdefault("elements", {}).setdefault(selector, {})
        elem["x"] = x
        elem["y"] = y
        self._save_delta(key)
        self.delta_changed.emit(key, self._deltas[key])
        self._block_signals(True)
        self._prop_x.setValue(x)
        self._prop_y.setValue(y)
        self._block_signals(False)

    # ── 속성 변경 ─────────────────────────────────────────────────────────

    def _set_prop(self, prop: str, value):
        if not self._sel_selector:
            return
        key  = self._current_key()
        elem = self._deltas.setdefault(key, {}).setdefault("elements", {}).setdefault(self._sel_selector, {})
        elem[prop] = value
        self._save_delta(key)
        self.delta_changed.emit(key, self._deltas[key])

        if prop != "gsap_start":
            js_v = json.dumps(value) if isinstance(value, str) else str(value)
            self._view.page().runJavaScript(
                f"if(window.__editor)window.__editor.setProperty("
                f"{json.dumps(self._sel_selector)},{json.dumps(prop)},{js_v});"
            )

    def _pick_color(self):
        color = QColorDialog.getColor(parent=self)
        if color.isValid():
            h = color.name()
            self._prop_color_btn.setStyleSheet(f"background:{h}; color:#000; padding:3px;")
            self._set_prop("color", h)

    # ── 스크러버 ──────────────────────────────────────────────────────────

    def _toggle_play(self, checked: bool):
        sp = self.style()
        if checked:
            self._play_btn.setIcon(sp.standardIcon(QStyle.StandardPixmap.SP_MediaPause))
            self._view.page().runJavaScript("if(window.__editor)window.__editor.play();")
            self._play_timer.start()
        else:
            self._play_btn.setIcon(sp.standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
            self._view.page().runJavaScript("if(window.__editor)window.__editor.pause();")
            self._play_timer.stop()

    def _on_scrub(self, val: int):
        t = val / 1000.0 * self._duration
        self._time_lbl.setText(f"{t:.1f} s")
        self._view.page().runJavaScript(f"if(window.__editor)window.__editor.scrub({t});")
        if self._play_btn.isChecked():
            self._play_btn.setChecked(False)
            self._play_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
            self._play_timer.stop()

    def _on_play_tick(self):
        def _cb(t):
            if not self._play_btn.isChecked():
                self._play_timer.stop()
                return
            if t is None:
                return
            t = float(t)
            pos = int(t / self._duration * 1000) if self._duration > 0 else 0
            self._scrubber.blockSignals(True)
            self._scrubber.setValue(min(1000, pos))
            self._scrubber.blockSignals(False)
            self._time_lbl.setText(f"{t:.1f} s")
            if t >= self._duration - 0.1:
                self._play_timer.stop()
                self._play_btn.setChecked(False)
                self._play_btn.setIcon(
                    self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
                )
        self._view.page().runJavaScript(
            "window.__editor ? window.__editor.getCurrentTime() : 0", _cb
        )

    def _on_element_prop_changed(self, selector: str, prop: str, value: str):
        self._sel_selector = selector
        # Save to delta and update the view
        self._set_prop(prop, value)
        # Sync property panel spinbox
        if prop == "fontSize":
            try:
                fs_val = int(float(value.replace("px", "").strip()))
                self._block_signals(True)
                self._prop_fs.setValue(max(8, min(300, fs_val)))
                self._block_signals(False)
            except Exception:
                pass

    # ── Undo / Redo ───────────────────────────────────────────────────────

    def _push_undo(self):
        import copy
        key  = self._current_key()
        snap = (key, copy.deepcopy(self._deltas.get(key, {})))
        self._undo_stack.append(snap)
        if len(self._undo_stack) > 50:
            self._undo_stack.pop(0)
        self._redo_stack.clear()
        self._undo_btn.setEnabled(True)
        self._redo_btn.setEnabled(False)

    def _undo(self):
        if not self._undo_stack:
            return
        import copy
        key = self._current_key()
        self._redo_stack.append((key, copy.deepcopy(self._deltas.get(key, {}))))
        snap_key, snap_delta = self._undo_stack.pop()
        self._deltas[snap_key] = snap_delta
        self._save_delta(snap_key)
        self.delta_changed.emit(snap_key, snap_delta)
        self._undo_btn.setEnabled(bool(self._undo_stack))
        self._redo_btn.setEnabled(True)
        if snap_key == key:
            self._load_slide()

    def _redo(self):
        if not self._redo_stack:
            return
        import copy
        key = self._current_key()
        self._undo_stack.append((key, copy.deepcopy(self._deltas.get(key, {}))))
        snap_key, snap_delta = self._redo_stack.pop()
        self._deltas[snap_key] = snap_delta
        self._save_delta(snap_key)
        self.delta_changed.emit(snap_key, snap_delta)
        self._undo_btn.setEnabled(True)
        self._redo_btn.setEnabled(bool(self._redo_stack))
        if snap_key == key:
            self._load_slide()

    # ── 헬퍼 ─────────────────────────────────────────────────────────────

    def _current_key(self) -> str:
        return self._slide_keys[self._slide_idx] if self._slide_keys else ""

    def _save_delta(self, key: str):
        if not self._comps_dir:
            return
        path  = self._comps_dir / f"{key}_delta.json"
        delta = self._deltas.get(key, {})
        try:
            path.write_text(json.dumps(delta, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def _set_props_enabled(self, enabled: bool):
        for w in [self._prop_x, self._prop_y, self._prop_fs,
                  self._prop_color_btn, self._prop_text, self._prop_gsap]:
            w.setEnabled(enabled)

    def _block_signals(self, block: bool):
        for w in [self._prop_x, self._prop_y, self._prop_fs, self._prop_gsap]:
            w.blockSignals(block)
        self._prop_text.blockSignals(block)


# ══════════════════════════════════════════════
# Step4Widget
# ══════════════════════════════════════════════

class Step4Widget(QWidget):

    def __init__(self, stack: QStackedWidget, parent=None):
        super().__init__(parent)
        self._stack        = stack
        self._project_dir: Path | None = None
        self._plan: dict | None = None

        # 스레드 레퍼런스
        self._render_thread: QThread | None = None
        self._render_worker: RenderWorker | None = None
        self._vrew_thread:   QThread | None = None
        self._vrew_worker:   VrewWorker | None = None
        self._gemini_thread: QThread | None = None
        self._gemini_worker: GeminiWorker | None = None
        self._match_thread:  QThread | None = None
        self._match_worker:  "SemanticMatchWorker | None" = None
        self._n8n_thread:    QThread | None = None
        self._n8n_worker:    "N8nLaunchWorker | None" = None

        # 타이밍 추적 (최종 리포트용)
        self._render_start_time: float | None = None
        self._render_done_count: int = 0
        self._skip_count:        int = 0

        self._latest_vrew: Path | None = None

        # Remotion Studio 프로세스 (중복 실행 방지)
        self._studio_proc: subprocess.Popen | None = None
        self._studio_port: int = 3000

        # VIVID Studio 에디터 서버 (FastAPI daemon thread)
        self._editor_thread: threading.Thread | None = None
        self._editor_port: int = 8000

        # VIVID Studio Vite dev 서버 프로세스
        self._vite_proc: subprocess.Popen | None = None
        self._vite_port: int = 4000

        # ── HyperFrames 관련 ──────────────────────────────────────────────
        self._hf_compositions: dict | None = None
        self._hf_render_thread: QThread | None = None
        self._hf_render_worker = None
        self._hf_vrew_thread:  QThread | None = None
        self._hf_vrew_worker  = None
        self._hf_latest_vrew:  Path | None = None
        self._hf_render_start_time: float | None = None

        self._build_ui()

    # ── UI 구성 ──────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 전체 페이지를 하나의 스크롤 영역으로 감쌈 ──────────────────
        outer_scroll = QScrollArea()
        outer_scroll.setWidgetResizable(True)
        outer_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer_scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
            "QScrollBar:vertical { background: #1E1E1E; width: 8px; border-radius: 4px; }"
            "QScrollBar::handle:vertical { background: #444; border-radius: 4px; }"
        )

        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        # ── 헤더: 제목 + 상태창 ───────────────────────────────────────
        header = QWidget()
        hdr = QVBoxLayout(header)
        hdr.setContentsMargins(32, 24, 32, 8)
        hdr.setSpacing(8)
        hdr.addWidget(make_title("4. 영상 기획안 및 조립"))
        self._status_box = make_status_box()
        hdr.addWidget(self._status_box)
        self._log = StatusLogger(self._status_box)
        page_layout.addWidget(header)

        # ── 탭 위젯 ───────────────────────────────────────────────────
        self._tab_widget = QTabWidget()
        self._tab_widget.setStyleSheet(
            f"QTabBar::tab {{ padding:6px 20px; font-size:12px; }}"
            f"QTabBar::tab:selected {{ color:{C_HIGHLIGHT}; font-weight:bold; }}"
        )
        self._tab_widget.setSizePolicy(
            self._tab_widget.sizePolicy().horizontalPolicy(),
            QSizePolicy.Policy.Preferred,
        )
        self._tab_widget.addTab(self._build_remotion_tab(), "🎬  Remotion")
        self._tab_widget.addTab(self._build_hf_tab(),       "⚡  HyperFrames")
        page_layout.addWidget(self._tab_widget)
        page_layout.addStretch()

        outer_scroll.setWidget(page)
        root.addWidget(outer_scroll)

    # ── Remotion 탭 ──────────────────────────────────────────────────────

    def _build_remotion_tab(self) -> QWidget:
        body = QWidget()
        root = QVBoxLayout(body)
        root.setContentsMargins(32, 8, 32, 24)
        root.setSpacing(12)

        root.addWidget(make_divider())

        # ─────────────────────────────────────────────────
        # STEP A: 기획안 업로드
        # ─────────────────────────────────────────────────
        lbl_a = QLabel("[ STEP A ]  영상 기획안 업로드 (remotion_plan.json)")
        lbl_a.setStyleSheet(
            f"color:{C_HIGHLIGHT}; font-size:12px; font-weight:bold;"
        )
        root.addWidget(lbl_a)

        self._drop_zone = DropZone(
            label="remotion_plan.json 파일을 여기에 끌어다 놓으세요\n(또는 아래 버튼으로 선택)",
            accepted_ext=".json",
        )
        self._drop_zone.file_dropped.connect(self._on_plan_received)
        root.addWidget(self._drop_zone)

        row_a = QHBoxLayout()
        row_a.setSpacing(10)

        self._upload_btn = QPushButton("📁  기획안 업로드")
        self._upload_btn.clicked.connect(self._on_upload_click)
        row_a.addWidget(self._upload_btn)

        self._fx_gallery_btn = QPushButton("🎨  FX 카탈로그 보기")
        self._fx_gallery_btn.setToolTip(
            "현재 등록된 FX 효과 목록을 갤러리로 확인하고 즐겨찾기를 등록합니다."
        )
        self._fx_gallery_btn.clicked.connect(self._on_fx_gallery_click)
        row_a.addWidget(self._fx_gallery_btn)

        self._open_input_btn = QPushButton("📂  프로젝트 폴더 열기")
        self._open_input_btn.setToolTip("프로젝트 input/ 폴더를 파일 탐색기로 엽니다.")
        self._open_input_btn.clicked.connect(self._on_open_input_folder)
        row_a.addWidget(self._open_input_btn)

        row_a.addStretch()
        root.addLayout(row_a)

        plan_hint = QLabel(
            "※ 업로드 시 파일명에 상관없이 remotion_plan.json 으로 자동 변환되어 저장됩니다."
        )
        plan_hint.setStyleSheet(f"color:{C_HIGHLIGHT}; font-size:11px;")
        plan_hint.setWordWrap(True)
        root.addWidget(plan_hint)

        root.addWidget(make_divider())

        # ─────────────────────────────────────────────────
        # STEP B: Remotion 제어
        # ─────────────────────────────────────────────────
        lbl_b = QLabel("[ STEP B ]  Remotion 렌더링 / VIVID Studio")
        lbl_b.setStyleSheet(f"color:{C_HIGHLIGHT}; font-size:12px; font-weight:bold;")
        root.addWidget(lbl_b)

        row_b = QHBoxLayout()
        row_b.setSpacing(10)

        self._render_btn = QPushButton("🎬  Remotion 투명 렌더링")
        self._render_btn.setEnabled(False)
        self._render_btn.setToolTip("배경 투명 .webm 파일 생성 (변경된 FX만 재렌더링 — Diff Check)")
        self._render_btn.clicked.connect(self._on_render_click)
        row_b.addWidget(self._render_btn)

        self._studio_btn = QPushButton("▶🖊  미리보기 + VIVID Studio")
        self._studio_btn.setEnabled(False)
        self._studio_btn.setToolTip("Custom FX 매칭 → Remotion Studio(미리보기) + VIVID Studio(편집) 동시 실행")
        self._studio_btn.clicked.connect(self._on_vivid_studio_click)
        row_b.addWidget(self._studio_btn)

        self._abort_btn = QPushButton("⏹  중단")
        self._abort_btn.setEnabled(False)
        self._abort_btn.clicked.connect(self._on_abort_click)
        row_b.addWidget(self._abort_btn)

        row_b.addStretch()
        root.addLayout(row_b)

        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setTextVisible(True)
        self._progress.setStyleSheet(
            f"QProgressBar {{ background:{C_BG_INPUT}; border:1px solid {C_BORDER};"
            f"border-radius:4px; height:18px; }}"
            f"QProgressBar::chunk {{ background:{C_SUCCESS}; border-radius:3px; }}"
        )
        root.addWidget(self._progress)

        root.addWidget(make_divider())

        # ─────────────────────────────────────────────────
        # STEP C: Vrew 조립
        # ─────────────────────────────────────────────────
        lbl_c = QLabel("[ STEP C ]  최종 Vrew 파일 생성")
        lbl_c.setStyleSheet(f"color:{C_HIGHLIGHT}; font-size:12px; font-weight:bold;")
        root.addWidget(lbl_c)

        row_c = QHBoxLayout()
        row_c.setSpacing(10)

        self._vrew_btn = QPushButton("📦  최종 Vrew 파일 생성")
        self._vrew_btn.setEnabled(False)
        self._vrew_btn.clicked.connect(self._on_vrew_click)
        row_c.addWidget(self._vrew_btn)

        self._open_btn = QPushButton("🎞  Vrew 열기")
        self._open_btn.setEnabled(False)
        self._open_btn.clicked.connect(self._on_open_vrew)
        row_c.addWidget(self._open_btn)

        row_c.addStretch()
        root.addLayout(row_c)

        root.addWidget(make_divider())

        # ─────────────────────────────────────────────────
        # STEP D: AI 기획 지시문 생성 (Google OAuth)
        # ─────────────────────────────────────────────────
        lbl_d = QLabel("[ STEP D ]  AI 기획 지시문 생성")
        lbl_d.setStyleSheet(f"color:{C_HIGHLIGHT}; font-size:12px; font-weight:bold;")
        root.addWidget(lbl_d)

        _oauth_active = (ROOT_DIR / "client_secret.json").exists()
        oauth_info = QLabel(
            "🔐  Google OAuth 인증 모드  (client_secret.json 감지됨)"
            if _oauth_active else
            "⚠️  client_secret.json 없음 — Google OAuth 파일을 루트에 배치하세요"
        )
        oauth_info.setStyleSheet(
            f"color:{'#4CAF50' if _oauth_active else '#FF5252'}; font-size:10px;"
        )
        oauth_info.setWordWrap(True)
        root.addWidget(oauth_info)

        directive_row = QHBoxLayout()
        directive_row.setSpacing(10)
        self._directive_btn = QPushButton("✨  기획 지시문 생성 및 클립보드 복사")
        self._directive_btn.setToolTip(
            "2단계에서 생성된 script_body_slide.txt를 Gemini에 전송하여\n"
            "슬라이드별 핵심 키워드 + 연출 분위기 요약을 생성 후 클립보드에 복사합니다."
        )
        self._directive_btn.clicked.connect(self._on_directive_click)
        directive_row.addWidget(self._directive_btn)
        directive_row.addStretch()
        root.addLayout(directive_row)

        root.addWidget(make_divider())

        nav = QHBoxLayout()
        back_btn = QPushButton("◀  BACK")
        back_btn.clicked.connect(lambda: self._stack.setCurrentIndex(2))
        nav.addWidget(back_btn)
        nav.addStretch()
        root.addLayout(nav)
        root.addStretch()

        return body

    # ── HyperFrames 탭 ───────────────────────────────────────────────────

    def _build_hf_tab(self) -> QWidget:
        body = QWidget()
        root = QVBoxLayout(body)
        root.setContentsMargins(32, 8, 32, 24)
        root.setSpacing(12)

        root.addWidget(make_divider())

        # ─────────────────────────────────────────────────
        # STEP HF-A: n8n 기획안 자동 생성
        # ─────────────────────────────────────────────────
        lbl_n8n = QLabel("[ STEP A ]  n8n 기획안 자동 생성")
        lbl_n8n.setStyleSheet(f"color:{C_HIGHLIGHT}; font-size:12px; font-weight:bold;")
        root.addWidget(lbl_n8n)

        row_n8n = QHBoxLayout()
        row_n8n.setSpacing(10)
        self._hf_n8n_btn = QPushButton("🚀  기획안 생성 (n8n 파이프라인)")
        self._hf_n8n_btn.setToolTip(
            "n8n HyperFrames 파이프라인을 실행합니다.\n"
            "완료 후 생성된 hyperframes_compositions.json을 STEP B에서 업로드하세요."
        )
        self._hf_n8n_btn.clicked.connect(self._trigger_n8n)
        row_n8n.addWidget(self._hf_n8n_btn)
        row_n8n.addStretch()
        root.addLayout(row_n8n)

        n8n_hint = QLabel(
            "※ n8n이 실행 중이어야 합니다 (n8n start). "
            "완료 후 asset/hyperframes_compositions.json이 저장되면 STEP B로 업로드하세요."
        )
        n8n_hint.setStyleSheet(f"color:{C_HIGHLIGHT}; font-size:11px;")
        n8n_hint.setWordWrap(True)
        root.addWidget(n8n_hint)

        root.addWidget(make_divider())

        # ─────────────────────────────────────────────────
        # STEP HF-B: Opal 기획안 업로드
        # ─────────────────────────────────────────────────
        lbl_a = QLabel("[ STEP B ]  Opal 기획안 업로드 (hyperframes_compositions.json)")
        lbl_a.setStyleSheet(f"color:{C_HIGHLIGHT}; font-size:12px; font-weight:bold;")
        root.addWidget(lbl_a)

        self._hf_drop_zone = DropZone(
            label="hyperframes_compositions.json 파일을 여기에 끌어다 놓으세요\n(또는 아래 버튼으로 선택)",
            accepted_ext=".json",
        )
        self._hf_drop_zone.file_dropped.connect(self._on_hf_plan_received)
        root.addWidget(self._hf_drop_zone)

        row_ha = QHBoxLayout()
        row_ha.setSpacing(10)
        self._hf_upload_btn = QPushButton("📁  기획안 업로드")
        self._hf_upload_btn.clicked.connect(self._on_hf_upload_click)
        row_ha.addWidget(self._hf_upload_btn)
        row_ha.addStretch()
        root.addLayout(row_ha)

        hf_hint = QLabel(
            "※ 업로드 시 파일명에 상관없이 hyperframes_compositions.json 으로 자동 변환됩니다."
        )
        hf_hint.setStyleSheet(f"color:{C_HIGHLIGHT}; font-size:11px;")
        hf_hint.setWordWrap(True)
        root.addWidget(hf_hint)

        # lint 결과 + 오류 수정 버튼 (E-18/E-19)
        self._hf_lint_lbl = QLabel("")
        self._hf_lint_lbl.setWordWrap(True)
        self._hf_lint_lbl.setVisible(False)
        root.addWidget(self._hf_lint_lbl)

        row_fix = QHBoxLayout()
        self._hf_fix_btn = QPushButton("⚡  Gemini CLI로 오류 수정")
        self._hf_fix_btn.setVisible(False)
        self._hf_fix_btn.clicked.connect(self._on_hf_fix_click)
        row_fix.addWidget(self._hf_fix_btn)
        row_fix.addStretch()
        root.addLayout(row_fix)

        root.addWidget(make_divider())

        # ─────────────────────────────────────────────────
        # STEP HF-B: 미리보기 / 편집
        # ─────────────────────────────────────────────────
        lbl_b_edit = QLabel("[ STEP C ]  슬라이드 미리보기 및 편집")
        lbl_b_edit.setStyleSheet(f"color:{C_HIGHLIGHT}; font-size:12px; font-weight:bold;")
        root.addWidget(lbl_b_edit)

        self._hf_editor = HfEditorPanel()
        root.addWidget(self._hf_editor)

        root.addWidget(make_divider())

        # ─────────────────────────────────────────────────
        # STEP HF-C: 렌더링
        # ─────────────────────────────────────────────────
        lbl_b = QLabel("[ STEP D ]  HyperFrames 슬라이드 렌더링")
        lbl_b.setStyleSheet(f"color:{C_HIGHLIGHT}; font-size:12px; font-weight:bold;")
        root.addWidget(lbl_b)

        row_hb = QHBoxLayout()
        row_hb.setSpacing(10)

        self._hf_render_btn = QPushButton("🎬  HyperFrames 렌더링")
        self._hf_render_btn.setEnabled(False)
        self._hf_render_btn.setToolTip("슬라이드별 .mp4 렌더링 (delta 편집 내역 자동 적용)")
        self._hf_render_btn.clicked.connect(self._on_hf_render_click)
        row_hb.addWidget(self._hf_render_btn)

        self._hf_abort_btn = QPushButton("⏹  중단")
        self._hf_abort_btn.setEnabled(False)
        self._hf_abort_btn.clicked.connect(self._on_hf_abort_click)
        row_hb.addWidget(self._hf_abort_btn)

        row_hb.addStretch()
        root.addLayout(row_hb)

        self._hf_progress = QProgressBar()
        self._hf_progress.setVisible(False)
        self._hf_progress.setTextVisible(True)
        self._hf_progress.setStyleSheet(
            f"QProgressBar {{ background:{C_BG_INPUT}; border:1px solid {C_BORDER};"
            f"border-radius:4px; height:18px; }}"
            f"QProgressBar::chunk {{ background:{C_SUCCESS}; border-radius:3px; }}"
        )
        root.addWidget(self._hf_progress)

        root.addWidget(make_divider())

        # ─────────────────────────────────────────────────
        # STEP HF-C: Vrew 조립
        # ─────────────────────────────────────────────────
        lbl_c = QLabel("[ STEP E ]  최종 Vrew 파일 생성")
        lbl_c.setStyleSheet(f"color:{C_HIGHLIGHT}; font-size:12px; font-weight:bold;")
        root.addWidget(lbl_c)

        row_hc = QHBoxLayout()
        row_hc.setSpacing(10)

        self._hf_vrew_btn = QPushButton("📦  최종 Vrew 파일 생성")
        self._hf_vrew_btn.setEnabled(False)
        self._hf_vrew_btn.clicked.connect(self._on_hf_vrew_click)
        row_hc.addWidget(self._hf_vrew_btn)

        self._hf_open_btn = QPushButton("🎞  Vrew 열기")
        self._hf_open_btn.setEnabled(False)
        self._hf_open_btn.clicked.connect(self._on_hf_open_vrew)
        row_hc.addWidget(self._hf_open_btn)

        row_hc.addStretch()
        root.addLayout(row_hc)

        root.addWidget(make_divider())

        nav = QHBoxLayout()
        back_btn = QPushButton("◀  BACK")
        back_btn.clicked.connect(lambda: self._stack.setCurrentIndex(2))
        nav.addWidget(back_btn)
        nav.addStretch()
        root.addLayout(nav)
        root.addStretch()

        return body

    # ── 외부 주입 ─────────────────────────────────────────────────────────

    def set_project_dir(self, path: Path | None):
        self._project_dir = path
        self._plan        = None
        self._latest_vrew = None
        self._render_done_count = 0
        self._skip_count        = 0

        # 프로젝트 변경 시 기존 Studio 프로세스 종료
        if self._studio_proc is not None and self._studio_proc.poll() is None:
            self._studio_proc.terminate()
        self._studio_proc = None
        self._studio_port = 3000

        # 프로젝트 변경 시 Vite 프로세스 종료 (FastAPI는 daemon이라 자동 종료)
        if self._vite_proc is not None and self._vite_proc.poll() is None:
            self._vite_proc.terminate()
        self._vite_proc = None

        # ── Remotion UI 초기화 ──
        self._drop_zone.reset()
        self._log.clear()
        self._render_btn.setEnabled(False)
        self._studio_btn.setEnabled(False)
        self._vrew_btn.setEnabled(False)
        self._open_btn.setEnabled(False)
        self._progress.setVisible(False)

        # ── HyperFrames UI 초기화 ──
        self._hf_compositions = None
        self._hf_latest_vrew  = None
        self._hf_drop_zone.reset()
        self._hf_lint_lbl.setVisible(False)
        self._hf_fix_btn.setVisible(False)
        self._hf_render_btn.setEnabled(False)
        self._hf_abort_btn.setEnabled(False)
        self._hf_vrew_btn.setEnabled(False)
        self._hf_open_btn.setEnabled(False)
        self._hf_progress.setVisible(False)
        self._hf_editor.unload()

        if path:
            self._log.highlight(f"프로젝트: {path.name}")

            # ── Remotion 기존 파일 복원 ──────────────────────────────────
            plan = path / "asset" / "remotion_plan.json"
            if plan.exists():
                try:
                    self._plan = parse_plan_json(plan)
                    self._drop_zone.set_ready("remotion_plan.json")
                    self._render_btn.setEnabled(True)
                    self._studio_btn.setEnabled(True)
                    self._log.success("기획안 파일이 확인되었습니다.")
                    self._log.info("Remotion 실행 또는 렌더링 버튼을 눌러주세요.")
                except Exception:
                    self._log.info(
                        "제미나이(웹)에 storyboard.pdf와 fx_catalog.txt를 참고하여 만든\n"
                        "영상 기획안(remotion_plan.json)을 업로드 하세요."
                    )
            else:
                self._log.info(
                    "제미나이(웹)에 storyboard.pdf와 fx_catalog.txt를 참고하여 만든\n"
                    "영상 기획안(remotion_plan.json)을 업로드 하세요."
                )

            # ── HyperFrames 기존 파일 복원 ───────────────────────────────
            hf_json = path / "asset" / "hyperframes_compositions.json"
            if hf_json.exists():
                try:
                    data = json.loads(hf_json.read_text(encoding="utf-8"))
                    ok, _, _ = _lint_hf_json(data)
                    if ok:
                        self._hf_compositions = data
                        self._hf_drop_zone.set_ready("hyperframes_compositions.json")
                        self._hf_render_btn.setEnabled(True)
                        self._log.info(f"HyperFrames 기획안 복원됨  ·  슬라이드 {len(data)}장")
                        comps_dir = path / "hyperframes" / "compositions"
                        if comps_dir.exists():
                            self._hf_editor.load_compositions(comps_dir, sorted(data.keys()))
                except Exception:
                    pass

    # ── §A: 기획안 업로드 ────────────────────────────────────────────────

    def _on_upload_click(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "기획안 파일 선택", str(Path.home()), "JSON 파일 (*.json)"
        )
        if path:
            self._on_plan_received(path)

    def _on_plan_received(self, src_path: str):
        src = Path(src_path)

        # ── 하네스: 기본 검증 ──
        if src.suffix.lower() != ".json":
            self._log.error(f"'{src.name}'은(는) .json 파일이 아닙니다.")
            return
        if src.stat().st_size == 0:
            self._log.error(f"'{src.name}' 파일이 비어 있습니다 (0바이트).")
            return
        if self._project_dir is None:
            self._log.error("프로젝트 폴더가 없습니다. 1단계로 돌아가세요.")
            return

        # ── 저장 (파일명 정규화: 항상 remotion_plan.json으로 저장, Overwrite 허용) ──
        asset_dir = self._project_dir / "asset"
        asset_dir.mkdir(parents=True, exist_ok=True)
        dest = asset_dir / "remotion_plan.json"
        try:
            shutil.copy2(str(src), str(dest))
        except Exception as e:
            self._log.error(f"파일 저장 오류:\n{e}")
            return

        if src.name != "remotion_plan.json":
            self._log.info(f"파일명 정규화: '{src.name}'  →  'remotion_plan.json'")

        # ── JSON 파싱 & 검증 ──
        try:
            plan = parse_plan_json(dest)
        except (FileNotFoundError, ValueError) as e:
            self._log.error(str(e))
            self._drop_zone.set_error("JSON 파싱 실패 — 내용을 확인하세요")
            return

        # ── Composition 파일 생성 (슬라이드 기반) ──
        remotion_dir  = self._project_dir / "remotion"
        timeline_path = self._project_dir / "asset" / "base_timeline.json"
        try:
            generate_compositions(plan, remotion_dir, timeline_path=timeline_path)
        except Exception as e:
            self._log.error(f"Composition 생성 오류:\n{e}")
            return

        self._plan = plan
        effects    = plan.get("effects", [])

        # ── Custom 항목 분류 ────────────────────────────────────────────────
        # ① type="Custom"                    → 신규 효과 필요 → PreflightDialog
        # ② type=컴포넌트명 & TSX 존재        → 기등록 효과 → 바로 사용
        # ③ type=컴포넌트명 & TSX 미존재      → 신규 효과 필요 → PreflightDialog
        _known_builtin = {"Popup", "Video", "TextPopup"}

        def _is_new_custom(eff: dict) -> bool:
            t = eff.get("type", "")
            if t in _known_builtin:
                return False
            if t == "Custom":
                return True           # 명시적 신규 요청
            # 컴포넌트명으로 지정됐지만 파일이 없는 경우
            return not (SHARED_FX_DIR / f"{t}.tsx").exists()

        truly_new   = [e for e in effects if _is_new_custom(e)]
        named_known = [
            e for e in effects
            if e.get("type") not in _known_builtin
            and e.get("type") != "Custom"
            and (SHARED_FX_DIR / f"{e.get('type','')}.tsx").exists()
        ]

        self._drop_zone.set_ready("remotion_plan.json")
        self._log.success(
            f"기획안 파일이 입력되었습니다.  ·  effects: {len(effects)}개"
        )

        # 기등록 컴포넌트 바로 사용 안내
        if named_known:
            self._log.info(
                f"기등록 FX {len(named_known)}개 감지 — "
                f"({', '.join(e.get('type','') for e in named_known)}) "
                "TSX 파일 확인됨. 즉시 사용 가능합니다."
            )

        # ── 진짜 신규 Custom 항목만 PreflightDialog ────────────────────────
        if truly_new:
            self._log.highlight(
                f"신규 Custom 시각 효과 {len(truly_new)}개가 감지되었습니다.\n"
                "코딩 지시 팝업을 확인하고, Claude Code에서 TSX를 작성한 후 진행하세요."
            )
            dlg = PreflightDialog(truly_new, parent=self)
            if dlg.exec() == PreflightDialog.DialogCode.Accepted:
                self._log.success("Custom FX 코딩 완료. 미리보기 또는 렌더링을 진행하세요.")
                self._render_btn.setEnabled(True)
                self._studio_btn.setEnabled(True)
            else:
                self._log.info("Custom FX 코딩이 취소되었습니다. 준비 후 다시 업로드하세요.")
                self._drop_zone.reset()
                self._plan = None
        else:
            self._log.info("미리보기 또는 렌더링 버튼을 눌러주세요.")
            self._render_btn.setEnabled(True)
            self._studio_btn.setEnabled(True)

    # ── §A: 프로젝트 input 폴더 열기 ────────────────────────────────────────

    def _on_open_input_folder(self):
        """프로젝트 input/ 폴더를 파일 탐색기로 열기"""
        if self._project_dir is None:
            return
        folder = self._project_dir / "input"
        folder.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            subprocess.Popen(["explorer", str(folder)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)])

    # ── §A: FX 카탈로그 갤러리 ────────────────────────────────────────────

    def _on_fx_gallery_click(self):
        """FX 갤러리 팝업 열기 (캐시 있으면 즉시, 없으면 파싱 후 표시)"""
        dlg = FxGalleryDialog(CATALOG_PATH, parent=self)
        dlg.exec()

    # ── §B: VIVID Studio 인터랙티브 에디터 ──────────────────────────────────

    def _on_vivid_studio_click(self):
        """
        Remotion Studio(미리보기) + VIVID Studio(편집) 일괄 실행:
          1. Custom FX 시맨틱 매칭 (필요시)
          2. Remotion Studio 실행
          3. FastAPI 브릿지 서버 시작
          4. Vite dev 서버 시작
        """
        if self._project_dir is None:
            self._log.error("프로젝트 폴더가 없습니다. 1단계로 돌아가세요.")
            return

        # ── 이미 모두 실행 중이면 브라우저 두 개 모두 오픈 ──────────────────
        vite_alive = (
            self._vite_proc is not None and self._vite_proc.poll() is None
        )
        api_alive = (
            self._editor_thread is not None and self._editor_thread.is_alive()
        )
        studio_alive = (
            self._studio_proc is not None and self._studio_proc.poll() is None
        )

        if vite_alive and api_alive and studio_alive:
            vite_url = f"http://127.0.0.1:{self._vite_port}"
            studio_url = f"http://localhost:{self._studio_port}"
            self._log.info("모든 서비스가 이미 실행 중입니다.")
            webbrowser.open(studio_url)
            webbrowser.open(vite_url)
            return

        if self._plan is None:
            self._log.error("기획안(remotion_plan.json)을 먼저 로드하세요.")
            return

        # Custom FX 감지
        custom_effs = detect_custom_fx(self._plan)

        if custom_effs:
            # ① PreflightDialog — Claude에게 코딩 요청
            dlg = PreflightDialog(custom_effs, parent=self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return   # 사용자가 취소

            # ② FX 파일 동기화 (심볼릭 링크 / 복사)
            self._sync_fx_files(self._project_dir / "remotion")

            # ③ fx_catalog.txt 읽기
            if not CATALOG_PATH.exists():
                self._log.error("fx_catalog.txt 파일이 없습니다. FX 카탈로그를 확인하세요.")
                return
            catalog_text = CATALOG_PATH.read_text(encoding="utf-8")

            # ④ SemanticMatchWorker 실행 (Gemini 일괄 매칭)
            self._log.info(
                f"Gemini로 Custom FX {len(custom_effs)}개 시맨틱 매칭 중...\n"
                "(첫 실행 시 브라우저 OAuth 로그인 창이 열립니다)"
            )
            self._match_thread = QThread(self)
            self._match_worker = SemanticMatchWorker(custom_effs, catalog_text)
            self._match_worker.moveToThread(self._match_thread)
            self._match_thread.started.connect(self._match_worker.run)
            self._match_worker.finished.connect(self._on_match_done)
            self._match_worker.error.connect(self._on_match_error)
            self._match_worker.finished.connect(self._match_thread.quit)
            self._match_worker.error.connect(self._match_thread.quit)
            self._match_thread.start()
        else:
            # Custom FX 없으면 즉시 일괄 실행
            self._launch_both()

    def _poll_editor_ready(
        self,
        api_port: int,
        vite_port: int,
        vite_url: str,
        attempts: int,
    ) -> None:
        """FastAPI + Vite 서버가 모두 응답할 때까지 폴링 (최대 60회 = 12초)"""
        import socket
        MAX_ATTEMPTS = 60
        INTERVAL_MS  = 200

        def _port_open(p: int) -> bool:
            try:
                with socket.create_connection(("127.0.0.1", p), timeout=0.2):
                    return True
            except OSError:
                return False

        if _port_open(api_port) and _port_open(vite_port):
            self._log.success(
                f"VIVID Studio 준비 완료 → 브라우저 오픈\n{vite_url}"
            )
            webbrowser.open(vite_url)
            return

        if attempts >= MAX_ATTEMPTS:
            self._log.error(
                "VIVID Studio 서버 시작 시간 초과.\n"
                f"  FastAPI: http://127.0.0.1:{api_port}/api/status\n"
                f"  Vite:    {vite_url}"
            )
            return

        QTimer.singleShot(
            INTERVAL_MS,
            lambda: self._poll_editor_ready(api_port, vite_port, vite_url, attempts + 1),
        )

    # ── §B: 미리보기 ─────────────────────────────────────────────────────

    def _sync_fx_files(self, remotion_dir: Path) -> None:
        """
        심볼릭 링크가 실패(Windows 권한 부족 등)한 경우를 대비해
        SHARED_FX_DIR의 최신 TSX 파일을 프로젝트 fx/ 폴더에 직접 동기화.
        심볼릭 링크가 정상이면 아무것도 하지 않는다.
        """
        fx_dir = remotion_dir / "src" / "components" / "fx"
        if fx_dir.is_symlink() and fx_dir.exists():
            return  # 심볼릭 링크 유효 → 동기화 불필요

        fx_dir.mkdir(parents=True, exist_ok=True)
        updated = 0
        for tsx in SHARED_FX_DIR.glob("*.tsx"):
            dest = fx_dir / tsx.name
            if not dest.exists() or dest.stat().st_mtime < tsx.stat().st_mtime:
                shutil.copy2(str(tsx), str(dest))
                updated += 1
        if updated:
            self._log.info(
                f"FX 파일 {updated}개 동기화 완료 "
                "(심볼릭 링크 미작동 → 직접 복사 모드)"
            )

    def _poll_studio_ready(self, port: int, url: str, attempts: int) -> None:
        """
        Remotion Studio가 포트에서 응답할 때까지 500ms마다 재확인.
        최대 60초(120회) 대기 후 타임아웃.
        """
        import socket as _socket
        try:
            with _socket.create_connection(("localhost", port), timeout=0.3):
                webbrowser.open(url)
                self._log.success(
                    f"Remotion Studio 준비 완료 ({url})  "
                    "— 브라우저에서 미리보기를 확인하세요."
                )
                return
        except OSError:
            pass

        if attempts >= 120:  # 60초 타임아웃
            self._log.error(
                "Remotion Studio가 60초 내에 응답하지 않았습니다. "
                "터미널에서 오류를 확인하거나 브라우저를 수동으로 열어주세요."
            )
            webbrowser.open(url)
            return

        # 5초마다 진행 알림
        if attempts > 0 and attempts % 10 == 0:
            elapsed = attempts // 2
            self._log.info(
                f"Remotion Studio 컴파일/번들링 중… ({elapsed}초 경과)"
            )

        QTimer.singleShot(
            500,
            lambda: self._poll_studio_ready(port, url, attempts + 1),
        )

    def _on_match_done(self, matches: dict):
        """SemanticMatchWorker 완료 — 매칭 결과를 plan에 역주입 후 미리보기 실행"""
        applied = []
        unmatched = []

        for eff in self._plan["effects"]:
            eid = eff.get("id", "")
            if eff.get("type") != "Custom":
                continue
            if eid in matches:
                comp_name = matches[eid]
                # type을 실제 컴포넌트명으로 교체 →
                # _build_slide_tsx()의 named-component 브랜치(SHARED_FX_DIR 존재 확인)가
                # 자동으로 처리하므로 별도 _componentName 의존 불필요
                eff["type"] = comp_name
                eff["_componentName"] = comp_name        # 메타데이터용 보존
                eff["_componentFile"] = f"{comp_name}.tsx"
                applied.append(f"  ✅ [{eid}] → {comp_name}")
            else:
                unmatched.append(f"  ⚠️ [{eid}] 매칭 결과 없음 — 렌더링 시 건너뜀")

        report = "\n".join(applied + unmatched)
        self._log.success(f"시맨틱 매칭 완료:\n{report}")

        # [추가] 매칭 결과가 반영된 plan을 디스크에 즉시 저장 (VIVID Studio 동기화)
        if self._project_dir and self._plan:
            plan_p = self._project_dir / "asset" / "remotion_plan.json"
            try:
                with open(plan_p, "w", encoding="utf-8") as f:
                    json.dump(self._plan, f, ensure_ascii=False, indent=2)
                self._log.success("시맨틱 매칭 정보가 기획안 파일에 저장되었습니다.")
            except Exception as e:
                self._log.error(f"기획안 파일 저장 중 오류 발생: {e}")

        self._launch_both()

    def _on_match_error(self, msg: str):
        """SemanticMatchWorker 실패"""
        self._log.error(f"FX 시맨틱 매칭 실패:\n{msg}\n\n매칭 없이 일괄 실행을 계속합니다.")
        # 매칭 실패해도 실행은 계속 (Custom FX는 건너뜀)
        self._launch_both()

    def _launch_preview(self):
        """Composition 재생성 + Remotion Studio 실행"""
        if self._project_dir is None:
            return

        remotion_dir  = self._project_dir / "remotion"
        timeline_path = self._project_dir / "asset" / "base_timeline.json"

        # ── Composition 재생성 ─────────────────────────────────────────
        # 매칭 후 type이 업데이트된 self._plan으로 TSX를 항상 최신 상태로 재생성.
        # (업로드 시점의 generate_compositions 호출은 매칭 전이라 Custom FX 스킵됨)
        try:
            generate_compositions(self._plan, remotion_dir, timeline_path=timeline_path)
        except Exception as e:
            self._log.error(f"Composition 생성 오류:\n{e}")
            return

        # ── 기존 프로세스 살아있으면 재사용 (새 탭 방지) ──────────────
        # Remotion Studio는 파일 변경을 감지해 자동 핫리로드하므로
        # 위에서 TSX를 재생성하면 브라우저도 자동 갱신됨.
        if self._studio_proc is not None and self._studio_proc.poll() is None:
            url = f"http://localhost:{self._studio_port}"
            self._log.info(f"Remotion Studio 이미 실행 중 → 재생성된 Composition 핫리로드 대기 ({url})")
            webbrowser.open(url)
            return

        remotion_dir = self._project_dir / "remotion"

        # ── FX 파일 동기화 (심볼릭 링크 오류 방지) ───────────────────
        self._sync_fx_files(remotion_dir)

        # ── 사용 가능한 포트 탐색 ─────────────────────────────────────
        port = _find_free_port(3000, 3100)

        self._log.info(
            f"Remotion Studio 시작 중 (포트 {port})… "
            "컴파일이 완료되면 브라우저가 자동으로 열립니다."
        )

        try:
            proc = subprocess.Popen(
                [_NPX, "remotion", "studio", "src/index.ts", "--port", str(port)],
                cwd=str(remotion_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=(
                    subprocess.CREATE_NEW_PROCESS_GROUP
                    if sys.platform == "win32" else 0
                ),
            )
        except Exception as e:
            self._log.error(f"Remotion Studio 실행 실패:\n{e}")
            return

        self._studio_proc = proc
        self._studio_port = port
        url = f"http://localhost:{port}"

        # ── 고정 딜레이 대신 포트 응답 폴링 후 브라우저 오픈 ──────────
        self._poll_studio_ready(port, url, attempts=0)

    def _launch_both(self):
        """Remotion Studio + VIVID Studio(FastAPI, Vite) 일괄 실행"""
        # 1. Remotion Studio 실행
        self._launch_preview()

        import socket
        vite_url = f"http://127.0.0.1:{self._vite_port}"

        # ── 2. FastAPI 서버 시작 ─────────────────────────────────────────
        api_alive = (
            self._editor_thread is not None and self._editor_thread.is_alive()
        )
        if not api_alive:
            try:
                from utils.editor_server import start_server
            except ImportError as e:
                self._log.error(
                    f"editor_server 임포트 실패:\n{e}\n"
                    "fastapi/uvicorn 설치 여부를 확인하세요."
                )
                return

            api_port = _find_free_port(8000, 8100)
            self._editor_port = api_port

            t = threading.Thread(
                target=start_server,
                args=(self._project_dir, api_port),
                daemon=True,
            )
            t.start()
            self._editor_thread = t
            self._log.info(f"FastAPI 브릿지 서버 시작 중 (port {api_port})…")

        # ── 3. Vite dev 서버 시작 ────────────────────────────────────────
        vite_alive = (
            self._vite_proc is not None and self._vite_proc.poll() is None
        )
        if not vite_alive:
            from utils.step4_workers import ROOT_DIR
            vivid_studio_dir = ROOT_DIR / "vivid_studio"

            if not vivid_studio_dir.exists():
                self._log.error(
                    f"vivid_studio/ 폴더가 없습니다: {vivid_studio_dir}\n"
                    "워크스페이스 루트에 vivid_studio/ 폴더가 있는지 확인하세요."
                )
                return
            if not (vivid_studio_dir / "node_modules").exists():
                self._log.error(
                    "vivid_studio/node_modules 없음. 터미널에서:\n"
                    f"  cd {vivid_studio_dir}\n  npm install"
                )
                return

            # 빈 포트 스캔 (4000~4100)
            vite_port = _find_free_port(4000, 4100)
            self._vite_port = vite_port
            vite_url = f"http://127.0.0.1:{self._vite_port}"

            try:
                self._vite_proc = subprocess.Popen(
                    [_NPM, "run", "dev", "--", "--port", str(vite_port)],
                    cwd=str(vivid_studio_dir),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=(
                        subprocess.CREATE_NEW_PROCESS_GROUP
                        if sys.platform == "win32" else 0
                    ),
                )
                self._log.info(
                    f"Vite dev 서버 시작 중 (port {self._vite_port})…"
                )
            except Exception as e:
                self._log.error(f"Vite 서버 시작 실패:\n{e}")
                return

        # ── 4. 양쪽 준비 완료 후 브라우저 오픈 ──────────────────────────
        self._poll_editor_ready(
            api_port=self._editor_port,
            vite_port=self._vite_port,
            vite_url=vite_url,
            attempts=0,
        )

    # ── §B: 투명 렌더링 ──────────────────────────────────────────────────

    def _on_render_click(self):
        """
        렌더링 버튼 클릭 — Custom FX 검사는 업로드 시점에 이미 완료되었으므로 바로 렌더 시작.
        """
        if self._plan is None or self._project_dir is None:
            return
        self._start_render()

    def _start_render(self):
        """Pre-flight Check 통과 후 실제 렌더 워커를 실행한다."""
        remotion_dir = self._project_dir / "remotion"
        renders_dir  = self._project_dir / "asset" / "renders"
        cache_path   = self._project_dir / "asset" / "render_cache.json"

        # ── VIVID Studio 편집 내용 강제 동기화 ──────────────────────────────
        # POST /api/plan 으로 저장된 최신 remotion_plan.json을 다시 읽어
        # 메모리의 self._plan(업로드 시점 스냅샷)을 갱신한다.
        plan_path = self._project_dir / "asset" / "remotion_plan.json"
        if plan_path.exists():
            try:
                refreshed = parse_plan_json(plan_path)
                timeline_path = self._project_dir / "asset" / "base_timeline.json"
                generate_compositions(
                    refreshed, remotion_dir,
                    timeline_path=timeline_path if timeline_path.exists() else None,
                )
                self._plan = refreshed
                self._log.info("최신 기획안으로 렌더링 동기화 완료.")
            except Exception as e:
                self._log.error(f"기획안 동기화 실패: {e}\n메모리 버전으로 렌더링 진행합니다.")

        # 타이밍 & 카운터 초기화
        self._render_start_time  = time.time()
        self._render_done_count  = 0
        self._skip_count         = 0

        self._log.info("렌더링 준비 중 (Diff-Check 실행)...")
        self._render_btn.setEnabled(False)
        self._abort_btn.setEnabled(True)
        self._progress.setVisible(True)
        self._progress.setValue(0)

        self._render_thread = QThread(self)
        self._render_worker = RenderWorker(
            self._plan, remotion_dir, renders_dir, cache_path
        )
        self._render_worker.moveToThread(self._render_thread)

        self._render_thread.started.connect(self._render_worker.run)
        self._render_worker.progress.connect(self._on_render_progress)
        self._render_worker.item_done.connect(self._on_item_done)
        self._render_worker.item_skip.connect(self._on_item_skip)
        self._render_worker.finished.connect(self._on_render_finished)
        self._render_worker.error.connect(self._on_render_error)
        self._render_worker.finished.connect(self._render_thread.quit)
        self._render_worker.error.connect(self._render_thread.quit)

        self._render_thread.start()

    def _on_render_progress(self, cur: int, total: int):
        if total:
            self._progress.setMaximum(total)
            self._progress.setValue(cur)
            self._progress.setFormat(f"렌더링 중...  {cur}/{total}")

    def _on_item_done(self, eid: str, path: str):
        self._render_done_count += 1
        self._log.success(f"렌더 완료: {eid}  →  {Path(path).name}")

    def _on_item_skip(self, eid: str):
        self._skip_count += 1
        self._log.info(f"  [스킵] {eid}  — 변경 없음 (캐시 재사용)")

    def _on_render_finished(self, cache: dict):
        if self._project_dir:
            cache_path = self._project_dir / "asset" / "render_cache.json"
            save_render_cache(cache_path, cache)

        self._progress.setValue(self._progress.maximum())
        self._progress.setFormat("렌더링 완료")
        self._abort_btn.setEnabled(False)
        self._render_btn.setEnabled(True)
        self._vrew_btn.setEnabled(True)

        # ── 최종 리포트 (골드 텍스트) ──
        elapsed = 0.0
        if self._render_start_time is not None:
            elapsed = time.time() - self._render_start_time

        total_fx = self._render_done_count + self._skip_count
        m, s     = divmod(int(elapsed), 60)
        time_str = f"{m}분 {s}초" if m else f"{s}초"

        self._log.highlight(
            "━━━━━━━━  렌더링 완료 리포트  ━━━━━━━━\n"
            f"  ⏱  총 소요 시간   : {time_str}\n"
            f"  🎬  신규 렌더 FX  : {self._render_done_count}개\n"
            f"  ⚡  캐시 재사용   : {self._skip_count}개 (Diff-Check 절약)\n"
            f"  📦  전체 FX 합계  : {total_fx}개\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "'최종 Vrew 파일 생성' 버튼을 눌러 조립을 완료하세요."
        )

    def _on_render_error(self, msg: str):
        self._log.error(f"렌더링 오류:\n{msg}")
        self._abort_btn.setEnabled(False)
        self._render_btn.setEnabled(True)
        self._progress.setFormat("오류 발생")

    def _on_abort_click(self):
        if self._render_worker:
            self._render_worker.abort()
        self._abort_btn.setEnabled(False)
        self._log.highlight("렌더링 중단 요청 전송...")

    # ── §C: Vrew 조립 ────────────────────────────────────────────────────

    def _on_vrew_click(self):
        if self._plan is None or self._project_dir is None:
            return

        asset_dir   = self._project_dir / "asset"
        renders_dir = asset_dir / "renders"
        fps         = self._plan.get("fps", 30)

        self._log.info("최종 Vrew 파일 조립 중...")
        self._vrew_btn.setEnabled(False)

        self._vrew_thread = QThread(self)
        self._vrew_worker = VrewWorker(asset_dir, self._plan, renders_dir, fps)
        self._vrew_worker.moveToThread(self._vrew_thread)

        self._vrew_thread.started.connect(self._vrew_worker.run)
        self._vrew_worker.finished.connect(self._on_vrew_finished)
        self._vrew_worker.error.connect(self._on_vrew_error)
        self._vrew_worker.finished.connect(self._vrew_thread.quit)
        self._vrew_worker.error.connect(self._vrew_thread.quit)

        self._vrew_thread.start()

    def _on_vrew_finished(self, out_path: str):
        self._latest_vrew = Path(out_path)
        self._vrew_btn.setEnabled(True)
        self._open_btn.setEnabled(True)
        self._log.success(
            f"최종 Vrew 파일이 생성되었습니다.\n"
            f"  →  {Path(out_path).name}\n"
            "'Vrew 열기' 버튼으로 파일을 확인하세요."
        )

    def _on_vrew_error(self, msg: str):
        self._log.error(f"Vrew 조립 오류:\n{msg}")
        self._vrew_btn.setEnabled(True)

    # ── §D: Vrew 열기 ────────────────────────────────────────────────────

    def _on_open_vrew(self):
        if self._latest_vrew is None or not self._latest_vrew.exists():
            self._log.error("열 수 있는 Vrew 파일이 없습니다.")
            return
        try:
            if sys.platform == "win32":
                import os
                os.startfile(str(self._latest_vrew))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(self._latest_vrew)])
            else:
                subprocess.Popen(["xdg-open", str(self._latest_vrew)])
            self._log.success(f"Vrew 실행 요청: {self._latest_vrew.name}")
        except Exception as e:
            self._log.error(f"Vrew 열기 실패:\n{e}")

    # ── §E: AI 기획 지시문 (Google OAuth) ───────────────────────────────

    def _on_directive_click(self):
        """기획 지시문 생성 + 클립보드 복사"""
        # OAuth 인증 파일 확인
        if not (ROOT_DIR / "client_secret.json").exists():
            self._log.error(
                "client_secret.json 파일이 없습니다.\n"
                "Google Cloud Console에서 OAuth 클라이언트 ID를 발급받아\n"
                f"아래 경로에 저장하세요:\n  {ROOT_DIR / 'client_secret.json'}"
            )
            return

        if self._project_dir is None:
            self._log.error("프로젝트 폴더가 없습니다. 1단계로 돌아가세요.")
            return

        slide_txt = self._project_dir / "input" / "script_body_slide.txt"
        if not slide_txt.exists():
            self._log.error(
                "script_body_slide.txt 파일이 없습니다.\n"
                "2단계 '대본 변환' 버튼을 먼저 실행해주세요."
            )
            return
        if slide_txt.stat().st_size == 0:
            self._log.error("script_body_slide.txt 파일이 비어 있습니다 (0바이트).")
            return

        try:
            script_text = slide_txt.read_text(encoding="utf-8")
        except Exception as e:
            self._log.error(f"파일 읽기 오류:\n{e}")
            return

        self._log.info("Google OAuth로 Gemini에 대본 분석 요청 중...\n(첫 실행 시 브라우저 로그인 창이 열립니다)")
        self._directive_btn.setEnabled(False)

        self._gemini_thread = QThread(self)
        self._gemini_worker = GeminiWorker(script_text=script_text)
        self._gemini_worker.moveToThread(self._gemini_thread)

        self._gemini_thread.started.connect(self._gemini_worker.run)
        self._gemini_worker.finished.connect(self._on_directive_done)
        self._gemini_worker.error.connect(self._on_directive_error)
        self._gemini_worker.finished.connect(self._gemini_thread.quit)
        self._gemini_worker.error.connect(self._gemini_thread.quit)

        self._gemini_thread.start()

    def _on_directive_done(self, result_text: str):
        self._directive_btn.setEnabled(True)

        # 클립보드 복사
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(result_text)
            self._log.success(
                "✅  AI 기획 지시문 생성 완료!\n"
                "클립보드에 복사되었습니다. 제미나이(웹)에 바로 붙여넣기 하세요.\n"
                f"  (분석 글자 수: {len(result_text)}자)"
            )
        else:
            self._log.highlight(
                "기획 지시문 생성 완료 (클립보드 접근 실패).\n"
                "결과:\n" + result_text[:500]
            )

    def _on_directive_error(self, msg: str):
        self._directive_btn.setEnabled(True)
        self._log.error(f"기획 지시문 생성 실패:\n{msg}")

    # ── §HF-0: n8n 기획안 자동 생성 ──────────────────────────────────────

    def _trigger_n8n(self):
        if self._project_dir is None:
            self._log.error("프로젝트 폴더가 없습니다. 1단계로 돌아가세요.")
            return

        if self._n8n_thread and self._n8n_thread.isRunning():
            self._log.warning("n8n 파이프라인이 이미 실행 중입니다.")
            return

        timeline_path = self._project_dir / "asset" / "base_timeline.json"
        slide_count = 0
        if timeline_path.exists():
            try:
                data = json.loads(timeline_path.read_text(encoding="utf-8"))
                slide_count = len(data)
            except Exception:
                pass

        self._hf_n8n_btn.setEnabled(False)
        self._log.info("n8n 상태 확인 중...")

        self._n8n_worker = N8nLaunchWorker(str(self._project_dir), slide_count)
        self._n8n_thread = QThread()
        self._n8n_worker.moveToThread(self._n8n_thread)
        self._n8n_thread.started.connect(self._n8n_worker.run)
        self._n8n_worker.status.connect(self._log.info)
        self._n8n_worker.finished.connect(self._on_n8n_done)
        self._n8n_worker.error.connect(self._on_n8n_error)
        self._n8n_worker.finished.connect(self._n8n_thread.quit)
        self._n8n_worker.error.connect(self._n8n_thread.quit)
        self._n8n_thread.finished.connect(lambda: self._hf_n8n_btn.setEnabled(True))
        self._n8n_thread.start()

    def _on_n8n_done(self, msg: str):
        self._log.success(msg)

    def _on_n8n_error(self, msg: str):
        self._log.error(msg)

    # ── §HF-A: Opal 기획안 업로드 ────────────────────────────────────────

    def _on_hf_upload_click(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Opal 기획안 파일 선택", str(Path.home()), "JSON 파일 (*.json)"
        )
        if path:
            self._on_hf_plan_received(path)

    def _on_hf_plan_received(self, src_path: str):
        src = Path(src_path)

        if src.suffix.lower() != ".json":
            self._log.error(f"'{src.name}'은(는) .json 파일이 아닙니다.")
            return
        if src.stat().st_size == 0:
            self._log.error(f"'{src.name}' 파일이 비어 있습니다 (0바이트).")
            return
        if self._project_dir is None:
            self._log.error("프로젝트 폴더가 없습니다. 1단계로 돌아가세요.")
            return

        # 파일명 정규화 저장
        asset_dir = self._project_dir / "asset"
        asset_dir.mkdir(parents=True, exist_ok=True)
        dest = asset_dir / "hyperframes_compositions.json"
        try:
            if src.resolve() != dest.resolve():
                shutil.copy2(str(src), str(dest))
        except Exception as e:
            self._log.error(f"파일 저장 오류:\n{e}")
            return

        if src.name != "hyperframes_compositions.json":
            self._log.info(f"파일명 정규화: '{src.name}'  →  'hyperframes_compositions.json'")

        # JSON 파싱
        try:
            data = json.loads(dest.read_text(encoding="utf-8"))
        except Exception as e:
            self._log.error(f"JSON 파싱 실패: {e}")
            self._hf_drop_zone.set_error("JSON 파싱 실패")
            return

        # Lint (E-18)
        ok, severity, detail = _lint_hf_json(data)

        if ok:
            self._hf_compositions = data
            self._hf_drop_zone.set_ready("hyperframes_compositions.json")
            self._hf_lint_lbl.setVisible(False)
            self._hf_fix_btn.setVisible(False)
            self._hf_render_btn.setEnabled(True)
            self._log.success(f"기획안 파일 확인 완료  ·  슬라이드 {len(data)}장")
            self._save_hf_slides(data)

        elif severity == "severe":
            self._hf_drop_zone.set_error("중대한 오류 — Opal에서 재생성 필요")
            self._hf_lint_lbl.setText(f"❌  중대한 오류\n{detail}\n\n→ Opal에서 기획안을 재생성해 주세요.")
            self._hf_lint_lbl.setStyleSheet(f"color:{C_ERROR}; font-size:11px;")
            self._hf_lint_lbl.setVisible(True)
            self._hf_fix_btn.setVisible(False)
            self._hf_render_btn.setEnabled(False)
            self._log.error(f"중대한 오류 — {detail}")

        else:  # light
            self._hf_compositions = data
            self._hf_drop_zone.set_ready("hyperframes_compositions.json (오류 있음)")
            self._hf_lint_lbl.setText(f"⚠️  가벼운 오류 감지\n{detail}\n\nGemini CLI로 수정하거나 그대로 렌더링을 진행할 수 있습니다.")
            self._hf_lint_lbl.setStyleSheet(f"color:{C_HIGHLIGHT}; font-size:11px;")
            self._hf_lint_lbl.setVisible(True)
            self._hf_fix_btn.setVisible(True)
            self._hf_render_btn.setEnabled(True)
            self._log.warning(f"가벼운 오류 — {detail}")
            self._save_hf_slides(data)

    def _save_hf_slides(self, data: dict):
        """JSON의 각 슬라이드 HTML을 hyperframes/compositions/에 저장."""
        if self._project_dir is None:
            return
        compositions_dir = self._project_dir / "hyperframes" / "compositions"
        compositions_dir.mkdir(parents=True, exist_ok=True)
        for slide_key in sorted(data):
            try:
                (compositions_dir / f"{slide_key}.html").write_text(
                    data[slide_key], encoding="utf-8"
                )
            except Exception as e:
                self._log.error(f"{slide_key}.html 저장 실패: {e}")

        slide_keys = sorted(data.keys())
        self._hf_editor.load_compositions(compositions_dir, slide_keys)

    # ── §HF-A: E-19 오류 수정 (Gemini CLI) ──────────────────────────────

    def _on_hf_fix_click(self):
        """가벼운 오류 → Gemini CLI로 자동 수정 요청."""
        if self._project_dir is None:
            return
        json_path = self._project_dir / "asset" / "hyperframes_compositions.json"
        prompt = (
            f"파일 경로: {json_path}\n"
            "위 hyperframes_compositions.json의 각 슬라이드 값이 완전한 "
            "<!DOCTYPE html> 독립 HTML 문서가 되도록 가벼운 오류만 수정해줘. "
            "JSON 구조(키: slide_NN, 값: HTML 문자열)는 반드시 유지."
        )
        try:
            from utils.step4_workers import _find_gemini_exe
            gemini_cmd = _find_gemini_exe()
        except Exception as e:
            self._log.error(f"Gemini CLI를 찾을 수 없습니다: {e}")
            return

        self._hf_fix_btn.setEnabled(False)
        self._log.info("Gemini CLI로 오류 수정 중...")

        def _fix():
            try:
                r = subprocess.run(
                    [gemini_cmd, "--yolo", "-p", prompt],
                    capture_output=True, text=True, timeout=120,
                    cwd=str(self._project_dir),
                )
                if r.returncode == 0:
                    QTimer.singleShot(0, self._reload_hf_after_fix)
                else:
                    self._log.error(f"Gemini 수정 실패:\n{r.stderr[:300]}")
                    QTimer.singleShot(0, lambda: self._hf_fix_btn.setEnabled(True))
            except Exception as e:
                self._log.error(f"Gemini 실행 오류: {e}")
                QTimer.singleShot(0, lambda: self._hf_fix_btn.setEnabled(True))

        threading.Thread(target=_fix, daemon=True).start()

    def _reload_hf_after_fix(self):
        json_path = self._project_dir / "asset" / "hyperframes_compositions.json"
        if json_path.exists():
            self._on_hf_plan_received(str(json_path))
            self._log.success("Gemini 수정 완료 — 기획안을 재검증했습니다.")
        self._hf_fix_btn.setEnabled(True)

    # ── §HF-B: 렌더링 ────────────────────────────────────────────────────

    def _on_hf_render_click(self):
        if self._project_dir is None or self._hf_compositions is None:
            return

        compositions_dir = self._project_dir / "hyperframes" / "compositions"
        output_dir       = self._project_dir / "output" / "hyperframes"
        hf_dir           = self._project_dir / "hyperframes"

        if not (hf_dir / "node_modules").exists():
            self._log.error(
                "HyperFrames node_modules가 없습니다.\n"
                "Health Check에서 npm install을 먼저 실행해주세요."
            )
            return

        self._hf_render_btn.setEnabled(False)
        self._hf_abort_btn.setEnabled(True)
        self._hf_progress.setRange(0, len(self._hf_compositions))
        self._hf_progress.setValue(0)
        self._hf_progress.setVisible(True)
        self._hf_render_start_time = time.time()
        self._log.info(f"HyperFrames 렌더링 시작 — 슬라이드 {len(self._hf_compositions)}장")

        from utils.step4_workers import HFRenderWorker
        self._hf_render_worker = HFRenderWorker(compositions_dir, output_dir, hf_dir)
        self._hf_render_thread = QThread(self)
        self._hf_render_worker.moveToThread(self._hf_render_thread)

        self._hf_render_thread.started.connect(self._hf_render_worker.run)
        self._hf_render_worker.progress.connect(self._on_hf_render_progress)
        self._hf_render_worker.finished.connect(self._on_hf_render_done)
        self._hf_render_worker.error.connect(self._on_hf_render_error)
        self._hf_render_worker.finished.connect(self._hf_render_thread.quit)
        self._hf_render_worker.error.connect(self._hf_render_thread.quit)

        self._hf_render_thread.start()

    def _on_hf_render_progress(self, current: int, total: int, name: str):
        self._hf_progress.setValue(current)
        self._hf_progress.setFormat(f"렌더 중: {name}  ({current}/{total})")
        self._log.info(f"[{current}/{total}]  {name} 렌더링 중...")

    def _on_hf_render_done(self, result: object):
        elapsed  = time.time() - (self._hf_render_start_time or time.time())
        rendered = result.get("rendered", [])   # type: ignore[union-attr]
        failed   = result.get("failed",   [])   # type: ignore[union-attr]

        self._hf_abort_btn.setEnabled(False)
        self._hf_progress.setVisible(False)
        self._hf_render_btn.setEnabled(True)

        if failed:
            self._log.error(f"렌더 실패 슬라이드 ({len(failed)}개): {', '.join(failed)}")

        if rendered:
            self._log.highlight(
                f"HyperFrames 렌더링 완료 — {elapsed:.1f}초\n"
                f"성공: {len(rendered)}장  /  실패: {len(failed)}장"
            )
            self._hf_vrew_btn.setEnabled(True)
        else:
            self._log.error("렌더링된 슬라이드가 없습니다.")

    def _on_hf_render_error(self, msg: str):
        self._hf_abort_btn.setEnabled(False)
        self._hf_progress.setVisible(False)
        self._hf_render_btn.setEnabled(True)
        self._log.error(f"렌더링 오류:\n{msg}")

    def _on_hf_abort_click(self):
        self._hf_abort_btn.setEnabled(False)
        self._log.info("렌더링 중단 요청... (현재 슬라이드 완료 후 정지)")

    # ── §HF-C: Vrew 조립 ─────────────────────────────────────────────────

    def _on_hf_vrew_click(self):
        if self._project_dir is None:
            return

        asset_dir   = self._project_dir / "asset"
        renders_dir = self._project_dir / "output" / "hyperframes"
        tl_path     = self._project_dir / "asset" / "base_timeline.json"

        try:
            timeline = json.loads(tl_path.read_text(encoding="utf-8")) if tl_path.exists() else []
        except Exception:
            timeline = []

        self._hf_vrew_btn.setEnabled(False)
        self._log.info("HyperFrames Vrew 조립 중...")

        from utils.step4_workers import HFVrewWorker
        self._hf_vrew_worker = HFVrewWorker(asset_dir, timeline, renders_dir)
        self._hf_vrew_thread = QThread(self)
        self._hf_vrew_worker.moveToThread(self._hf_vrew_thread)

        self._hf_vrew_thread.started.connect(self._hf_vrew_worker.run)
        self._hf_vrew_worker.finished.connect(self._on_hf_vrew_done)
        self._hf_vrew_worker.error.connect(self._on_hf_vrew_error)
        self._hf_vrew_worker.finished.connect(self._hf_vrew_thread.quit)
        self._hf_vrew_worker.error.connect(self._hf_vrew_thread.quit)

        self._hf_vrew_thread.start()

    def _on_hf_vrew_done(self, path_str: str):
        self._hf_latest_vrew = Path(path_str)
        self._hf_vrew_btn.setEnabled(True)
        self._hf_open_btn.setEnabled(True)
        self._log.success(f"HyperFrames Vrew 생성 완료: {Path(path_str).name}")

    def _on_hf_vrew_error(self, msg: str):
        self._hf_vrew_btn.setEnabled(True)
        self._log.error(f"Vrew 조립 오류:\n{msg}")

    def _on_hf_open_vrew(self):
        if self._hf_latest_vrew is None or not self._hf_latest_vrew.exists():
            self._log.error("열 수 있는 Vrew 파일이 없습니다.")
            return
        try:
            if sys.platform == "win32":
                import os
                os.startfile(str(self._hf_latest_vrew))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(self._hf_latest_vrew)])
            else:
                subprocess.Popen(["xdg-open", str(self._hf_latest_vrew)])
            self._log.success(f"Vrew 실행 요청: {self._hf_latest_vrew.name}")
        except Exception as e:
            self._log.error(f"Vrew 열기 실패:\n{e}")

    # ── 정리 ─────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        if self._render_worker:
            self._render_worker.abort()
        for t in (
            self._render_thread, self._vrew_thread,
            self._gemini_thread, self._match_thread,
            self._hf_render_thread, self._hf_vrew_thread,
        ):
            if t and t.isRunning():
                t.quit()
                t.wait(2000)
        super().closeEvent(event)
