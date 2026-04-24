"""
utils/backend_ext.py
backend_rules.md §5 · §6 · §7 구현
  §5  generate_custom_fx_component() + update_fx_catalog()
  §5  generate_compositions()   : Root.tsx + 개별 FX 컴포지션 파일 생성
  §6  diff_check_effects()      : 변경된 FX ID만 추출 (스마트 부분 렌더링)
  §7  assemble_vrew()           : 원본.vrew + rendered .webm → 최종_vN.vrew

Vrew 파일 구조 (실물 분석 기반):
  - .vrew = ZIP (project.json + media/)
  - project.json:
      files[]              : 미디어 파일 메타데이터 배열
      transcript.clips[]   : 씬 단위 클립 (word 타이밍 포함)
      props.tracks{}       : trackId → 트랙 객체 (video/image/bgm/ttsClip)
      props.assets{}       : assetId → {role, trackIds[]}
    연결: clip.assetIds → asset.trackIds → track (mediaId)
"""

import hashlib
import json
import shutil
import subprocess
import sys
import uuid
import zipfile
from pathlib import Path

_HIDDEN_SH = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}

from utils.theme import SHARED_ASSETS_DIR, SHARED_FX_DIR

# ══════════════════════════════════════════════
# 공용 에셋 경로 해석 (Shared Asset Resolver)
# ══════════════════════════════════════════════

def resolve_asset(filename: str, asset_dir: Path) -> Path | None:
    """
    에셋 파일 2단계 Fallback 탐색.

    1순위: project/asset/{filename}   — 프로젝트 전용 파일 (우선)
    2순위: shared_assets/{filename}   — 채널 공용 파일 (bumper.mp4 등)
    없으면 None 반환.

    사용처:
      - generate_compositions() : Video 타입 파일을 remotion/public/ 에 복사
      - assemble_vrew()         : Video 타입 파일을 Vrew ZIP 에 삽입
    """
    local = asset_dir / filename
    if local.exists():
        return local
    shared = SHARED_ASSETS_DIR / filename
    if shared.exists():
        return shared
    return None


# ══════════════════════════════════════════════
# §5-A  Custom FX TSX 템플릿 사전
# ══════════════════════════════════════════════

_FX_TEMPLATES: dict[str, dict] = {
    "rain": {
        "componentName": "RainFX",
        "defaultProps": {"particleCount": 40, "color": "#87CEEB", "speed": 4.0, "size": 12},
        "tsx": """\
import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, random } from "remotion";

interface Props {
  startFrame?: number; durationFrames?: number;
  particleCount?: number; color?: string; speed?: number; size?: number;
}
export const {name}: React.FC<Props> = ({
  startFrame = 0, durationFrames = 60,
  particleCount = 40, color = "#87CEEB", speed = 4.0, size = 12,
}) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const rel = frame - startFrame;
  if (rel < 0 || rel >= durationFrames) return null;
  const opacity = interpolate(rel, [0, 8, durationFrames - 8, durationFrames],
    [0, 1, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <div style={{ position: "absolute", inset: 0, overflow: "hidden", opacity }}>
      {Array.from({ length: particleCount }).map((_, i) => {
        const x = random(`x${i}`) * width;
        const y = ((random(`y${i}`) * height + rel * speed * (0.8 + random(`s${i}`) * 0.4)) % height);
        return <div key={i} style={{ position: "absolute", left: x, top: y,
          width: size, height: size * 2, borderRadius: size / 2,
          backgroundColor: color, opacity: 0.7 + random(`o${i}`) * 0.3 }} />;
      })}
    </div>
  );
};
""",
    },
    "money": {
        "componentName": "MoneyRainFX",
        "defaultProps": {"particleCount": 30, "color": "#FFD700", "speed": 5.0, "size": 24},
        "tsx": """\
import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, random } from "remotion";

interface Props {
  startFrame?: number; durationFrames?: number;
  particleCount?: number; color?: string; speed?: number; size?: number;
}
export const {name}: React.FC<Props> = ({
  startFrame = 0, durationFrames = 60,
  particleCount = 30, color = "#FFD700", speed = 5.0, size = 24,
}) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const rel = frame - startFrame;
  if (rel < 0 || rel >= durationFrames) return null;
  const opacity = interpolate(rel, [0, 8, durationFrames - 8, durationFrames],
    [0, 1, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <div style={{ position: "absolute", inset: 0, overflow: "hidden", opacity }}>
      {Array.from({ length: particleCount }).map((_, i) => {
        const x = random(`x${i}`) * width;
        const y = ((random(`y${i}`) * height + rel * speed * (0.7 + random(`s${i}`) * 0.6)) % height);
        const rot = (rel * 3 + random(`r${i}`) * 360) % 360;
        return (
          <div key={i} style={{ position: "absolute", left: x, top: y, width: size, height: size,
            borderRadius: "50%", backgroundColor: color,
            transform: `rotate(${rot}deg)`, boxShadow: `0 0 ${size / 3}px ${color}` }}>
            <span style={{ fontSize: size * 0.65, lineHeight: `${size}px` }}>💰</span>
          </div>
        );
      })}
    </div>
  );
};
""",
    },
    "particle": {
        "componentName": "ParticleBurstFX",
        "defaultProps": {"particleCount": 60, "color": "#FF6B35", "speed": 8.0, "size": 8},
        "tsx": """\
import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, random } from "remotion";

interface Props {
  startFrame?: number; durationFrames?: number;
  particleCount?: number; color?: string; speed?: number; size?: number;
}
export const {name}: React.FC<Props> = ({
  startFrame = 0, durationFrames = 60,
  particleCount = 60, color = "#FF6B35", speed = 8.0, size = 8,
}) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const rel = frame - startFrame;
  if (rel < 0 || rel >= durationFrames) return null;
  const progress = rel / durationFrames;
  const opacity = interpolate(rel, [0, 5, durationFrames - 10, durationFrames],
    [0, 1, 0.6, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <div style={{ position: "absolute", inset: 0, overflow: "hidden", opacity }}>
      {Array.from({ length: particleCount }).map((_, i) => {
        const angle = random(`a${i}`) * Math.PI * 2;
        const dist  = progress * speed * (50 + random(`d${i}`) * 200);
        const cx = width / 2 + Math.cos(angle) * dist;
        const cy = height / 2 + Math.sin(angle) * dist;
        return <div key={i} style={{ position: "absolute", left: cx, top: cy,
          width: size, height: size, borderRadius: "50%",
          backgroundColor: color, opacity: 1 - progress,
          transform: `scale(${1 - progress * 0.7})` }} />;
      })}
    </div>
  );
};
""",
    },
    "glow": {
        "componentName": "GlowFX",
        "defaultProps": {"color": "#FFD700", "intensity": 0.4, "pulseSpeed": 2.0},
        "tsx": """\
import React from "react";
import { useCurrentFrame, interpolate } from "remotion";

interface Props {
  startFrame?: number; durationFrames?: number;
  color?: string; intensity?: number; pulseSpeed?: number;
}
export const {name}: React.FC<Props> = ({
  startFrame = 0, durationFrames = 60,
  color = "#FFD700", intensity = 0.4, pulseSpeed = 2.0,
}) => {
  const frame = useCurrentFrame();
  const rel = frame - startFrame;
  if (rel < 0 || rel >= durationFrames) return null;
  const base = interpolate(rel, [0, 10, durationFrames - 10, durationFrames],
    [0, intensity, intensity, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const pulse = Math.sin(rel * pulseSpeed * 0.2) * 0.1 + 1;
  return (
    <div style={{
      position: "absolute", inset: 0,
      background: `radial-gradient(ellipse at center, ${color}88 0%, ${color}22 50%, transparent 80%)`,
      opacity: base * pulse,
    }} />
  );
};
""",
    },
    "generic": {
        "componentName": "OverlayFX",
        "defaultProps": {"color": "#FFFFFF", "opacity": 0.3},
        "tsx": """\
import React from "react";
import { useCurrentFrame, interpolate } from "remotion";

interface Props {
  startFrame?: number; durationFrames?: number;
  color?: string; opacity?: number;
}
export const {name}: React.FC<Props> = ({
  startFrame = 0, durationFrames = 60,
  color = "#FFFFFF", opacity = 0.3,
}) => {
  const frame = useCurrentFrame();
  const rel = frame - startFrame;
  if (rel < 0 || rel >= durationFrames) return null;
  const alpha = interpolate(rel, [0, 10, durationFrames - 10, durationFrames],
    [0, opacity, opacity, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return <div style={{ position: "absolute", inset: 0, backgroundColor: color, opacity: alpha }} />;
};
""",
    },
}


