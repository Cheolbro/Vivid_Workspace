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
import uuid
import zipfile
from pathlib import Path

from utils.theme import SHARED_ASSETS_DIR

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
    """fx_catalog.md에 신규 컴포넌트 한 행 등재 (중복 방지)"""
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

def generate_compositions(plan: dict, remotion_dir: Path) -> None:
    """
    remotion_plan.json → Root.tsx + src/compositions/FX_<id>.tsx 생성.
    각 FX 항목은 독립 Composition (VividFX_<id>)으로 분리 렌더링 가능.
    """
    fps     = plan.get("fps", 30)
    w       = plan.get("width", 1920)
    h       = plan.get("height", 1080)
    effects = plan.get("effects", [])

    comp_dir = remotion_dir / "src" / "compositions"
    comp_dir.mkdir(parents=True, exist_ok=True)

    imports:  list[str] = []
    comp_els: list[str] = []

    for eff in effects:
        eid      = eff["id"]
        etype    = eff.get("type", "Popup")
        dur_f    = eff.get("durationFrames", 60)
        cname    = f"Comp_{eid}"
        comp_id  = f"VividFX_{eid}"

        if etype == "Popup":
            src_img   = eff.get("src", "")
            cp        = eff.get("commonProps", {})
            wval      = cp.get("width", "70%")
            mh        = cp.get("maxHeight", "70%")
            body = (
                f'  <PopupElement src="{src_img}" startFrame={{0}}'
                f' durationFrames={{{dur_f}}} width="{wval}" maxHeight="{mh}" />'
            )
            import_line = 'import { PopupElement } from "../components/PopupElement";'
            tsx = (
                'import React from "react";\n'
                f'{import_line}\n\n'
                f'export const {cname}: React.FC = () => (\n'
                f'  <div style={{{{ position:"relative", width:"100%", height:"100%", background:"transparent" }}}}>\n'
                f'{body}\n  </div>\n);\n'
            )

        elif etype == "Custom":
            cn   = eff.get("_componentName", "OverlayFX")
            fn   = eff.get("_componentFile", f"{cn}.tsx").replace(".tsx", "")
            sp   = eff.get("specificProps", {})
            p_str = " ".join(f'{k}={{{repr(v)}}}' for k, v in sp.items())
            body  = f'  <{cn} startFrame={{0}} durationFrames={{{dur_f}}} {p_str} />'
            tsx = (
                'import React from "react";\n'
                f'import {{ {cn} }} from "../components/fx/{fn}";\n\n'
                f'export const {cname}: React.FC = () => (\n'
                f'  <div style={{{{ position:"relative", width:"100%", height:"100%", background:"transparent" }}}}>\n'
                f'{body}\n  </div>\n);\n'
            )

        elif etype == "Video":
            # Video 타입(bumper, intro 등)은 투명 오버레이가 아니므로
            # Remotion Composition을 별도 생성하지 않는다.
            # 단, Remotion Studio 미리보기를 위해 파일을 public/ 에 복사한다.
            src_name = eff.get("src", "")
            if src_name:
                asset_dir = remotion_dir.parent / "asset"
                resolved  = resolve_asset(src_name, asset_dir)
                if resolved:
                    public_dir = remotion_dir / "public"
                    public_dir.mkdir(parents=True, exist_ok=True)
                    dest_pub = public_dir / src_name
                    if not dest_pub.exists():
                        shutil.copy2(str(resolved), str(dest_pub))
            continue   # Composition/Root.tsx 에는 등재하지 않음

        else:
            continue

        (comp_dir / f"FX_{eid}.tsx").write_text(tsx, encoding="utf-8")
        imports.append(f'import {{ {cname} }} from "./compositions/FX_{eid}";')
        comp_els.append(
            f'    <Composition id="{comp_id}" component={{{cname}}}'
            f' durationInFrames={{{dur_f}}} fps={{{fps}}} width={{{w}}} height={{{h}}} />'
        )

    root_src = (
        'import React from "react";\n'
        'import { Composition } from "remotion";\n'
        + "\n".join(imports) + "\n\n"
        'export const RemotionRoot: React.FC = () => (\n  <>\n'
        + "\n".join(comp_els) + "\n"
        '  </>\n);\n'
    )
    (remotion_dir / "src" / "Root.tsx").write_text(root_src, encoding="utf-8")
    (remotion_dir / "src" / "index.ts").write_text(
        'import { registerRoot } from "remotion";\n'
        'import { RemotionRoot } from "./Root";\n'
        'registerRoot(RemotionRoot);\n',
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
