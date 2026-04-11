"""
utils/backend.py
파이썬 백엔드 가공 함수 모음 (backend_rules.md 기준)

포함 기능:
  §1  parse_script()       : 인트로/본문 분리
  §1  build_slide_script() : 슬라이드 번호 부여
  §1  convert_script()     : script.txt → 3종 출력 파일
  §2  generate_pdf()       : 이미지 → storyboard.pdf (Pillow)
  §4  parse_srt()          : SRT → base_timeline.json
"""

import json
import re
from pathlib import Path


# ══════════════════════════════════════════════
# §1  대본 분할 (backend_rules.md §1)
# ══════════════════════════════════════════════

# 인트로/본문 구분자 패턴 (우선순위 순)
_SEP_PATTERNS = [
    re.compile(r'^\[본문\]',              re.IGNORECASE),
    re.compile(r'^\[body\]',              re.IGNORECASE),
    re.compile(r'^==\s*(본문|body)\s*==$', re.IGNORECASE),   # ==Body== / ==본문==
    re.compile(r'^-{3,}$'),
    re.compile(r'^={3,}$'),
    re.compile(r'^#{1,3}\s*(본문|body)',  re.IGNORECASE),
    re.compile(r'^\*{3,}$'),
]


def parse_script(text: str) -> tuple[str, str]:
    """
    script.txt 전체 텍스트를 받아 (intro_text, body_text) 튜플 반환.
    구분자를 찾지 못하면 ValueError 발생.
    """
    lines = text.splitlines()
    sep_idx: int | None = None

    for i, line in enumerate(lines):
        if any(pat.match(line.strip()) for pat in _SEP_PATTERNS):
            sep_idx = i
            break

    if sep_idx is None:
        raise ValueError(
            "인트로/본문 구분자를 찾을 수 없습니다.\n"
            "script.txt 안에 [본문], ---, === 등의 구분자 줄이 있어야 합니다."
        )

    # 인트로 영역에서 ==Intro== / [인트로] 등 헤더 줄 제거
    _INTRO_HEADER = re.compile(r'^(==\s*(intro|인트로)\s*==|\[인트로\]|\[intro\])', re.IGNORECASE)
    intro_lines = [l for l in lines[:sep_idx] if not _INTRO_HEADER.match(l.strip())]

    intro = "\n".join(intro_lines).strip()
    body  = "\n".join(lines[sep_idx + 1:]).strip()
    return intro, body


def build_slide_script(body_text: str) -> str:
    """
    본문 텍스트를 빈 줄 기준으로 문단 분리 후
    [슬라이드 N] 번호를 각 문단 앞에 부여하여 반환.
    """
    paragraphs = [p.strip() for p in re.split(r'\n{2,}', body_text) if p.strip()]
    lines: list[str] = []
    for idx, para in enumerate(paragraphs, start=1):
        lines.append(f"[슬라이드 {idx}]")
        lines.append(para)
        lines.append("")
    return "\n".join(lines).strip()


def convert_script(input_dir: Path) -> dict[str, Path]:
    """
    input_dir/script.txt → script_intro.txt, script_body.txt, script_body_slide.txt 생성.

    하네스:
      - 파일 미존재 → FileNotFoundError
      - 0바이트     → ValueError
      - 구분자 없음 → ValueError (parse_script 위임)
      - 인트로/본문 비어있음 → ValueError

    Returns: {"intro": Path, "body": Path, "slide": Path}
    """
    src = input_dir / "script.txt"

    if not src.exists():
        raise FileNotFoundError(f"script.txt 파일을 찾을 수 없습니다: {src}")
    if src.stat().st_size == 0:
        raise ValueError("script.txt 파일이 비어 있습니다 (0바이트).")

    text = src.read_text(encoding="utf-8")
    intro, body = parse_script(text)

    if not intro:
        raise ValueError("인트로 텍스트가 비어 있습니다. 구분자 위 내용을 확인하세요.")
    if not body:
        raise ValueError("본문 텍스트가 비어 있습니다. 구분자 아래 내용을 확인하세요.")

    slide = build_slide_script(body)

    out_intro = input_dir / "script_intro.txt"
    out_body  = input_dir / "script_body.txt"
    out_slide = input_dir / "script_body_slide.txt"

    out_intro.write_text(intro, encoding="utf-8")
    out_body.write_text(body,   encoding="utf-8")
    out_slide.write_text(slide, encoding="utf-8")

    return {"intro": out_intro, "body": out_body, "slide": out_slide}


# ══════════════════════════════════════════════
# §2  스토리보드 PDF 병합 (backend_rules.md §3)
# ══════════════════════════════════════════════

