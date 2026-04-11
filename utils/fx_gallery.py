"""
utils/fx_gallery.py
FX 카탈로그 갤러리 팝업 다이얼로그

기능:
  - fx_catalog.txt 파싱 → 최초 1회만 로드, 이후 메모리 캐시에서 즉시 반환
  - 각 FX 카드에 ★ 즐겨찾기 토글 체크박스
  - '즐겨찾기 적용' 버튼 → fx_catalog.txt 최상단 ## 즐겨찾기 섹션에 자동 등재
  - 툴팁: 호버 시 Props 상세 정보 표시
"""

import re
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QWidget, QCheckBox,
    QFrame, QMessageBox,
)

from utils.theme import (
    C_BG_MAIN, C_HIGHLIGHT, C_SUCCESS, C_ERROR, C_TEXT,
    C_BORDER, C_BG_INPUT,
)

# ══════════════════════════════════════════════
# 모듈 레벨 캐시 — 최초 1회 파싱 후 재사용
# ══════════════════════════════════════════════

_catalog_cache: list[dict] | None = None


def _parse_catalog(catalog_path: Path) -> list[dict]:
    """
    fx_catalog.txt 테이블 행들을 파싱하여 FX 항목 리스트 반환.
    두 번째 호출부터는 캐시된 데이터를 즉시 반환 (파일 I/O 없음).
    """
    global _catalog_cache
    if _catalog_cache is not None:
        return _catalog_cache

    if not catalog_path.exists():
        _catalog_cache = []
        return _catalog_cache

    text  = catalog_path.read_text(encoding="utf-8")
    lines = text.split("\n")
    entries: list[dict] = []

    in_table   = False
    past_header = False

    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            in_table    = False
            past_header = False
            continue

        # 구분선 (|---|---|...)
        if re.match(r"^\|[\s\-|]+\|$", stripped):
            in_table    = True
            past_header = True
            continue

        if not past_header:
            # 헤더 행 — 스킵
            continue

        cols = [c.strip() for c in stripped.split("|")[1:-1]]
        if len(cols) < 4:
            continue

        # 빈 행 / 마커 행 무시
        raw_id   = cols[0].strip("`")
        raw_type = cols[1].strip("`")
        if not raw_type or "비어있음" in cols[0]:
            continue

        entries.append({
            "id":          raw_id,
            "type":        raw_type,
            "file":        cols[2].strip("`") if len(cols) > 2 else "",
            "description": cols[3]            if len(cols) > 3 else "",
            "props":       cols[4]            if len(cols) > 4 else "",
        })

    _catalog_cache = entries
    return _catalog_cache


def invalidate_cache() -> None:
    """FX 카탈로그가 업데이트되었을 때 캐시를 초기화합니다."""
    global _catalog_cache
    _catalog_cache = None


def _update_favorites(catalog_path: Path, fav_entries: list[dict]) -> None:
    """
    fx_catalog.txt 최상단에 ## 즐겨찾기 (Favorites) 섹션을 작성/갱신.
    기존 즐겨찾기 섹션이 있으면 교체, 없으면 파일 맨 앞에 삽입.
    """
    text = catalog_path.read_text(encoding="utf-8") if catalog_path.exists() else ""

    # 새 즐겨찾기 블록 구성
    header_lines = [
        "## 즐겨찾기 (Favorites)\n",
        "> 갤러리에서 ★ 체크 후 '즐겨찾기 적용'으로 등재된 항목입니다.\n\n",
        "| type 값 | 파일 경로 | 설명 | Props |\n",
        "|---|---|---|---|\n",
    ]
    for e in fav_entries:
        header_lines.append(
            f"| `{e['type']}` | `{e['file']}` | {e['description']} | {e['props']} |\n"
        )
    header_lines.append("\n---\n\n")
    fav_block = "".join(header_lines)

    # 기존 즐겨찾기 섹션 제거
    pattern = r"## 즐겨찾기 \(Favorites\).*?(?=\n## |\Z)"
    cleaned = re.sub(pattern, "", text, flags=re.DOTALL).lstrip()

    catalog_path.write_text(fav_block + cleaned, encoding="utf-8")


# ══════════════════════════════════════════════
# FxGalleryDialog
# ══════════════════════════════════════════════