def _pick_fx_template(description: str) -> str:
    d = description.lower()
    # 구체적인 키워드를 먼저 검사 (우선순위 높음)
    if any(k in d for k in ["돈", "coin", "money", "동전", "황금"]):
        return "money"
    if any(k in d for k in ["불꽃", "firework", "파티클", "particle", "버스트", "burst"]):
        return "particle"
    if any(k in d for k in ["글로우", "glow", "발광"]):
        return "glow"
    if any(k in d for k in ["rain", "떨어지", "낙하", "드롭", "비가"]):
        return "rain"
    return "generic"


def generate_custom_fx_component(effect: dict, fx_dir: Path) -> dict:
    """
    effect.description 분석 → TSX 컴포넌트 생성.
    Returns: {componentName, fileName, defaultProps, templateKey}
    """
    fx_dir.mkdir(parents=True, exist_ok=True)
    tkey           = _pick_fx_template(effect.get("description", ""))
    tmpl           = _FX_TEMPLATES[tkey]
    component_name = tmpl["componentName"]
    out_path       = fx_dir / f"{component_name}.tsx"

    # 충돌 방지
    if out_path.exists():
        for n in range(2, 99):
            candidate = fx_dir / f"{component_name}{n}.tsx"
            if not candidate.exists():
                component_name = f"{component_name}{n}"
                out_path = candidate
                break

    tsx_src = tmpl["tsx"].replace("{name}", component_name)
    out_path.write_text(tsx_src, encoding="utf-8")

    return {
        "componentName": component_name,
        "fileName":      out_path.name,
        "templateKey":   tkey,
        "defaultProps":  dict(tmpl["defaultProps"]),
        "description":   effect.get("description", ""),
    }


def update_fx_catalog(catalog_path: Path, info: dict) -> None:
    """
    fx_catalog.txt에 신규 컴포넌트 한 행 등재 (중복 방지).

    카탈로그 내 경로는 `src/components/fx/{fileName}` 으로 기술한다.
    물리적 파일은 shared_assets/shared_fx/ 에 저장되지만,
    각 프로젝트의 remotion/src/components/fx/ 는 심볼릭 링크로 연결되므로
    Remotion import 경로 관점에서는 동일하다.
    """
    text = catalog_path.read_text(encoding="utf-8") if catalog_path.exists() else ""
    if info["componentName"] in text:
        return

    props_str = " / ".join(f"`{k}`={v}" for k, v in info["defaultProps"].items())
    row = (
        f"| auto | `Custom` | `src/components/fx/{info['fileName']}` | "
        f"{info['description'][:40]} | {props_str} |"
    )
    marker = "| (비어있음 — Custom 요청 시 Python이 자동 등재) |"
    if marker in text:
        text = text.replace(marker, row)
    else:
        text += f"\n{row}\n"
    catalog_path.write_text(text, encoding="utf-8")


# ══════════════════════════════════════════════
# §5-B  Composition.tsx / Root.tsx 자동 생성
# ══════════════════════════════════════════════

