"""
utils/motion_comic_editor.py
모션 코믹 전용 편집기 — chapter_NN.html 시각 검수 및 인터랙티브 편집 (과제 6)

template.html의 VIVID_EDIT_* API(과제 21)를 QWebChannel로 연결하여
본 렌더(수 시간) 진입 전 레이어 위치/스케일/회전/투명도를 조정.
편집 결과는 project/edits/chapter_NN_edits.json delta로 분리 저장 (원본 HTML 무수정).
"""

import copy
import json
from pathlib import Path

from PySide6.QtCore import Qt, QObject, QTimer, QUrl, QUrlQuery, Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QDoubleSpinBox, QSlider, QStyle, QFrame,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEngineScript, QWebEngineSettings


# ── 미리보기 캔버스 상수 ──────────────────────────────────────────
_MC_PREVIEW_W = 854
_MC_PREVIEW_H = 480
_MC_ZOOM = _MC_PREVIEW_W / 1920  # ≈ 0.4448

# ── JS 브리지 스크립트 ────────────────────────────────────────────
# loadFinished 후 주입. template.html의 VIVID_EDIT_* API + QWebChannel을 연결.
_MC_BRIDGE_JS = r"""
(function () {
    function waitForChannel(n) {
        if (!window.QWebChannel || !window.qt || !window.qt.webChannelTransport) {
            if (n < 60) setTimeout(function () { waitForChannel(n + 1); }, 50);
            return;
        }
        new QWebChannel(window.qt.webChannelTransport, function (channel) {
            var bridge = channel.objects.mcBridge;
            if (!bridge) return;

            var lastDeltaHash = '';
            var lastSelKey = '';

            // ── Selection 감지 (MutationObserver) ──
            // template.html의 _selectEditTarget()은 closure 내부이므로 직접 패치 불가.
            // [data-edit-id] 요소의 class 변경을 감시하여 .edit-selected 추가를 감지.
            function setupObserver() {
                var viewport = document.getElementById('viewport');
                if (!viewport) return;
                var targets = viewport.querySelectorAll('[data-edit-id]');
                var observer = new MutationObserver(function (mutations) {
                    for (var i = 0; i < mutations.length; i++) {
                        var m = mutations[i];
                        if (m.type !== 'attributes' || m.attributeName !== 'class') continue;
                        var el = m.target;
                        if (!el.classList.contains('edit-selected') || !el.dataset.editId) continue;
                        var sceneGroup = el.closest('.scene-group');
                        var sceneId = sceneGroup ? sceneGroup.id.replace('scene-', '') : 'global';
                        var key = sceneId + ':' + el.dataset.editId;
                        if (key === lastSelKey) continue;
                        lastSelKey = key;
                        var delta = window.VIVID_GET_EDIT_DELTA();
                        var props = delta[key] || { x: 0, y: 0, scale: 1, rotation: 0, opacity: 1 };
                        bridge.on_select(key, JSON.stringify(props));
                    }
                });
                targets.forEach(function (el) {
                    observer.observe(el, { attributes: true, attributeFilter: ['class'] });
                });
            }
            // DOM이 이미 빌드된 상태(loadFinished 후 주입)이므로 즉시 + 100ms 백업
            setupObserver();
            setTimeout(setupObserver, 100);

            // ── Delta 변경 폴링 (200ms) ──
            setInterval(function () {
                var d = JSON.stringify(window.VIVID_GET_EDIT_DELTA());
                if (d !== lastDeltaHash) {
                    lastDeltaHash = d;
                    bridge.on_delta_changed(d);
                }
            }, 200);

            // ── 타임라인 참조 ──
            var _tl = null;
            function getTl() {
                if (_tl) return _tl;
                if (typeof gsap === 'undefined') return null;
                var children = gsap.globalTimeline.getChildren(false, false, true);
                if (children.length) { _tl = children[0]; return _tl; }
                return null;
            }

            // ── Python에서 호출하는 API ──
            window.__mcEditor = {
                seekTo: function (t) {
                    window.VIVID_SEEK(t);
                    // VIVID_SEEK은 applyTime만 호출하고 _reapplyAllDeltas는 호출 안 함.
                    // VIVID_SET_EDIT_DELTA를 자기 자신으로 호출하면 _reapplyAllDeltas 트리거.
                    var d = window.VIVID_GET_EDIT_DELTA();
                    window.VIVID_SET_EDIT_DELTA(d);
                },
                play: function () {
                    var tl = getTl();
                    if (tl) tl.play();
                },
                pause: function () {
                    var tl = getTl();
                    if (tl) tl.pause();
                    var d = window.VIVID_GET_EDIT_DELTA();
                    window.VIVID_SET_EDIT_DELTA(d);
                },
                getTime: function () {
                    var tl = getTl();
                    return tl ? tl.time() : 0;
                },
                getDuration: function () {
                    return window.VIVID_DURATION || 10;
                },
                setDelta: function (jsonStr) {
                    try {
                        window.VIVID_SET_EDIT_DELTA(JSON.parse(jsonStr));
                    } catch (e) {}
                },
                setTransformProp: function (key, prop, value) {
                    var d = window.VIVID_GET_EDIT_DELTA();
                    if (!d[key]) d[key] = { x: 0, y: 0, scale: 1, rotation: 0, opacity: 1 };
                    d[key][prop] = value;
                    window.VIVID_SET_EDIT_DELTA(d);
                }
            };

            // ── Ready 시그널 ──
            bridge.on_ready(window.VIVID_DURATION || 10);
        });
    }
    waitForChannel(0);
})();
"""