class FxGalleryDialog(QDialog):
    """
    FX 카탈로그 갤러리 팝업.

    사용법:
        dlg = FxGalleryDialog(catalog_path, parent=self)
        dlg.exec()
    """

    def __init__(self, catalog_path: Path, parent=None):
        super().__init__(parent)
        self._catalog_path = catalog_path
        self._entries      = _parse_catalog(catalog_path)
        # (QCheckBox, entry_dict) 쌍 목록
        self._checks: list[tuple[QCheckBox, dict]] = []

        self.setWindowTitle("🎨  FX 카탈로그 갤러리")
        self.setMinimumSize(660, 500)
        self.setStyleSheet(
            f"QDialog {{ background:{C_BG_MAIN}; color:{C_TEXT}; }}"
            f"QLabel  {{ color:{C_TEXT}; }}"
        )
        self._build_ui()

    # ── UI 구성 ─────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(10)

        # 제목
        title = QLabel("🎨  FX 카탈로그 갤러리")
        title.setStyleSheet(
            f"color:{C_HIGHLIGHT}; font-size:14px; font-weight:bold;"
        )
        root.addWidget(title)

        hint = QLabel(
            "★ 체크박스로 즐겨찾기 선택 후 '즐겨찾기 적용'을 클릭하면\n"
            "fx_catalog.txt 최상단에 자동 등재됩니다. "
            "각 카드에 마우스를 올리면 Props 상세정보가 표시됩니다."
        )
        hint.setStyleSheet("color:#888888; font-size:11px;")
        hint.setWordWrap(True)
        root.addWidget(hint)

        root.addWidget(self._make_divider())

        # ── 스크롤 영역 ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            f"QScrollArea {{ border: 1px solid {C_BORDER}; background:{C_BG_INPUT}; }}"
        )

        container = QWidget()
        container.setStyleSheet(f"background:{C_BG_INPUT};")
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(8, 8, 8, 8)
        vbox.setSpacing(6)

        if not self._entries:
            empty_lbl = QLabel(
                "등록된 FX가 없습니다.\n"
                "기획안 업로드 시 Custom FX가 자동 등재됩니다."
            )
            empty_lbl.setStyleSheet("color:#888888; font-size:12px;")
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            vbox.addWidget(empty_lbl)
        else:
            for entry in self._entries:
                vbox.addWidget(self._make_card(entry))

        vbox.addStretch()
        scroll.setWidget(container)
        root.addWidget(scroll)

        root.addWidget(self._make_divider())

        # ── 버튼 행 ──
        btn_row = QHBoxLayout()

        # 전체 선택 / 해제
        sel_all_btn = QPushButton("전체 선택")
        sel_all_btn.setFixedWidth(90)
        sel_all_btn.clicked.connect(lambda: self._toggle_all(True))
        btn_row.addWidget(sel_all_btn)

        desel_btn = QPushButton("전체 해제")
        desel_btn.setFixedWidth(90)
        desel_btn.clicked.connect(lambda: self._toggle_all(False))
        btn_row.addWidget(desel_btn)

        btn_row.addStretch()

        apply_btn = QPushButton("★  즐겨찾기 적용")
        apply_btn.setStyleSheet(
            f"background:{C_HIGHLIGHT}; color:#000000; font-weight:bold;"
            "padding: 6px 18px; border-radius:4px;"
        )
        apply_btn.clicked.connect(self._on_apply)
        btn_row.addWidget(apply_btn)

        close_btn = QPushButton("닫기")
        close_btn.setFixedWidth(70)
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)

        root.addLayout(btn_row)

    def _make_card(self, entry: dict) -> QFrame:
        """FX 하나를 카드 형태의 QFrame으로 생성"""
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background:#1E1E1E; border:1px solid {C_BORDER};"
            "border-radius:6px; }}"
        )
        # 툴팁: Props 상세 정보
        tooltip_text = (
            f"<b>type:</b> {entry['type']}<br>"
            f"<b>file:</b> {entry['file']}<br>"
            f"<b>Props:</b> {entry['props']}"
        )
        card.setToolTip(tooltip_text)

        row = QHBoxLayout(card)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(10)

        # ★ 체크박스
        chk = QCheckBox("★")
        chk.setStyleSheet(
            f"QCheckBox {{ color:{C_HIGHLIGHT}; font-size:18px; }}"
            "QCheckBox::indicator { width:0px; height:0px; }"
        )
        chk.setToolTip("즐겨찾기에 추가")
        row.addWidget(chk)
        self._checks.append((chk, entry))

        # type 배지
        badge_color = C_HIGHLIGHT if entry["type"] == "Custom" else "#4A90D9"
        type_badge = QLabel(f" {entry['type']} ")
        type_badge.setStyleSheet(
            f"background:{badge_color}; color:#000; font-size:10px;"
            "font-weight:bold; border-radius:3px; padding:1px 6px;"
        )
        type_badge.setFixedWidth(70)
        type_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(type_badge)

        # 설명 + 파일 경로
        info_col = QVBoxLayout()
        info_col.setSpacing(2)
        desc = entry["description"] or "(설명 없음)"
        desc_lbl = QLabel(desc[:60] + ("…" if len(desc) > 60 else ""))
        desc_lbl.setStyleSheet(f"color:{C_TEXT}; font-size:12px;")
        file_lbl = QLabel(entry["file"])
        file_lbl.setStyleSheet("color:#888888; font-size:10px;")
        info_col.addWidget(desc_lbl)
        info_col.addWidget(file_lbl)
        row.addLayout(info_col)
        row.addStretch()

        # Props 요약 (우측)
        props_summary = entry["props"][:55] + ("…" if len(entry["props"]) > 55 else "")
        props_lbl = QLabel(props_summary)
        props_lbl.setStyleSheet("color:#666666; font-size:10px;")
        props_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        props_lbl.setMaximumWidth(200)
        props_lbl.setWordWrap(True)
        row.addWidget(props_lbl)

        return card

    @staticmethod
    def _make_divider() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color:{C_BORDER}; margin:4px 0;")
        return line

    # ── 핸들러 ──────────────────────────────────────────────────────────

    def _toggle_all(self, checked: bool):
        for chk, _ in self._checks:
            chk.setChecked(checked)

    def _on_apply(self):
        favorites = [entry for chk, entry in self._checks if chk.isChecked()]
        if not favorites:
            QMessageBox.information(
                self, "즐겨찾기",
                "★ 체크된 항목이 없습니다.\n등록할 FX를 선택해주세요."
            )
            return

        try:
            _update_favorites(self._catalog_path, favorites)
            invalidate_cache()   # 다음 갤러리 열기 시 재파싱
        except Exception as e:
            QMessageBox.warning(self, "저장 오류", f"fx_catalog.txt 저장 실패:\n{e}")
            return

        QMessageBox.information(
            self, "즐겨찾기 저장 완료",
            f"{len(favorites)}개 항목이 fx_catalog.txt 즐겨찾기에 등록되었습니다."
        )
        self.accept()