# NOTE: _FX_KEYWORD_MAP 및 _resolve_custom_component() 는 제거됨 (2026-04).
# Custom FX 매칭은 SemanticMatchWorker(Gemini 기반)가 담당하며,
# "_componentName" 필드가 plan에 역주입된 후 _build_slide_tsx()가 읽는다.

# ── 하위 호환을 위해 남아있는 임시 심볼 (사용하지 않음) ────────────
# 아무 키워드도 없이 제거하면 기존 import가 깨질 수 있어 빈 dict 유지
_FX_KEYWORD_MAP: dict[str, list[str]] = {
    "golden": ["황금", "골든", "golden"],
    "ray":    ["빛줄기", "광선", "ray", "beam", "light"],
    "money":  ["동전", "돈", "코인", "money", "coin"],
    "rain":   ["비", "떨어지", "낙하", "rain", "fall", "drop"],
    "fire":   ["불꽃", "화염", "fire", "flame"],
    "glow":   ["발광", "글로우", "glow", "shine", "아우라"],
    "particle": ["파티클", "먼지", "particle", "dust", "sparkle"],
    "confetti": ["색종이", "confetti"],
    "snow":   ["눈", "설", "snow"],
    # 원유/오일 계열
    "oil":    ["원유", "석유", "기름", "oil", "petroleum", "crude"],
    "fill":   ["차오르", "가득", "채워", "홀로그램", "fill", "rising", "level", "flow"],
    "leak":   ["유출", "흘러", "누출", "증발", "파티클이", "leak", "spill", "escape", "evaporate"],
    # 기타 UI FX
    "warning": ["경고", "위험", "주의", "알람", "warning", "danger", "alert"],
    "underline": ["밑줄", "강조선", "underline"],
    "highlight": ["하이라이트", "형광", "highlight"],
    "typewriter": ["타이핑", "타자기", "typewriter"],
    "blur":   ["블러", "흐림", "blur", "reveal"],
    "progress": ["진행", "progress"],
    "bar":    ["막대", "차트", "bar", "chart"],
    "count":  ["카운트", "숫자", "count", "counter"],
    "vignette": ["비네트", "vignette"],
    "flash":  ["번쩍", "플래시", "flash"],
    "focus":  ["초점", "포커스", "focus", "ring"],
    "screen": ["화면", "스크린", "screen"],
    "change": ["변화", "증감", "change", "indicator"],
    "data":   ["데이터", "수치", "data", "label"],
}


# _resolve_custom_component() 는 2026-04에 제거됨.
# 대체: SemanticMatchWorker (Gemini 기반 시맨틱 매칭) → _componentName 역주입 후
#       _build_slide_tsx() 에서 eff["_componentName"] 직접 읽음.


import re as _re


# ──────────────────────────────────────────────────────────────
# §5-B 헬퍼: 슬라이드 그룹핑 / 배경이미지 / 자막 구간 추출
# ──────────────────────────────────────────────────────────────

def _group_effects_by_slide(effects: list[dict]) -> dict[str, list[dict]]:
    """
    effect ID에서 슬라이드 prefix를 추출하여 그룹핑.
      예) p1_1_txt, p1_2_fx, p1_3_txt  →  {"p1": [...]}
    Video 타입은 Composition 대상이 아니므로 제외.
    정렬: p1, p2, p3 … (자릿수 → 이름 순)
    """
    groups: dict[str, list[dict]] = {}
    for eff in effects:
        if eff.get("type") == "Video":
            continue
        eid = eff.get("id", "")
        m = _re.match(r'^(p\d+)', eid)
        slide = m.group(1) if m else "misc"
        groups.setdefault(slide, []).append(eff)
    return dict(sorted(groups.items(), key=lambda x: (len(x[0]), x[0])))


def _find_background_image(
    slide_id: str,
    asset_dir: Path,
    public_dir: Path | None = None,
) -> str | None:
    """
    슬라이드 번호(p1→1)에 대응하는 배경 이미지 파일명 반환.
    public_dir이 주어지면 remotion/public/ 으로 자동 복사한다.
    (Remotion <Img>는 public/ 기준으로 경로를 해석)
    """
    m = _re.match(r'^p(\d+)$', slide_id)
    if not m:
        return None
    n = m.group(1)
    for ext in (".jpeg", ".jpg", ".png", ".webp"):
        src = asset_dir / f"image_{n}{ext}"
        if src.exists():
            fname = f"image_{n}{ext}"
            if public_dir is not None:
                public_dir.mkdir(parents=True, exist_ok=True)
                dest = public_dir / fname
                if not dest.exists():
                    shutil.copy2(str(src), str(dest))
            return fname
    return None


