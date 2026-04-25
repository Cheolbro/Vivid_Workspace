"""
utils/hf_editor.py
HyperFrames 슬라이드 편집 UI — JS 상수, 검증 유틸, HfBridge, HfEditorPanel
"""

import json
import re as _re
from pathlib import Path

from PySide6.QtCore import Qt, QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton,
    QColorDialog, QDoubleSpinBox, QSpinBox, QSlider, QLineEdit, QStyle,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEngineScript, QWebEngineSettings


# ── 미리보기 캔버스 상수 ──────────────────────────────────────────────────────
_HF_PREVIEW_W = 854
_HF_PREVIEW_H = 480
_HF_ZOOM      = _HF_PREVIEW_W / 1920   # ≈ 0.4448

# DocumentCreation 시점 주입 — GSAP CDN 번들이 window.gsap을 할당할 때 가로채서
# (1) autoRemoveChildren=false, (2) timeline() 생성을 window.__capturedTl에 기록.
# _EDITOR_JS(loadFinished 후 주입)보다 반드시 먼저 실행되어야 함.
_GSAP_INTERCEPT_JS = r"""
(function () {
    // DOMContentLoaded: inline <script>가 실행된 직후, 애니메이션이 아직 진행 중인 시점.
    // (31초짜리 슬라이드 — 페이지 로딩은 <1초이므로 타임라인이 globalTimeline에 존재함)
    // Object.defineProperty 방식은 GSAP UMD가 빈 {}를 먼저 할당한 뒤
    // 메서드를 채우는 패턴 때문에 인터셉트에 실패하므로 사용하지 않음.
    document.addEventListener('DOMContentLoaded', function () {
        if (typeof gsap === 'undefined') return;
        // 타임라인 완료 시 globalTimeline에서 제거되지 않도록 설정
        gsap.globalTimeline.autoRemoveChildren = false;
        if (!window.__capturedTl) {
            var direct = gsap.globalTimeline.getChildren(false, false, true);
            if (direct.length) {
                window.__capturedTl = direct[0];
            } else {
                var all = gsap.globalTimeline.getChildren(true, false, true);
                if (all.length) window.__capturedTl = all[0];
            }
        }
    });
})();
"""

_EDITOR_JS = r"""
(function () {
    // ── Fix 1: override viewport meta (width=device-width + setZoomFactor = 2x coord mismatch)
    var _vp = document.querySelector('meta[name="viewport"]');
    if (_vp) _vp.content = 'width=1920';

    // ── Fix 2: prevent GSAP from discarding completed timelines before JS injection
    if (typeof gsap !== 'undefined') gsap.globalTimeline.autoRemoveChildren = false;

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

    // ── Step 2: Locate the actual child timeline ─────────────────────────────────
    // Priority: window.__capturedTl (set by _GSAP_INTERCEPT_JS at DocumentCreation)
    // Fallback:  globalTimeline.getChildren() in case intercept wasn't injected
    function _getMainTl() {
        if (window.__capturedTl) return window.__capturedTl;
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
        c.querySelectorAll('*').forEach(function (el) { el.classList.add('hf-editor-visible'); });
    }
    _forceVisible();

    var _handles = [], _resizing = false, _resizeDir = null;
    var _resizeStartX, _resizeStartY, _resizeStartFontSize, _resizeStartScale;

    function _getScale(el) {
        var t = el.style.transform || window.getComputedStyle(el).transform;
        if (!t || t === 'none') return 1;
        var m = t.match(/scale\(([^)]+)\)/);
        if (m) return parseFloat(m[1]);
        var mat = t.match(/matrix\(([^,]+)/);
        return mat ? parseFloat(mat[1]) : 1;
    }

    function _removeHandles() {
        _handles.forEach(function (h) { if (h.parentNode) h.parentNode.removeChild(h); });
        _handles = [];
    }
    function _addHandles(el) {
        _removeHandles();
        var isText = el.classList.contains('text-common');
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
                    if (isText) {
                        _resizeStartFontSize = parseFloat(window.getComputedStyle(el).fontSize) || 80;
                    } else {
                        _resizeStartScale = _getScale(el);
                    }
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
                    if (sel.classList.contains('text-common')) {
                        sel.style.fontSize = Math.max(12, _resizeStartFontSize + delta * 0.5) + 'px';
                    } else {
                        var newScale = Math.max(0.05, _resizeStartScale + delta * 0.002);
                        sel.style.transform = 'scale(' + newScale + ')';
                    }
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
                        if (sel.classList.contains('text-common')) {
                            var newFs = window.getComputedStyle(sel).fontSize;
                            bridge.on_prop_change(getSel(sel), 'fontSize', newFs);
                        } else {
                            bridge.on_prop_change(getSel(sel), 'scale', String(_getScale(sel)));
                        }
                        _removeHandles(); _addHandles(sel);
                    }
                }
            });

            window.__editor = {
                scrub: function (t) {
                    if (!window.__timelines && typeof gsap !== 'undefined') {
                        var tl2 = _getMainTl();
                        if (tl2) { tl2.pause(); window.__timelines = { main: tl2 }; }
                    }
                    Object.values(window.__timelines || {}).forEach(function (tl) {
                        tl.seek(t); tl.pause();
                    });
                    _forceVisible();
                },
                play: function () {
                    // Re-acquire timeline if not yet captured (last-resort fallback)
                    if (!window.__timelines) {
                        var tl2 = _getMainTl();
                        if (tl2) { tl2.pause(); window.__timelines = { main: tl2 }; }
                    }
                    var hasTl = Object.keys(window.__timelines || {}).length > 0;
                    // Only remove forced-visibility when we actually have a timeline to play.
                    // Without this guard, elements would disappear with nothing animating them back.
                    var c = document.getElementById('composition');
                    if (c && hasTl) {
                        c.querySelectorAll('*').forEach(function (el) {
                            el.classList.remove('hf-editor-visible');
                        });
                    }
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

            // Poll until GSAP timeline is captured (max 20 × 50 ms = 1 s) before
            // signalling Python. Needed because loadFinished fires while the CDN
            // script may still be resolving, leaving window.__timelines unset on
            // the first one-shot attempt above.
            (function _waitForTl(n) {
                if (!window.__timelines && typeof gsap !== 'undefined') {
                    gsap.globalTimeline.autoRemoveChildren = false;
                    var tl3 = _getMainTl();
                    if (tl3) { tl3.pause(); window.__timelines = { main: tl3 }; }
                }
                if (window.__timelines || n >= 20) {
                    bridge.on_ready(window.__editor.getDuration());
                } else {
                    setTimeout(function () { _waitForTl(n + 1); }, 50);
                }
            })(0);
        });
    }
    init();
})();
"""


# ── 검증 유틸 ─────────────────────────────────────────────────────────────────

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
        # file:// 페이지에서 CDN(GSAP 등) HTTPS 스크립트 로드 허용
        # 기본값 False이면 gsap이 undefined → window.__timelines 미설정 → 재생 불가
        self._view.page().settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )

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

        # GSAP 인터셉터: window.gsap 할당 시점(CDN 번들 실행 직후)을 가로채서
        # autoRemoveChildren=false + timeline 캡처. loadFinished보다 먼저 실행됨.
        gsap_intercept = QWebEngineScript()
        gsap_intercept.setName("gsap-intercept")
        gsap_intercept.setSourceCode(_GSAP_INTERCEPT_JS)
        gsap_intercept.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        gsap_intercept.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        self._view.page().scripts().insert(gsap_intercept)

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
        self._set_prop(prop, value)
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