# ══════════════════════════════════════════════
# MotionComicBridge — QWebChannel JS↔Python 브리지
# ══════════════════════════════════════════════

class MotionComicBridge(QObject):
    element_selected = Signal(str, str)   # edit_key, props_json
    delta_changed    = Signal(str)        # full delta JSON string
    editor_ready     = Signal(float)      # duration (seconds)
    time_updated     = Signal(float)      # current time (seconds)

    @Slot(str, str)
    def on_select(self, key: str, props_json: str):
        self.element_selected.emit(key, props_json)

    @Slot(str)
    def on_delta_changed(self, delta_json: str):
        self.delta_changed.emit(delta_json)

    @Slot(float)
    def on_ready(self, duration: float):
        self.editor_ready.emit(duration)

    @Slot(float)
    def on_time_update(self, time: float):
        self.time_updated.emit(time)


# ══════════════════════════════════════════════
# MotionComicEditor — 챕터 미리보기/편집 위젯
# ══════════════════════════════════════════════

class MotionComicEditor(QWidget):
    delta_saved = Signal(str, dict)  # chapter_key, delta

    def __init__(self, parent=None):
        super().__init__(parent)
        self._chapter_keys: list[str] = []
        self._chapter_idx:  int = 0
        self._comps_dir:    Path | None = None
        self._edits_dir:    Path | None = None
        self._deltas:       dict[str, dict] = {}
        self._undo_stack:   list[tuple[str, dict]] = []
        self._redo_stack:   list[tuple[str, dict]] = []
        self._sel_key:      str | None = None
        self._duration:     float = 10.0
        self._is_playing:   bool = False
        self._suppress_prop_signals: bool = False

        self._build_ui()
        self._setup_channel()

        self._play_timer = QTimer(self)
        self._play_timer.setInterval(50)
        self._play_timer.timeout.connect(self._on_play_tick)

    # ── UI 구성 ──────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        # ── 챕터 네비게이션 바 ──
        nav = QHBoxLayout()
        _s = self.style()

        self._prev_btn = QPushButton()
        self._prev_btn.setIcon(_s.standardIcon(QStyle.StandardPixmap.SP_ArrowLeft))
        self._prev_btn.setToolTip("이전 챕터")
        self._prev_btn.setFixedWidth(36)
        self._prev_btn.clicked.connect(self._prev_chapter)

        self._chapter_lbl = QLabel("챕터 없음")
        self._chapter_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._chapter_lbl.setStyleSheet("color:#aaa; font-size:12px;")

        self._next_btn = QPushButton()
        self._next_btn.setIcon(_s.standardIcon(QStyle.StandardPixmap.SP_ArrowRight))
        self._next_btn.setToolTip("다음 챕터")
        self._next_btn.setFixedWidth(36)
        self._next_btn.clicked.connect(self._next_chapter)

        self._undo_btn = QPushButton()
        self._undo_btn.setIcon(_s.standardIcon(QStyle.StandardPixmap.SP_ArrowBack))
        self._undo_btn.setText("  되돌리기")
        self._undo_btn.setToolTip("Undo")
        self._undo_btn.setEnabled(False)
        self._undo_btn.clicked.connect(self._undo)

        self._redo_btn = QPushButton()
        self._redo_btn.setIcon(_s.standardIcon(QStyle.StandardPixmap.SP_ArrowForward))
        self._redo_btn.setText("  다시하기")
        self._redo_btn.setToolTip("Redo")
        self._redo_btn.setEnabled(False)
        self._redo_btn.clicked.connect(self._redo)

        nav.addWidget(self._prev_btn)
        nav.addWidget(self._chapter_lbl, 1)
        nav.addWidget(self._next_btn)
        nav.addSpacing(12)
        nav.addWidget(self._undo_btn)
        nav.addWidget(self._redo_btn)
        root.addLayout(nav)

        # ── 메인 영역: WebView + 속성 패널 ──
        main = QHBoxLayout()
        main.setSpacing(8)

        self._view = QWebEngineView()
        self._view.setFixedSize(_MC_PREVIEW_W, _MC_PREVIEW_H)
        main.addWidget(self._view)

        # 속성 패널
        prop = QWidget()
        prop.setFixedWidth(200)
        pl = QVBoxLayout(prop)
        pl.setContentsMargins(6, 0, 0, 0)
        pl.setSpacing(4)

        self._sel_lbl = QLabel("레이어를 클릭하여 선택")
        self._sel_lbl.setStyleSheet("color:#888; font-size:11px;")
        self._sel_lbl.setWordWrap(True)
        pl.addWidget(self._sel_lbl)

        def _lbl(t):
            l = QLabel(t)
            l.setStyleSheet("color:#aaa; font-size:11px; margin-top:4px;")
            return l

        pl.addWidget(_lbl("X (px)"))
        self._prop_x = QDoubleSpinBox()
        self._prop_x.setRange(-1920, 1920)
        self._prop_x.setDecimals(1)
        self._prop_x.setSingleStep(5)
        self._prop_x.valueChanged.connect(lambda v: self._set_transform_prop("x", v))
        pl.addWidget(self._prop_x)

        pl.addWidget(_lbl("Y (px)"))
        self._prop_y = QDoubleSpinBox()
        self._prop_y.setRange(-1080, 1080)
        self._prop_y.setDecimals(1)
        self._prop_y.setSingleStep(5)
        self._prop_y.valueChanged.connect(lambda v: self._set_transform_prop("y", v))
        pl.addWidget(self._prop_y)

        pl.addWidget(_lbl("Scale"))
        self._prop_scale = QDoubleSpinBox()
        self._prop_scale.setRange(0.1, 8.0)
        self._prop_scale.setDecimals(2)
        self._prop_scale.setSingleStep(0.05)
        self._prop_scale.setValue(1.0)
        self._prop_scale.valueChanged.connect(lambda v: self._set_transform_prop("scale", v))
        pl.addWidget(self._prop_scale)

        pl.addWidget(_lbl("Rotation (deg)"))
        self._prop_rot = QDoubleSpinBox()
        self._prop_rot.setRange(-360, 360)
        self._prop_rot.setDecimals(1)
        self._prop_rot.setSingleStep(1)
        self._prop_rot.valueChanged.connect(lambda v: self._set_transform_prop("rotation", v))
        pl.addWidget(self._prop_rot)

        pl.addWidget(_lbl("Opacity"))
        self._prop_opacity = QDoubleSpinBox()
        self._prop_opacity.setRange(0.0, 1.0)
        self._prop_opacity.setDecimals(2)
        self._prop_opacity.setSingleStep(0.05)
        self._prop_opacity.setValue(1.0)
        self._prop_opacity.valueChanged.connect(lambda v: self._set_transform_prop("opacity", v))
        pl.addWidget(self._prop_opacity)

        # 캐릭터 위치 프리셋
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#333;")
        pl.addWidget(sep)

        pl.addWidget(_lbl("캐릭터 위치 프리셋"))
        preset_row = QHBoxLayout()
        preset_row.setSpacing(4)
        for label, x_val in [("Left", -400), ("Center", 0), ("Right", 400)]:
            btn = QPushButton(label)
            btn.setFixedHeight(24)
            btn.clicked.connect(lambda _, xv=x_val: self._apply_position_preset(xv))
            preset_row.addWidget(btn)
        pl.addLayout(preset_row)

        pl.addStretch()

        self._save_btn = QPushButton("💾  Delta 저장")
        self._save_btn.setToolTip("현재 챕터의 편집 delta를 JSON으로 저장")
        self._save_btn.clicked.connect(self._on_save_click)
        pl.addWidget(self._save_btn)

        self._set_props_enabled(False)
        main.addWidget(prop)
        root.addLayout(main)

        # ── 타임라인 스크러버 ──
        scrub = QHBoxLayout()
        self._play_btn = QPushButton()
        self._play_btn.setIcon(_s.standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self._play_btn.setToolTip("재생 / 일시정지")
        self._play_btn.setFixedWidth(36)
        self._play_btn.setCheckable(True)
        self._play_btn.clicked.connect(self._toggle_play)

        self._scrubber = QSlider(Qt.Orientation.Horizontal)
        self._scrubber.setRange(0, 10000)
        self._scrubber.setValue(0)
        self._scrubber.sliderMoved.connect(self._on_scrub)

        self._time_lbl = QLabel("0.00 s")
        self._time_lbl.setFixedWidth(100)
        self._time_lbl.setStyleSheet("color:#888; font-size:11px;")

        scrub.addWidget(self._play_btn)
        scrub.addWidget(self._scrubber, 1)
        scrub.addWidget(self._time_lbl)
        root.addLayout(scrub)

    # ── QWebChannel 설정 ─────────────────────────────────────────────

    def _setup_channel(self):
        self._view.page().settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )

        self._bridge = MotionComicBridge()
        self._channel = QWebChannel(self._view.page())
        self._channel.registerObject("mcBridge", self._bridge)
        self._view.page().setWebChannel(self._channel)

        # qwebchannel.js — DocumentCreation 시점 자동 주입
        qwc = QWebEngineScript()
        qwc.setName("qwebchannel-js")
        qwc.setSourceUrl(QUrl("qrc:///qtwebchannel/qwebchannel.js"))
        qwc.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        qwc.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        self._view.page().scripts().insert(qwc)

        self._bridge.element_selected.connect(self._on_element_selected)
        self._bridge.delta_changed.connect(self._on_delta_changed)
        self._bridge.editor_ready.connect(self._on_editor_ready)
        self._view.loadFinished.connect(self._on_load_finished)
        self._view.page().setZoomFactor(_MC_ZOOM)

    # ── Public API ───────────────────────────────────────────────────

    def load_chapters(self, comps_dir: Path, edits_dir: Path, chapter_keys: list[str]):
        self._comps_dir = comps_dir
        self._edits_dir = edits_dir
        self._chapter_keys = chapter_keys
        self._chapter_idx = 0
        self._deltas = {}
        self._undo_stack = []
        self._redo_stack = []
        self._undo_btn.setEnabled(False)
        self._redo_btn.setEnabled(False)
        self._load_chapter()

    def unload(self):
        self._chapter_keys = []
        self._chapter_idx = 0
        self._comps_dir = None
        self._edits_dir = None
        self._deltas = {}
        self._undo_stack = []
        self._redo_stack = []
        self._sel_key = None
        self._undo_btn.setEnabled(False)
        self._redo_btn.setEnabled(False)
        self._chapter_lbl.setText("챕터 없음")
        self._sel_lbl.setText("레이어를 클릭하여 선택")
        self._set_props_enabled(False)
        self._scrubber.setValue(0)
        self._time_lbl.setText("0.00 s")
        self._play_timer.stop()
        self._is_playing = False
        self._view.setHtml("")

    # ── 챕터 네비게이션 ──────────────────────────────────────────────

    def _current_key(self) -> str:
        return self._chapter_keys[self._chapter_idx] if self._chapter_keys else ""

    def _load_chapter(self):
        if not self._chapter_keys or not self._comps_dir:
            return

        key = self._current_key()
        n = self._chapter_idx + 1
        total = len(self._chapter_keys)
        self._chapter_lbl.setText(f"Chapter {n:02d} / {total:02d}  ({key})")

        self._sel_key = None
        self._sel_lbl.setText("레이어를 클릭하여 선택")
        self._set_props_enabled(False)
        self._scrubber.setValue(0)
        self._time_lbl.setText("0.00 s")
        self._stop_playback()

        # 기존 delta 로드
        if key not in self._deltas:
            self._deltas[key] = self._read_delta_file(key)

        # chapter HTML 로드 (?edit=1로 편집 모드 자동 진입)
        html_path = self._comps_dir / f"{key}.html"
        if html_path.exists():
            url = QUrl.fromLocalFile(str(html_path))
            query = QUrlQuery()
            query.addQueryItem("edit", "1")
            url.setQuery(query)
            self._view.load(url)

    def _prev_chapter(self):
        if self._chapter_idx > 0:
            self._save_delta(self._current_key())
            self._chapter_idx -= 1
            self._load_chapter()

    def _next_chapter(self):
        if self._chapter_idx < len(self._chapter_keys) - 1:
            self._save_delta(self._current_key())
            self._chapter_idx += 1
            self._load_chapter()

    # ── WebEngine 콜백 ───────────────────────────────────────────────

    def _on_load_finished(self, ok: bool):
        if not ok:
            return
        # 브리지 JS 주입
        self._view.page().runJavaScript(_MC_BRIDGE_JS)
        # 저장된 delta가 있으면 주입
        key = self._current_key()
        delta = self._deltas.get(key, {})
        if delta:
            js = json.dumps(delta, ensure_ascii=False)
            self._view.page().runJavaScript(
                f"if(window.VIVID_SET_EDIT_DELTA)window.VIVID_SET_EDIT_DELTA({js});"
            )

    def _on_editor_ready(self, duration: float):
        self._duration = max(float(duration), 1.0)
        self._time_lbl.setText(f"0.00 / {self._duration:.2f} s")

    def _on_element_selected(self, key: str, props_json: str):
        try:
            props = json.loads(props_json)
        except Exception:
            return
        self._sel_key = key
        short = key if len(key) < 40 else f"…{key[-37:]}"
        self._sel_lbl.setText(f"선택: {short}")
        self._set_props_enabled(True)

        self._suppress_prop_signals = True
        self._prop_x.setValue(props.get("x", 0))
        self._prop_y.setValue(props.get("y", 0))
        self._prop_scale.setValue(props.get("scale", 1))
        self._prop_rot.setValue(props.get("rotation", 0))
        self._prop_opacity.setValue(props.get("opacity", 1))
        self._suppress_prop_signals = False

    def _on_delta_changed(self, delta_json: str):
        try:
            delta = json.loads(delta_json)
        except Exception:
            return
        key = self._current_key()
        old = self._deltas.get(key, {})
        if delta != old:
            self._push_undo()
            self._deltas[key] = delta
            self._save_delta(key)

        # 선택된 요소의 속성값 동기화
        if self._sel_key and self._sel_key in delta:
            props = delta[self._sel_key]
            self._suppress_prop_signals = True
            self._prop_x.setValue(props.get("x", 0))
            self._prop_y.setValue(props.get("y", 0))
            self._prop_scale.setValue(props.get("scale", 1))
            self._prop_rot.setValue(props.get("rotation", 0))
            self._prop_opacity.setValue(props.get("opacity", 1))
            self._suppress_prop_signals = False

    # ── 속성 변경 ────────────────────────────────────────────────────

    def _set_transform_prop(self, prop: str, value: float):
        if self._suppress_prop_signals or not self._sel_key:
            return
        key = self._current_key()
        delta = self._deltas.setdefault(key, {})
        if self._sel_key not in delta:
            delta[self._sel_key] = {"x": 0, "y": 0, "scale": 1, "rotation": 0, "opacity": 1}
        delta[self._sel_key][prop] = value
        self._save_delta(key)

        # JS 측에 반영
        js_key = json.dumps(self._sel_key)
        self._view.page().runJavaScript(
            f"if(window.__mcEditor)window.__mcEditor.setTransformProp({js_key},'{prop}',{value});"
        )

    def _apply_position_preset(self, x_val: int):
        if not self._sel_key:
            return
        self._push_undo()
        key = self._current_key()
        delta = self._deltas.setdefault(key, {})
        if self._sel_key not in delta:
            delta[self._sel_key] = {"x": 0, "y": 0, "scale": 1, "rotation": 0, "opacity": 1}
        delta[self._sel_key]["x"] = x_val
        self._save_delta(key)

        self._suppress_prop_signals = True
        self._prop_x.setValue(x_val)
        self._suppress_prop_signals = False

        js = json.dumps(delta, ensure_ascii=False)
        self._view.page().runJavaScript(
            f"if(window.VIVID_SET_EDIT_DELTA)window.VIVID_SET_EDIT_DELTA({js});"
        )

    # ── 타임라인 트랜스포트 ──────────────────────────────────────────

    def _toggle_play(self, checked: bool):
        sp = self.style()
        if checked:
            self._is_playing = True
            self._play_btn.setIcon(sp.standardIcon(QStyle.StandardPixmap.SP_MediaPause))
            self._view.page().runJavaScript("if(window.__mcEditor)window.__mcEditor.play();")
            self._play_timer.start()
        else:
            self._is_playing = False
            self._play_btn.setIcon(sp.standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
            self._view.page().runJavaScript("if(window.__mcEditor)window.__mcEditor.pause();")
            self._play_timer.stop()

    def _on_scrub(self, val: int):
        t = val / 10000.0 * self._duration
        self._time_lbl.setText(f"{t:.2f} / {self._duration:.2f} s")
        self._view.page().runJavaScript(
            f"if(window.__mcEditor)window.__mcEditor.seekTo({t});"
        )
        self._stop_playback()

    def _on_play_tick(self):
        def _cb(t):
            if not self._is_playing:
                return
            if t is None:
                return
            t = float(t)
            pos = int(t / self._duration * 10000) if self._duration > 0 else 0
            self._scrubber.blockSignals(True)
            self._scrubber.setValue(min(10000, pos))
            self._scrubber.blockSignals(False)
            self._time_lbl.setText(f"{t:.2f} / {self._duration:.2f} s")
            if t >= self._duration - 0.1:
                self._stop_playback()

        self._view.page().runJavaScript(
            "window.__mcEditor ? window.__mcEditor.getTime() : 0", _cb
        )

    def _stop_playback(self):
        if self._is_playing:
            self._is_playing = False
            self._play_btn.setChecked(False)
            self._play_btn.setIcon(
                self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
            )
            self._play_timer.stop()

    # ── Undo / Redo ──────────────────────────────────────────────────

    def _push_undo(self):
        key = self._current_key()
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
        key = self._current_key()
        self._redo_stack.append((key, copy.deepcopy(self._deltas.get(key, {}))))
        snap_key, snap_delta = self._undo_stack.pop()
        self._deltas[snap_key] = snap_delta
        self._save_delta(snap_key)
        self._undo_btn.setEnabled(bool(self._undo_stack))
        self._redo_btn.setEnabled(True)
        if snap_key == key:
            self._apply_delta_to_view(snap_delta)

    def _redo(self):
        if not self._redo_stack:
            return
        key = self._current_key()
        self._undo_stack.append((key, copy.deepcopy(self._deltas.get(key, {}))))
        snap_key, snap_delta = self._redo_stack.pop()
        self._deltas[snap_key] = snap_delta
        self._save_delta(snap_key)
        self._undo_btn.setEnabled(True)
        self._redo_btn.setEnabled(bool(self._redo_stack))
        if snap_key == key:
            self._apply_delta_to_view(snap_delta)

    def _apply_delta_to_view(self, delta: dict):
        js = json.dumps(delta, ensure_ascii=False)
        self._view.page().runJavaScript(
            f"if(window.VIVID_SET_EDIT_DELTA)window.VIVID_SET_EDIT_DELTA({js});"
        )

    # ── 저장 / 로드 ─────────────────────────────────────────────────

    def _read_delta_file(self, chapter_key: str) -> dict:
        if not self._edits_dir:
            return {}
        path = self._edits_dir / f"{chapter_key}_edits.json"
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data.get("edit_delta", data) if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_delta(self, chapter_key: str):
        if not self._edits_dir:
            return
        self._edits_dir.mkdir(parents=True, exist_ok=True)
        path = self._edits_dir / f"{chapter_key}_edits.json"
        delta = self._deltas.get(chapter_key, {})
        payload = {"edit_delta": delta}
        try:
            path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass
        self.delta_saved.emit(chapter_key, delta)

    def _on_save_click(self):
        key = self._current_key()
        if key:
            self._save_delta(key)

    # ── 헬퍼 ────────────────────────────────────────────────────────

    def _set_props_enabled(self, enabled: bool):
        for w in [self._prop_x, self._prop_y, self._prop_scale,
                  self._prop_rot, self._prop_opacity, self._save_btn]:
            w.setEnabled(enabled)

    def _block_prop_signals(self, block: bool):
        for w in [self._prop_x, self._prop_y, self._prop_scale,
                  self._prop_rot, self._prop_opacity]:
            w.blockSignals(block)