def _load_timeline(timeline_path: Path | None) -> list[dict]:
    """base_timeline.json 로드. 항목 형식: {start, end, text}"""
    if not timeline_path or not timeline_path.exists():
        return []
    try:
        data = json.loads(timeline_path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _get_subtitles_for_range(
    timeline: list[dict],
    slide_start_frame: int,
    slide_end_frame: int,
    fps: int,
) -> list[dict]:
    """
    슬라이드 절대 프레임 구간에 해당하는 자막을 로컬 프레임 기준으로 변환하여 반환.
    반환 형식: [{startFrame, endFrame, text}, ...]
    """
    s_sec = slide_start_frame / fps
    e_sec = slide_end_frame   / fps
    result = []
    for entry in timeline:
        t_start = float(entry.get("start", entry.get("startTime", 0)))
        t_end   = float(entry.get("end",   entry.get("endTime",   t_start + 1)))
        text    = str(entry.get("text", "")).strip()
        if not text or t_end <= s_sec or t_start >= e_sec:
            continue
        local_s = max(0, round((t_start - s_sec) * fps))
        local_e = max(local_s + 1, round((t_end   - s_sec) * fps))
        result.append({"startFrame": local_s, "endFrame": local_e, "text": text})
    return result


# ── FX props 병합 헬퍼 ──────────────────────────────────────────────────────

# Popup 전용 key — FX 컴포넌트에 전달하지 않는다.
# width/height 는 OilFillFX 등 FX 컴포넌트도 사용하므로 제외하지 않음.
_POPUP_ONLY_KEYS = frozenset({"src", "maxHeight"})


def _merge_fx_props(eff: dict) -> dict:
    """
    effect 객체에서 FX 컴포넌트에 전달할 props dict 를 구성한다.

    우선순위 (낮음 → 높음):
      commonProps 전체 (Popup 전용 key 제외)
        → specificProps 전체
          → 최상위 'text' 필드 (Gemini가 Popup 형식으로 작성하는 경우 대비)

    주의: Gemini는 text/fontSize 를 commonProps 또는 최상위 레벨에 넣는 경향이 있으므로
          x·y 만 추출하던 기존 방식 대신 commonProps 전체를 포함한다.
    """
    cp = eff.get("commonProps", {})
    sp = {
        **{k: v for k, v in cp.items() if k not in _POPUP_ONLY_KEYS},
        **eff.get("specificProps", {}),
    }
    # 최상위 'text' 필드 (Gemini가 Popup 규칙 따라 상위에 놓는 경우)
    if "text" not in sp and eff.get("text"):
        sp["text"] = eff["text"]
    return sp


def _props_to_jsx(props: dict) -> str:
    """
    Python dict → JSX 인라인 props 문자열.

    repr() 대신 json.dumps()를 사용하여:
      - 문자열: "텍스트"  →  {"텍스트"}  (큰따옴표, TS 친화적)
      - 불리언: True/False  →  {true}/{false}  (JS 표기)
      - 배열: [...]  →  {[...]}  (JSON 직렬화)
      - null: None  →  {null}
    """
    parts = []
    for k, v in props.items():
        js_val = json.dumps(v, ensure_ascii=False)
        parts.append(f"{k}={{{js_val}}}")
    return " ".join(parts)


def _wrap_with_scale(inner_jsx: str, eff: dict) -> str:
    """
    FX 컴포넌트 JSX 문자열을 DynamicSlide.tsx wrapFX와 동일한 scale 래퍼 div로 감쌉니다.
    scale = commonProps.width / 400 (baseline 400px).
    cx/cy: CENTER-RELATIVE x/y → 절대 좌표 (1920/2 + x, 1080/2 + y).
    scale이 1.0에 가까우면 래퍼 없이 inner_jsx를 그대로 반환.
    """
    BASELINE_W = 400
    cp = eff.get("commonProps", {})
    w  = cp.get("width",  eff.get("width",  BASELINE_W))
    x  = cp.get("x",     eff.get("x",      0))
    y  = cp.get("y",     eff.get("y",      0))
    z  = eff.get("zIndex", 0)
    try:
        w = float(w)
    except (TypeError, ValueError):
        w = BASELINE_W
    scale = w / BASELINE_W
    if abs(scale - 1.0) < 0.001:
        return inner_jsx
    cx = 1920 / 2 + float(x)
    cy = 1080 / 2 + float(y)
    return (
        f'      <div style={{{{ position: "absolute", inset: 0,'
        f' transform: "scale({scale:.4f})",'
        f' transformOrigin: "{cx:.1f}px {cy:.1f}px",'
        f' zIndex: {z}, pointerEvents: "none" }}}}>\n'
        f'        {inner_jsx.strip()}\n'
        f'      </div>'
    )


def _build_slide_tsx(
    slide_id: str,
    effects: list[dict],
    slide_start: int,
    bg_src: str | None,
    subtitles: list[dict],
) -> str:
    """
    슬라이드 Composition TSX 코드 생성.

    구조:
      - previewMode=true  (Studio 기본): 배경이미지 + 자막 + FX
      - previewMode=false (렌더링):      FX만 (투명 배경)
    """
    imports_set: set[str] = set()
    imports_set.add('import React from "react";')
    # Img + staticFile import 는 배경이미지 블록에서 추가 (staticFile 같이 묶기 위해)
    if subtitles:
        imports_set.add(
            'import { SubtitleOverlay } from "../components/SubtitleOverlay";'
        )

    fx_lines: list[str] = []

    for eff in effects:
        etype       = eff.get("type", "Popup")
        dur_f       = eff.get("durationFrames", 60)
        abs_start   = eff.get("startFrame", 0)
        local_start = abs_start - slide_start

        if etype == "Image":
            src_img = eff.get("src", "")
            if src_img:
                imports_set.add('import { ImageElement } from "../components/ImageElement";')
                cp = eff.get("commonProps", {})
                wval = cp.get("width", "100%")
                hval = cp.get("height", "100%")
                ken_burns = eff.get("kenBurns", {})
                kb_str = json.dumps(ken_burns, ensure_ascii=False)
                fx_lines.append(
                    f'      {{previewMode && <ImageElement src="{src_img}"'
                    f' startFrame={{{local_start}}} durationFrames={{{dur_f}}}'
                    f' width="{wval}" height="{hval}" kenBurns={{{kb_str}}} />}}'
                )

        elif etype == "Popup":
            src_img = eff.get("src", "")
            text    = eff.get("text", "")
            cp      = eff.get("commonProps", {})

            if text and not src_img:
                imports_set.add(
                    'import { TextPopupElement } from "../components/TextPopupElement";'
                )
                x_val   = cp.get("x", 0)
                y_val   = cp.get("y", 0)
                fs_val  = cp.get("fontSize", "80px")
                w_val   = cp.get("width", "90%")
                escaped = text.replace("\\", "\\\\").replace('"', '\\"')
                ts      = eff.get("textStyle", {})
                ts_str  = json.dumps(ts, ensure_ascii=False)
                anim    = eff.get("animation", {})
                anim_str = json.dumps(anim, ensure_ascii=False)
                fx_lines.append(
                    f'      <TextPopupElement text="{escaped}"'
                    f' startFrame={{{local_start}}} durationFrames={{{dur_f}}}'
                    f' x={{{x_val}}} y={{{y_val}}} fontSize="{fs_val}" width="{w_val}"'
                    f' textStyle={{{ts_str}}} animation={{{anim_str}}} />'
                )
            elif src_img:
                imports_set.add(
                    'import { PopupElement } from "../components/PopupElement";'
                )
                wval = cp.get("width", "70%")
                mh   = cp.get("maxHeight", "70%")
                fx_lines.append(
                    f'      <PopupElement src="{src_img}"'
                    f' startFrame={{{local_start}}} durationFrames={{{dur_f}}}'
                    f' width="{wval}" maxHeight="{mh}" />'
                )

        elif etype == "Custom":
            # 시맨틱 매칭이 완료된 경우에만 _componentName이 주입되어 있음.
            # 매칭 미완료 시 해당 효과를 건너뜀 (경고 출력).
            cn = eff.get("_componentName", "").strip()
            if not cn:
                print(
                    f"[WARN] Custom FX '{eff.get('id')}' has no _componentName — skipped"
                )
                continue
            fn  = eff.get("_componentFile", f"{cn}.tsx").replace(".tsx", "")
            sp  = _merge_fx_props(eff)
            p_s = _props_to_jsx(sp)
            imports_set.add(f'import {{ {cn} }} from "../components/fx/{fn}";')
            inner = (
                f'<{cn} startFrame={{{local_start}}}'
                f' durationFrames={{{dur_f}}} {p_s} />'
            )
            fx_lines.append(_wrap_with_scale(f'      {inner}', eff))

        elif (SHARED_FX_DIR / f"{etype}.tsx").exists():
            # type = 컴포넌트명 직접 지정 (예: "GoldenRayFX", "HighlighterFX")
            # fx_catalog.txt에 등록된 기존 효과를 Gemini가 이름으로 직접 참조하는 경우
            cn  = etype
            fn  = etype
            sp  = _merge_fx_props(eff)
            p_s = _props_to_jsx(sp)
            imports_set.add(f'import {{ {cn} }} from "../components/fx/{fn}";')
            inner = (
                f'<{cn} startFrame={{{local_start}}}'
                f' durationFrames={{{dur_f}}} {p_s} />'
            )
            fx_lines.append(_wrap_with_scale(f'      {inner}', eff))

    cname    = f"Slide_{slide_id}"
    subs_str = json.dumps(subtitles, ensure_ascii=False)

    # 배경이미지 import — sorted_imports 생성 전에 추가해야 반영됨
    if bg_src:
        imports_set.add('import { Img, staticFile } from "remotion";')

    # import 정렬: React → Remotion → 컴포넌트 순
    sorted_imports = sorted(imports_set, key=lambda s: (
        0 if 'from "react"' in s else
        1 if 'from "remotion"' in s else
        2
    ))

    lines: list[str] = []
    lines += sorted_imports
    lines.append("")
    lines.append("interface Props { previewMode?: boolean; }")
    lines.append("")
    lines.append(f"export const {cname}: React.FC<Props> = ({{ previewMode = false }}) => (")
    lines.append(
        '  <div style={{ position: "relative", width: "100%",'
        ' height: "100%", background: "transparent" }}>'
    )

    # 배경이미지 (미리보기 전용)
    # staticFile() 사용 → Remotion 4.x dev-server 정적 자산 경로 자동 해석
    has_image_effect = any(e.get("type") == "Image" for e in effects)
    if bg_src and not has_image_effect:
        lines.append("    {previewMode && (")
        lines.append(f'      <Img src={{staticFile("{bg_src}")}} style={{{{')
        lines.append(
            '        position: "absolute", top: 0, left: 0,'
            ' width: "100%", height: "100%",'
            ' objectFit: "cover" as const, opacity: 0.85,'
        )
        lines.append("      }} />")
        lines.append("    )}")

    # FX 레이어 (항상)
    lines += fx_lines

    # 자막 (미리보기 전용)
    if subtitles:
        lines.append(f"    {{previewMode && <SubtitleOverlay subtitles={{{subs_str}}} />}}")

    lines.append("  </div>")
    lines.append(");")

    return "\n".join(lines) + "\n"


def generate_compositions(
    plan: dict,
    remotion_dir: Path,
    timeline_path: Path | None = None,
) -> None:
    """
    remotion_plan.json → 슬라이드별 Composition 생성.

    각 슬라이드 Composition (VividSlide-p1 등):
      - defaultProps.previewMode=true  → Studio에서 배경이미지+자막+FX 전체 미리보기
      - 렌더링 시 previewMode=false 전달 → 투명 배경, FX만 출력
    """
    fps     = plan.get("fps", 30)
    w       = plan.get("width", 1920)
    h       = plan.get("height", 1080)
    effects = plan.get("effects", [])

    asset_dir = remotion_dir.parent / "asset"

    # Video 타입 파일 → remotion/public/ 복사 (기존 동작 유지)
    for eff in effects:
        if eff.get("type") == "Video":
            src_name = eff.get("src", "")
            if src_name:
                resolved = resolve_asset(src_name, asset_dir)
                if resolved:
                    pub = remotion_dir / "public"
                    pub.mkdir(parents=True, exist_ok=True)
                    dest = pub / src_name
                    if not dest.exists():
                        shutil.copy2(str(resolved), str(dest))

    # 슬라이드 그룹핑
    slides   = _group_effects_by_slide(effects)
    timeline = _load_timeline(timeline_path)

    comp_dir = remotion_dir / "src" / "compositions"
    comp_dir.mkdir(parents=True, exist_ok=True)

    root_imports: list[str] = []
    root_comps:   list[str] = []

    for slide_id, slide_effs in slides.items():
        # 슬라이드 절대 프레임 범위
        slide_start = min(e.get("startFrame", 0) for e in slide_effs)
        slide_end   = max(
            e.get("startFrame", 0) + e.get("durationFrames", 60)
            for e in slide_effs
        )
        slide_dur = slide_end - slide_start

        # 배경이미지 (asset/ → remotion/public/ 자동 복사)
        public_dir = remotion_dir / "public"
        bg_src     = _find_background_image(slide_id, asset_dir, public_dir)
        subtitles  = _get_subtitles_for_range(timeline, slide_start, slide_end, fps)

        # TSX 생성
        tsx = _build_slide_tsx(
            slide_id=slide_id,
            effects=slide_effs,
            slide_start=slide_start,
            bg_src=bg_src,
            subtitles=subtitles,
        )
        cname = f"Slide_{slide_id}"
        (comp_dir / f"{cname}.tsx").write_text(tsx, encoding="utf-8")

        # Remotion 4.x: ID에 언더스코어 불가 → 하이픈 치환
        comp_id = f"VividSlide-{slide_id.replace('_', '-')}"
        root_imports.append(f'import {{ {cname} }} from "./compositions/{cname}";')
        root_comps.append(
            f'    <Composition id="{comp_id}" component={{{cname}}}'
            f' durationInFrames={{{slide_dur}}} fps={{{fps}}}'
            f' width={{{w}}} height={{{h}}}'
            f' defaultProps={{{{ previewMode: true }}}} />'
        )

    # Root.tsx / index.ts 생성
    root_src = (
        'import React from "react";\n'
        'import { Composition } from "remotion";\n'
        + "\n".join(root_imports) + "\n\n"
        "export const RemotionRoot: React.FC = () => (\n  <>\n"
        + "\n".join(root_comps) + "\n"
        "  </>\n);\n"
    )
    (remotion_dir / "src" / "Root.tsx").write_text(root_src, encoding="utf-8")
    (remotion_dir / "src" / "index.ts").write_text(
        'import { registerRoot } from "remotion";\n'
        'import { RemotionRoot } from "./Root";\n'
        "registerRoot(RemotionRoot);\n",
        encoding="utf-8",
    )


# ══════════════════════════════════════════════
# §6  스마트 Diff Check
# ══════════════════════════════════════════════

def _effect_hash(effect: dict) -> str:
    raw = json.dumps(effect, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def diff_check_effects(
    cache_path: Path,
    new_plan: dict,
) -> tuple[list[str], dict[str, str]]:
    """
    render_cache.json 과 비교해 변경된 effect id 목록 반환.
    Returns: (changed_ids, new_cache_dict)
    """
    effects   = new_plan.get("effects", [])
    new_cache = {e["id"]: _effect_hash(e) for e in effects}

    if not cache_path.exists():
        return ([e["id"] for e in effects], new_cache)

    old_cache: dict[str, str] = json.loads(cache_path.read_text(encoding="utf-8"))
    changed = [eid for eid, h in new_cache.items() if old_cache.get(eid) != h]
    return (changed, new_cache)


def save_render_cache(cache_path: Path, cache: dict[str, str]) -> None:
    cache_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")


# ══════════════════════════════════════════════
# §7  Vrew 프로젝트 조립
# ══════════════════════════════════════════════

def _random_track_id() -> str:
    """Vrew 스타일 10자 랜덤 ID"""
    import random as _r
    chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
    return "".join(_r.choices(chars, k=10))


def _compute_clip_timings(transcript_clips: list) -> list[dict]:
    """word.duration 합산으로 각 clip의 [start, end) 초 계산"""
    result: list[dict] = []
    t = 0.0
    for cl in transcript_clips:
        dur = sum(w.get("duration", 0.0) for w in cl.get("words", []))
        result.append({"clip_id": cl["id"], "start": round(t, 4),
                       "end": round(t + dur, 4), "duration": round(dur, 4)})
        t += dur
    return result


def _normalize_file_paths(project: dict) -> dict:
    """
    project.json의 files[] 배열 내 절대 경로 필드를 상대 경로(파일명만)로 변환.
    Vrew가 다른 PC에서 열릴 때 절대 경로로 인한 에러를 방지.

    검사 대상 필드: filePath / localPath / sourcePath
    변환 기준: 값이 경로 구분자('/', '\\')를 포함하거나 드라이브 문자로 시작하면 → basename
    """
    PATH_FIELDS = ("filePath", "localPath", "sourcePath", "path")

    def _to_relative(val: str) -> str:
        if not isinstance(val, str):
            return val
        # 드라이브 경로(Windows) 또는 절대 경로(Unix)
        is_abs = (
            (len(val) >= 2 and val[1] == ":")   # C:\...
            or val.startswith("/")               # /home/...
            or ("\\" in val and len(val) > 3)    # 역슬래시 포함
        )
        if is_abs:
            return Path(val).name               # 파일명만 추출
        return val

    for file_entry in project.get("files", []):
        if not isinstance(file_entry, dict):
            continue
        for field in PATH_FIELDS:
            if field in file_entry:
                file_entry[field] = _to_relative(file_entry[field])

    return project


def assemble_vrew(
    asset_dir: Path,
    plan: dict,
    renders_dir: Path,
    fps: int = 30,
) -> Path:
    """
    규칙:
      1) 원본.vrew 직접 수정 금지 → 최종_vN.vrew로 복제
      2) 렌더링된 .webm 파일을 media/ 에 삽입
      3) project.json 에 files / tracks / assets 등록
      4) 클립 타이밍 기반으로 올바른 clip.assetIds 에 연결
      5) 기존 files[] 절대 경로 → 상대 경로 자동 정규화 (무결성 강화)
    """
    # ── 원본 .vrew 탐색 ──
    vrew_files = sorted(asset_dir.glob("*.vrew"))
    # 최종_v*.vrew 제외, 원본 우선
    originals  = [f for f in vrew_files if not f.stem.startswith("최종_")]
    if not originals:
        raise FileNotFoundError("asset 폴더에 원본.vrew 파일이 없습니다.")
    vrew_src = originals[0]

    # ── 출력 버전 결정 ──
    v = 0
    while (asset_dir / f"최종_v{v}.vrew").exists():
        v += 1
    out_path = asset_dir / f"최종_v{v}.vrew"

    # ── project.json 로드 + 경로 정규화 ──
    with zipfile.ZipFile(str(vrew_src), "r") as z:
        project = json.loads(z.read("project.json").decode("utf-8"))

    # 하네스: 기존 에셋 절대 경로 → 상대 경로 변환
    project = _normalize_file_paths(project)

    clips        = project["transcript"]["clips"]
    clip_timings = _compute_clip_timings(clips)
    clip_by_id   = {cl["id"]: cl for cl in clips}
    plan_fps     = plan.get("fps", fps)
    effects      = plan.get("effects", [])

    new_media_map: dict[str, Path] = {}   # mediaId → webm Path

    for eff in effects:
        eid       = eff["id"]
        webm      = renders_dir / f"{eid}.webm"
        if not webm.exists():
            continue

        start_sec = eff.get("startFrame", 0) / plan_fps
        dur_sec   = eff.get("durationFrames", 60) / plan_fps
        media_id  = str(uuid.uuid4())
        track_id  = _random_track_id()
        asset_id  = str(uuid.uuid4())

        # 클립 타이밍 매칭
        target_clip_id = None
        for ct in clip_timings:
            if ct["start"] <= start_sec < ct["end"]:
                target_clip_id = ct["clip_id"]
                break
        if target_clip_id is None and clip_timings:
            target_clip_id = clip_timings[-1]["clip_id"]

        # files[] 등록
        project["files"].append({
            "version": 1, "mediaId": media_id, "sourceOrigin": "USER",
            "fileSize": webm.stat().st_size, "name": f"{media_id}.webm",
            "type": "AVMedia",
            "videoAudioMetaInfo": {
                "duration": round(dur_sec, 3),
                "videoInfo": {"codec": "vp8", "frameRate": plan_fps},
            },
            "sourceFileType": "VIDEO_ONLY", "fileLocation": "IN_MEMORY",
        })

        # tracks{} 등록
        project["props"]["tracks"][track_id] = {
            "trackId": track_id, "mediaId": media_id,
            "xPos": 0.0, "yPos": 0.0, "height": 1.0, "width": 1.0,
            "rotation": 0, "zIndex": 200 + v,
            "type": "video", "sourceIn": 0, "sourceOut": round(dur_sec, 3),
            "hasAlphaChannel": True, "isTrimmable": True,
            "editInfo": {}, "fillType": "cut",
        }

        # assets{} 등록
        project["props"]["assets"][asset_id] = {
            "trackIds": [track_id], "role": "sub",
        }

        # clip.assetIds 연결
        if target_clip_id and target_clip_id in clip_by_id:
            clip_by_id[target_clip_id]["assetIds"].append(asset_id)

        new_media_map[media_id] = webm

    # ── Video 타입 효과 (bumper, intro 등) → Vrew 직접 삽입 ──
    # resolve_asset() 으로 asset/ 우선 탐색, 없으면 shared_assets/ fallback
    new_video_map: dict[str, tuple[Path, str]] = {}  # mediaId → (file_path, archive_ext)

    for eff in effects:
        if eff.get("type") != "Video":
            continue

        src_name = eff.get("src", "")
        if not src_name:
            continue

        video_file = resolve_asset(src_name, asset_dir)
        if not video_file:
            continue  # 어느 폴더에도 없으면 건너뜀

        start_sec = eff.get("startFrame", 0) / plan_fps
        dur_sec   = eff.get("durationFrames", 90) / plan_fps
        media_id  = str(uuid.uuid4())
        track_id  = _random_track_id()
        asset_id  = str(uuid.uuid4())
        ext       = video_file.suffix.lower()   # .mp4 / .mov 등

        # 클립 타이밍 매칭
        target_clip_id = None
        for ct in clip_timings:
            if ct["start"] <= start_sec < ct["end"]:
                target_clip_id = ct["clip_id"]
                break
        if target_clip_id is None and clip_timings:
            target_clip_id = clip_timings[-1]["clip_id"]

        # files[] 등록 (불투명 전체화면 영상)
        project["files"].append({
            "version": 1, "mediaId": media_id, "sourceOrigin": "USER",
            "fileSize": video_file.stat().st_size,
            "name": f"{media_id}{ext}",
            "type": "AVMedia",
            "videoAudioMetaInfo": {
                "duration": round(dur_sec, 3),
                "videoInfo": {"codec": "h264", "frameRate": plan_fps},
            },
            "sourceFileType": "VIDEO", "fileLocation": "IN_MEMORY",
        })

        # tracks{} 등록 (hasAlphaChannel=False, zIndex=10 — 메인 레이어)
        project["props"]["tracks"][track_id] = {
            "trackId": track_id, "mediaId": media_id,
            "xPos": 0.0, "yPos": 0.0, "height": 1.0, "width": 1.0,
            "rotation": 0, "zIndex": 10,
            "type": "video", "sourceIn": 0, "sourceOut": round(dur_sec, 3),
            "hasAlphaChannel": False, "isTrimmable": True,
            "editInfo": {}, "fillType": "cut",
        }

        # assets{} 등록
        project["props"]["assets"][asset_id] = {
            "trackIds": [track_id], "role": "sub",
        }

        # clip.assetIds 연결
        if target_clip_id and target_clip_id in clip_by_id:
            clip_by_id[target_clip_id]["assetIds"].append(asset_id)

        new_video_map[media_id] = (video_file, ext)

    # ── ZIP 재조립 ──
    with zipfile.ZipFile(str(vrew_src), "r") as z_in:
        with zipfile.ZipFile(str(out_path), "w", zipfile.ZIP_DEFLATED) as z_out:
            for item in z_in.infolist():
                if item.filename == "project.json":
                    continue
                z_out.writestr(item, z_in.read(item.filename))

            z_out.writestr(
                "project.json",
                json.dumps(project, ensure_ascii=False, separators=(",", ":")),
            )
            # 투명 오버레이 .webm
            for mid, wp in new_media_map.items():
                z_out.write(str(wp), f"media/{mid}.webm")
            # 불투명 Video 클립 (.mp4 등 — bumper, intro)
            for mid, (vp, ext) in new_video_map.items():
                z_out.write(str(vp), f"media/{mid}{ext}")

    return out_path


# ══════════════════════════════════════════════
# §8  HyperFrames Vrew 조립
# ══════════════════════════════════════════════

def _get_mp4_duration(mp4_path: Path) -> float:
    """ffprobe로 mp4 재생 시간(초) 추출."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error",
             "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1",
             str(mp4_path)],
            capture_output=True, text=True, timeout=10,
            **_HIDDEN_SH,
        )
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def assemble_vrew_hf(
    asset_dir: Path,
    timeline: list[dict],   # noqa: ARG001 — Phase 3에서 슬라이드-그룹 타이밍 정렬에 활용 예정
    renders_dir: Path,
    fps: int = 30,
) -> Path:
    """
    HyperFrames 렌더된 .mp4 슬라이드들을 Vrew 파일에 조립.

    assemble_vrew()와의 차이:
      - 입력: renders_dir 내 slide_NN.mp4 (slides 기반, effects[] 아님)
      - codec: h264 / hasAlphaChannel: False / zIndex: 10
      - 버전 파일명: 최종_hf_vN.vrew
      - 슬라이드 타이밍: ffprobe duration 누적 계산
    """
    # ── 원본 .vrew 탐색 ──
    vrew_files = sorted(asset_dir.glob("*.vrew"))
    originals  = [f for f in vrew_files if not f.stem.startswith("최종_")]
    if not originals:
        raise FileNotFoundError("asset 폴더에 원본.vrew 파일이 없습니다.")
    vrew_src = originals[0]

    # ── 출력 버전 결정 ──
    v = 0
    while (asset_dir / f"최종_hf_v{v}.vrew").exists():
        v += 1
    out_path = asset_dir / f"최종_hf_v{v}.vrew"

    # ── project.json 로드 + 경로 정규화 ──
    with zipfile.ZipFile(str(vrew_src), "r") as z:
        project = json.loads(z.read("project.json").decode("utf-8"))
    project = _normalize_file_paths(project)

    clips        = project["transcript"]["clips"]
    clip_timings = _compute_clip_timings(clips)
    clip_by_id   = {cl["id"]: cl for cl in clips}

    # ── slide_NN.mp4 파일 목록 정렬 ──
    mp4_files = sorted(renders_dir.glob("slide_*.mp4"), key=lambda p: p.stem)

    new_mp4_map: dict[str, Path] = {}   # mediaId → mp4 Path

    cumulative_sec = 0.0
    for mp4 in mp4_files:
        dur_sec   = _get_mp4_duration(mp4)
        start_sec = cumulative_sec
        cumulative_sec += dur_sec

        media_id = str(uuid.uuid4())
        track_id = _random_track_id()
        asset_id = str(uuid.uuid4())

        # 클립 타이밍 매칭
        target_clip_id = None
        for ct in clip_timings:
            if ct["start"] <= start_sec < ct["end"]:
                target_clip_id = ct["clip_id"]
                break
        if target_clip_id is None and clip_timings:
            target_clip_id = clip_timings[-1]["clip_id"]

        # files[] 등록
        project["files"].append({
            "version": 1, "mediaId": media_id, "sourceOrigin": "USER",
            "fileSize": mp4.stat().st_size, "name": f"{media_id}.mp4",
            "type": "AVMedia",
            "videoAudioMetaInfo": {
                "duration": round(dur_sec, 3),
                "videoInfo": {"codec": "h264", "frameRate": fps},
            },
            "sourceFileType": "VIDEO_ONLY", "fileLocation": "IN_MEMORY",
        })

        # tracks{} 등록
        project["props"]["tracks"][track_id] = {
            "trackId": track_id, "mediaId": media_id,
            "xPos": 0.0, "yPos": 0.0, "height": 1.0, "width": 1.0,
            "rotation": 0, "zIndex": 10,
            "type": "video", "sourceIn": 0, "sourceOut": round(dur_sec, 3),
            "hasAlphaChannel": False, "isTrimmable": True,
            "editInfo": {}, "fillType": "cut",
        }

        # assets{} 등록
        project["props"]["assets"][asset_id] = {
            "trackIds": [track_id], "role": "sub",
        }

        # clip.assetIds 연결
        if target_clip_id and target_clip_id in clip_by_id:
            clip_by_id[target_clip_id]["assetIds"].append(asset_id)

        new_mp4_map[media_id] = mp4

    # ── ZIP 재조립 ──
    with zipfile.ZipFile(str(vrew_src), "r") as z_in:
        with zipfile.ZipFile(str(out_path), "w", zipfile.ZIP_DEFLATED) as z_out:
            for item in z_in.infolist():
                if item.filename == "project.json":
                    continue
                z_out.writestr(item, z_in.read(item.filename))
            z_out.writestr(
                "project.json",
                json.dumps(project, ensure_ascii=False, separators=(",", ":")),
            )
            for mid, mp4_path in new_mp4_map.items():
                z_out.write(str(mp4_path), f"media/{mid}.mp4")

    return out_path