def generate_storyboard_pdf(asset_dir: Path) -> Path:
    """
    asset_dir 안의 image_N.jpeg 파일들을 순서대로 병합하여
    asset_dir/storyboard.pdf 로 저장. 생성된 Path 반환.

    하네스:
      - 이미지 0장 → ValueError
      - Pillow 미설치 → ImportError (호출부에서 처리)
    """
    try:
        from PIL import Image
    except ImportError:
        raise ImportError(
            "Pillow 라이브러리가 설치되지 않았습니다.\n"
            "터미널에서 'pip install Pillow' 를 실행하세요."
        )

    # image_N.jpeg 파일 수집 후 번호순 정렬
    pattern = re.compile(r'^image_(\d+)\.(jpe?g|png|webp)$', re.IGNORECASE)
    entries: list[tuple[int, Path]] = []
    for f in asset_dir.iterdir():
        m = pattern.match(f.name)
        if m:
            entries.append((int(m.group(1)), f))

    if not entries:
        raise ValueError(
            f"asset 폴더에 image_N.jpeg 파일이 없습니다.\n"
            "Watchdog으로 이미지를 먼저 수집하세요."
        )

    entries.sort(key=lambda x: x[0])
    images: list[Image.Image] = []

    for _, path in entries:
        img = Image.open(path).convert("RGB")
        images.append(img)

    out_pdf = asset_dir / "storyboard.pdf"
    images[0].save(
        out_pdf,
        save_all=True,
        append_images=images[1:],
    )
    return out_pdf


# ══════════════════════════════════════════════
# §4  SRT → base_timeline.json (backend_rules.md §4)
# ══════════════════════════════════════════════

def _srt_time_to_seconds(t: str) -> float:
    """
    'HH:MM:SS,mmm' → float 초 변환.
    잘못된 포맷이면 ValueError 발생.
    """
    t = t.strip().replace(",", ".")
    parts = t.split(":")
    if len(parts) != 3:
        raise ValueError(f"SRT 시간 형식 오류: '{t}'")
    h, m, s = parts
    return float(h) * 3600 + float(m) * 60 + float(s)


def parse_srt(srt_path: Path) -> list[dict]:
    """
    Subtitle.srt 파일을 파싱하여 타임라인 레코드 리스트 반환.

    각 레코드: {"index": int, "start": float, "end": float, "text": str}

    하네스:
      - 0바이트      → ValueError
      - 블록 0개     → ValueError
      - 시간 파싱 실패 → ValueError (상세 메시지)
    """
    if not srt_path.exists():
        raise FileNotFoundError(f"SRT 파일을 찾을 수 없습니다: {srt_path}")
    if srt_path.stat().st_size == 0:
        raise ValueError("Subtitle.srt 파일이 비어 있습니다 (0바이트).")

    # BOM 포함 가능성 대비 utf-8-sig
    raw = srt_path.read_text(encoding="utf-8-sig", errors="replace")

    # 빈 줄 2개 이상으로 블록 분리
    blocks = re.split(r'\n{2,}', raw.strip())
    if not blocks:
        raise ValueError("SRT 파일에서 자막 블록을 찾을 수 없습니다.")

    records: list[dict] = []
    time_pat = re.compile(
        r'(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})'
    )

    for block in blocks:
        lines = [l.rstrip() for l in block.strip().splitlines()]
        if len(lines) < 3:
            continue

        # 첫 줄: 인덱스 번호
        try:
            idx = int(lines[0])
        except ValueError:
            continue  # 인덱스가 아닌 블록은 건너뜀

        # 둘째 줄: 타임코드
        m = time_pat.search(lines[1])
        if not m:
            raise ValueError(
                f"SRT 타임코드 형식 오류 (블록 {idx}):\n  '{lines[1]}'"
            )

        try:
            start = _srt_time_to_seconds(m.group(1))
            end   = _srt_time_to_seconds(m.group(2))
        except ValueError as e:
            raise ValueError(f"SRT 시간 파싱 오류 (블록 {idx}): {e}") from e

        # 나머지 줄: 자막 텍스트
        text = " ".join(lines[2:]).strip()

        records.append({
            "index": idx,
            "start": round(start, 3),
            "end":   round(end,   3),
            "text":  text,
        })

    if not records:
        raise ValueError(
            "SRT 파일에서 유효한 자막 블록을 찾지 못했습니다.\n"
            "파일 형식을 확인하세요."
        )

    return records


def generate_timeline_json(asset_dir: Path) -> Path:
    """
    asset_dir/Subtitle.srt → asset_dir/base_timeline.json 생성.
    Returns: 생성된 json Path
    """
    srt_path = asset_dir / "Subtitle.srt"
    records  = parse_srt(srt_path)          # 내부에서 하네스 검사

    out_path = asset_dir / "base_timeline.json"
    out_path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out_path
