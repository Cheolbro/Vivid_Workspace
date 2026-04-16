"""
utils/editor_server.py
VIVID Studio — FastAPI 브릿지 서버 (port 8000)

역할:
  • GET  /api/plan      — remotion_plan.json 반환
  • POST /api/plan      — 검증 → 백업 → 파일 덮어쓰기 → touch (Remotion 캐시 무효화)
  • GET  /api/timeline  — base_timeline.json 반환
  • GET  /api/fx-catalog — fx_catalog.txt 파싱 결과 반환 (Phase 3 동적 UI용)
  • GET  /api/status    — 서버 헬스체크 + 현재 project_dir
  • Static /            — editor/ 폴더의 정적 파일 서빙 (React 빌드 산출물)

실행 방법 (step4.py에서 daemon 스레드로 호출):
  from utils.editor_server import start_server
  threading.Thread(target=start_server, args=(project_dir,), daemon=True).start()
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import shutil

from fastapi import FastAPI, HTTPException, Request
from utils.backend_ext import generate_compositions
from utils.theme import SHARED_FX_DIR
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# ── 모듈 레벨 상태 ──────────────────────────────────────────────────────────
_project_dir: Path | None = None

# editor/ 정적 파일 루트 (Project_templete/remotion/editor/)
_EDITOR_DIR: Path = (
    Path(__file__).parent.parent        # workspace root
    / "Project_templete" / "remotion" / "editor"
)

# ── FastAPI 앱 ───────────────────────────────────────────────────────────────
app = FastAPI(title="VIVID Studio Bridge", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 유틸 ────────────────────────────────────────────────────────────────────

def _plan_path() -> Path:
    if _project_dir is None:
        raise HTTPException(status_code=503, detail="프로젝트가 선택되지 않았습니다.")
    p = _project_dir / "asset" / "remotion_plan.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"remotion_plan.json 없음: {p}")
    return p


def _timeline_path() -> Path:
    if _project_dir is None:
        raise HTTPException(status_code=503, detail="프로젝트가 선택되지 않았습니다.")
    p = _project_dir / "asset" / "base_timeline.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"base_timeline.json 없음: {p}")
    return p


def _next_backup_path(plan_p: Path) -> Path:
    """remotion_plan_v0.json, v1.json ... 순차 증가 백업 경로 반환"""
    parent = plan_p.parent
    idx = 0
    while True:
        candidate = parent / f"remotion_plan_v{idx}.json"
        if not candidate.exists():
            return candidate
        idx += 1


def _touch(path: Path) -> None:
    """파일 mtime을 현재 시각으로 갱신 → Remotion 핫리로드 트리거"""
    path.touch()


def _flat_to_slides(plan: dict) -> dict:
    """
    remotion_plan.json의 flat effects 배열 → VIVID Studio용 slides 구조 변환.
    - Video 타입(intro/bumper) 제외
    - effect ID prefix (p1, p2, p3...) 기준으로 그룹핑
    - 배경 이미지: Popup 타입 + src 필드에서 추출
    """
    effects = plan.get("effects", [])
    groups: dict[str, list] = {}

    for eff in effects:
        if eff.get("type") == "Video":
            continue  # 인트로/범퍼 영상은 편집 대상 제외
        eid = eff.get("id", "")
        m = re.match(r"^(p\d+)", eid)
        slide_id = m.group(1) if m else "misc"
        groups.setdefault(slide_id, []).append(eff)

    # p1, p2, p3 … 자릿수→이름 순 정렬
    sorted_groups = sorted(groups.items(), key=lambda x: (len(x[0]), x[0]))

    slides = []
    for slide_id, slide_effs in sorted_groups:
        starts = [e.get("startFrame", 0) for e in slide_effs]
        ends   = [e.get("startFrame", 0) + e.get("durationFrames", 0) for e in slide_effs]
        dur    = (max(ends) - min(starts)) if ends else 0
        # 배경 이미지: Popup 타입의 src(최상위 또는 props.src)에서 파일명만 추출
        def _extract_src(e: dict) -> str:
            return e.get("src") or (e.get("props") or {}).get("src") or ""

        raw_bg = next(
            (_extract_src(e) for e in slide_effs if _extract_src(e) and e.get("type") == "Popup"),
            "",
        )
        bg = Path(raw_bg).name if raw_bg else None
        slides.append({
            "id": slide_id,
            "durationFrames": dur,
            "backgroundImage": bg,
            "effects": slide_effs,
        })

    result = {k: v for k, v in plan.items() if k != "effects"}
    result["slides"] = slides
    return result


def _slides_to_flat(plan: dict) -> dict:
    """slides 구조 → flat effects 역변환 (파일 저장용)"""
    if "slides" not in plan:
        return plan  # 이미 flat 포맷
    slides  = plan.get("slides", [])
    effects = []
    for slide in slides:
        effects.extend(slide.get("effects", []))
    result = {k: v for k, v in plan.items() if k != "slides"}
    result["effects"] = effects
    return result


# ── API 엔드포인트 ───────────────────────────────────────────────────────────

@app.get("/api/status")
def get_status():
    return {
        "ok": True,
        "project_dir": str(_project_dir) if _project_dir else None,
        "editor_dir": str(_EDITOR_DIR),
    }


@app.get("/api/plan")
def get_plan():
    """현재 remotion_plan.json 반환 (flat effects → slides 구조 변환)"""
    p = _plan_path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"JSON 파싱 실패: {e}")
    # flat effects → slides 구조로 변환하여 반환 (VIVID Studio UI용)
    return JSONResponse(content=_flat_to_slides(data))


@app.post("/api/plan")
async def post_plan(request: Request):
    """
    remotion_plan.json 업데이트
    1. 요청 body를 JSON 검증
    2. 기존 파일 백업 (remotion_plan_v*.json)
    3. 새 내용 덮어쓰기
    4. touch → Remotion 핫리로드 트리거
    """
    plan_p = _plan_path()

    # ── 1. 요청 body 파싱 ──────────────────────────────────────────────────
    try:
        body: Any = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"JSON 파싱 실패: {e}")

    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="최상위 구조는 JSON 객체여야 합니다.")

    # ── 2. 백업 ───────────────────────────────────────────────────────────
    backup_p = _next_backup_path(plan_p)
    try:
        import shutil
        shutil.copy2(plan_p, backup_p)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"백업 실패: {e}")

    # ── 3. 덮어쓰기 (slides → flat effects 역변환 후 저장) ────────────────
    flat_body = _slides_to_flat(body)
    try:
        plan_p.write_text(
            json.dumps(flat_body, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"파일 저장 실패: {e}")

    # ── 4. touch → 핫리로드 ───────────────────────────────────────────────
    _touch(plan_p)

    # ── 5. TSX 재생성 → Remotion 핫리로드에 편집 내용 즉시 반영 ─────────────
    if _project_dir is not None:
        remotion_dir  = _project_dir / "remotion"
        timeline_path = _project_dir / "asset" / "base_timeline.json"
        if remotion_dir.exists():
            try:
                generate_compositions(
                    flat_body,
                    remotion_dir,
                    timeline_path=timeline_path if timeline_path.exists() else None,
                )
            except Exception as e:
                # TSX 재생성 실패는 경고만 — JSON 저장 성공으로 응답은 유지
                print(f"[WARN] editor_server: TSX 재생성 실패: {e}")

    return {"ok": True, "backup": backup_p.name}


@app.get("/api/timeline")
def get_timeline():
    """base_timeline.json 반환"""
    p = _timeline_path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"JSON 파싱 실패: {e}")
    return JSONResponse(content=data)


@app.get("/api/asset/{filename:path}")
def get_asset(filename: str):
    """프로젝트 asset 폴더의 파일 서빙 (배경 이미지 등)"""
    if _project_dir is None:
        raise HTTPException(status_code=503, detail="프로젝트가 선택되지 않았습니다.")
    # 경로 순회 공격 방지: 파일명만 사용
    safe_name = Path(filename).name
    asset_path = _project_dir / "asset" / safe_name
    if not asset_path.exists():
        raise HTTPException(status_code=404, detail=f"파일 없음: {safe_name}")
    return FileResponse(str(asset_path))


@app.get("/api/fx-catalog")
def get_fx_catalog():
    """
    fx_catalog.txt 파싱 → FX 컴포넌트 목록 반환
    각 항목: { name, file, description, props: [{key, type, default}] }
    (Phase 3 동적 UI 구성용)
    """
    catalog_path = Path(__file__).parent.parent / "fx_catalog.txt"
    if not catalog_path.exists():
        return JSONResponse(content=[])

    text = catalog_path.read_text(encoding="utf-8")
    items: list[dict] = []

    # 간단한 섹션 파싱: "## FX명" 블록 단위로 추출
    sections = re.split(r"(?=^## )", text, flags=re.MULTILINE)
    for sec in sections:
        lines = sec.strip().splitlines()
        if not lines or not lines[0].startswith("## "):
            continue
        name = lines[0].lstrip("# ").strip()
        desc = ""
        file_name = ""
        props: list[dict] = []

        for line in lines[1:]:
            if line.startswith("- 파일:") or line.startswith("- file:"):
                file_name = line.split(":", 1)[-1].strip()
            elif line.startswith("- 설명:") or line.startswith("- description:"):
                desc = line.split(":", 1)[-1].strip()
            elif line.startswith("  - ") or line.startswith("    - "):
                # Props 파싱: "  - propName (type, default: val)"
                m = re.match(r"\s+-\s+(\w+)\s*\(([^)]+)\)", line)
                if m:
                    prop_name = m.group(1)
                    meta = m.group(2)
                    prop_type = meta.split(",")[0].strip()
                    default_m = re.search(r"default:\s*(.+)", meta)
                    default_val = default_m.group(1).strip() if default_m else ""
                    props.append({"key": prop_name, "type": prop_type, "default": default_val})

        if name:
            items.append({"name": name, "file": file_name, "description": desc, "props": props})

    return JSONResponse(content=items)


# ── FX 코드 미리보기 / 되돌리기 / 반영 확정 ────────────────────────────────────
#
# 흐름:
#   1. POST /api/fx/preview  → 코드 저장 + 기존 파일 .bak 백업 (Remotion 핫리로드)
#   2. POST /api/fx/revert   → .bak 복원 (되돌리기)
#   3. POST /api/fx/commit   → .bak 삭제 (반영 확정 — 이후 모든 프로젝트에 영구 적용)

def _safe_fx_name(raw: str) -> str:
    """경로 순회 방지: 파일명만 추출하고 .tsx 확장자 강제"""
    name = Path(raw).name
    if not name.endswith(".tsx"):
        name += ".tsx"
    return name


@app.post("/api/fx/preview")
async def fx_preview(request: Request):
    """
    TSX 코드를 임시 적용.
    기존 파일은 .bak으로 백업(원본 보호), 새 코드로 덮어씌움.
    Remotion dev-server가 파일 변경을 감지해 핫리로드.
    """
    body = await request.json()
    filename = _safe_fx_name(body.get("filename", ""))
    code: str = body.get("code", "")
    if not filename or not code.strip():
        raise HTTPException(status_code=400, detail="filename과 code가 필요합니다.")

    SHARED_FX_DIR.mkdir(parents=True, exist_ok=True)
    fx_path  = SHARED_FX_DIR / filename
    bak_path = SHARED_FX_DIR / (filename + ".bak")

    # 원본 백업 (이미 .bak 있으면 덮어쓰지 않음 — 원본 보호)
    if fx_path.exists() and not bak_path.exists():
        shutil.copy2(fx_path, bak_path)

    fx_path.write_text(code, encoding="utf-8")

    # Windows chokidar는 junction 타겟 직접 쓰기를 감지 못함.
    # junction 경로(remotion/src/components/fx/)를 통해 실제 write해야 watcher 트리거됨.
    if _project_dir is not None:
        junction_fx = _project_dir / "remotion" / "src" / "components" / "fx" / filename
        if junction_fx.parent.exists():
            junction_fx.write_text(code, encoding="utf-8")

    return {"ok": True, "filename": filename, "has_backup": bak_path.exists()}


@app.post("/api/fx/revert")
async def fx_revert(request: Request):
    """
    미리보기 취소 — .bak 파일로 원복.
    .bak이 없으면 원본이 없다는 뜻(신규 파일)이므로 .tsx 자체를 삭제.
    """
    body = await request.json()
    filename = _safe_fx_name(body.get("filename", ""))
    if not filename:
        raise HTTPException(status_code=400, detail="filename이 필요합니다.")

    fx_path  = SHARED_FX_DIR / filename
    bak_path = SHARED_FX_DIR / (filename + ".bak")

    if bak_path.exists():
        shutil.copy2(bak_path, fx_path)
        bak_path.unlink()
    elif fx_path.exists():
        fx_path.unlink()  # 신규 파일이었으므로 제거

    return {"ok": True, "filename": filename}


@app.post("/api/fx/commit")
async def fx_commit(request: Request):
    """
    미리보기 확정 — .bak 파일 삭제.
    현재 .tsx가 영구 적용됨. shared_fx를 심볼릭 링크로 공유하는
    모든 프로젝트에서 이후 동일 FX 이름 사용 시 새 연출로 표시됨.
    """
    body = await request.json()
    filename = _safe_fx_name(body.get("filename", ""))
    if not filename:
        raise HTTPException(status_code=400, detail="filename이 필요합니다.")

    bak_path = SHARED_FX_DIR / (filename + ".bak")
    if bak_path.exists():
        bak_path.unlink()

    return {"ok": True, "filename": filename}


# ── AI 채팅 엔드포인트 ───────────────────────────────────────────────────────

_WORKSPACE_ROOT = Path(__file__).parent.parent  # c:\Youtube\Vivid_Workspace

# ── 시각 효과 구현 전략 가이드 (FX 프롬프트 공통 첨부) ──────────────────────
_FX_IMPL_GUIDE = """\
## 시각 효과 구현 전략 가이드
사용자의 묘사를 보고 아래 기준에 따라 구현 기법을 선택하세요.
단순한 원형 div 파티클 방식은 유체/물줄기/균열 묘사에 절대 사용하지 마세요.

| 묘사 키워드 | 금지 | 권장 구현 기법 |
|---|---|---|
| 물, 물줄기, 흘러가는, 흐르는, 흐름, 흘러나옴, 液體 | 원형 div 나열 | SVG `<path>` + cubic bezier + **아래 필수 기법 2가지 적용** |
| 고임, 웅덩이, puddle | 개별 파티클 | 바닥 타원이 interpolate로 점점 퍼지는 CSS ellipse |
| 뚝뚝 떨어짐, 낙하 물방울 | 균일한 원 | 세로로 긴 물방울(border-radius 비대칭) + 포물선 궤도 |
| 균열, 틈새, 갈라짐 | 사각 div | SVG `<line>` 또는 clip-path 다각형 |
| 구멍, 공허, 블랙홀 | 단색 원 | radial-gradient(black→transparent) + box-shadow inset |
| 연기, 안개, 증기 | 선명한 원 | blur(px) 큰 타원, opacity interpolate |
| 빛줄기, 광선, 글로우 | 단색 div | radial-gradient + filter:blur + 방사형 배치 |
| 충격파, 파문, 링 | 채워진 원 | border만 있는 원 + scale spring 확장 |
| 파티클, 폭발, 방사 | (파티클은 허용) | 방향 벡터 + 중력 가속도 + size/opacity 곡선 |

### 물/흐름 계열 필수 기법 (사용자 요청에 "물", "물줄기", "흘러가는", "흐르는", "흐름" 중 하나라도 포함된 경우 반드시 적용)

**기법 1 — strokeDashoffset 흐름 애니메이션**
SVG path에 `strokeDasharray`와 `strokeDashoffset`을 사용해 줄기가 구멍에서 끝점으로 흘러가는 것처럼 보이게 한다.
```tsx
const totalLength = 400; // path 총 길이 (어림값)
const flowOffset = interpolate(rel, [0, durationFrames], [totalLength, -totalLength]);
// <path strokeDasharray={totalLength} strokeDashoffset={flowOffset} ... />
```

**기법 2 — 가장자리 sin파 흔들림**
줄기 폭(strokeWidth)이 시간에 따라 미세하게 진동해 점성 액체처럼 보이게 한다.
```tsx
const wobble = Math.sin(rel * 0.15) * 2; // ±2px 진동
// strokeWidth={baseWidth + wobble}
```
"""

# 의도별 시스템 프롬프트
_SYSTEM_FX_MODIFY = """\
당신은 Remotion TSX FX 컴포넌트 개발자입니다.

아래 순서대로 작업하세요:
1. shared_assets/shared_fx/ 폴더에서 해당 .tsx 파일을 읽고 사용자의 요청에 맞게 수정하세요.
2. fx_catalog.txt 파일을 열어 해당 FX 항목의 specificProps 기본값을 확인하세요.
   수정된 연출에 맞게 기본값 변경이 필요하면 fx_catalog.txt 도 함께 수정하세요.

{guide}

[출력 규칙] 작업 완료 후 설명 문장 없이 아래 JSON 한 개만 출력하세요:
{{"type":"tsx_code","filename":"XxxFX.tsx","code":"// 완전한 수정된 TSX 코드","summary":"변경 내용 한 줄 요약"}}
""".format(guide=_FX_IMPL_GUIDE)

_SYSTEM_FX_CREATE = """\
당신은 Remotion TSX FX 컴포넌트 개발자입니다.

아래 순서대로 작업하세요:
1. fx_catalog.txt 파일을 읽어 기존 FX 목록을 확인하고, 중복되지 않는 컴포넌트 이름을 정하세요.
2. shared_assets/shared_fx/ 폴더에서 기존 .tsx 파일 하나를 읽어 코딩 스타일과 파일 구조를 파악하세요.
3. 동일한 스타일로 새 FX 컴포넌트를 작성하세요.
   완성된 파일은 shared_assets/shared_fx/ 에 저장되며, 실제 저장은 시스템이 처리합니다.

{guide}

[출력 규칙] 작업 완료 후 설명 문장 없이 아래 JSON 한 개만 출력하세요:
{{"type":"tsx_code","filename":"XxxFX.tsx","code":"// 완전한 TSX 코드","summary":"FX 설명"}}
""".format(guide=_FX_IMPL_GUIDE)

_SYSTEM_GENERAL = """\
당신은 VIVID Studio AI 어시스턴트입니다.

[출력 규칙] 설명 문장 없이 아래 JSON 한 개만 출력하세요:
{"type":"text","content":"답변 내용"}
"""

_FX_MODIFY_KEYWORDS  = ["변경", "수정", "바꿔", "고쳐", "바꿔줘", "연출", "교체"]
_FX_CREATE_KEYWORDS  = ["만들어", "새로", "추가", "생성", "새 fx", "새fx", "신규"]


def _detect_intent(message: str) -> str:
    """키워드 기반 요청 의도 분류 → fx_modify / fx_create / general"""
    has_fx_name    = bool(re.search(r"\w+fx\b", message, re.IGNORECASE))
    has_fx_keyword = "fx" in message.lower() or "효과" in message

    if has_fx_name and any(k in message for k in _FX_MODIFY_KEYWORDS):
        return "fx_modify"
    if any(k in message for k in _FX_CREATE_KEYWORDS) and has_fx_keyword:
        return "fx_create"
    return "general"


import subprocess
import shutil

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[mGKHF]")

# node.exe + gemini entry.js 경로 캐시 (프로세스당 1회 탐색)
_gemini_node_cmd_cache: list[str] | None = None


def _find_gemini_exe() -> str:
    """
    gemini CLI 실행파일 경로를 반환한다.
    shutil.which 실패 시 Windows npm 글로벌 경로를 직접 탐색.
    """
    found = shutil.which("gemini") or shutil.which("gemini.cmd")
    if found:
        return found

    import os
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        candidate = Path(appdata) / "npm" / "gemini.cmd"
        if candidate.exists():
            return str(candidate)

    raise RuntimeError(
        "'gemini' CLI를 찾을 수 없습니다.\n"
        "터미널에서 npm install -g @google/gemini-cli 를 실행한 뒤\n"
        "Vivid Studio 서버를 재시작하세요."
    )


def _find_node_gemini_cmd() -> list[str]:
    """
    [node.exe경로, entry.js경로] 를 3계층 탐색으로 반환 (결과 캐싱).

    Layer 1 — require.resolve (가장 정확, Node.js 모듈 탐색 알고리즘 직접 활용)
    Layer 2 — cmd_path.parent/node_modules (글로벌 npm 표준 구조)
    Layer 3 — cmd_path.parent.parent (로컬 node_modules/.bin 구조 대응)
    """
    global _gemini_node_cmd_cache
    if _gemini_node_cmd_cache is not None:
        return _gemini_node_cmd_cache

    node = shutil.which("node.exe") or shutil.which("node")
    if not node:
        raise RuntimeError("node.exe를 찾을 수 없습니다. Node.js 설치를 확인하세요.")

    _BUNDLE = ("node_modules", "@google", "gemini-cli", "bundle", "gemini.js")

    # ── Layer 1: require.resolve로 Node.js에게 직접 질의 ──────────────────
    try:
        resolve_script = (
            "const r=require.resolve('@google/gemini-cli');"
            "const p=require('path');"
            "console.log(p.join(p.dirname(r),'../bundle/gemini.js'))"
        )
        res = subprocess.run(
            [node, "-e", resolve_script],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=15,
        )
        if res.returncode == 0:
            js_path = Path(res.stdout.strip())
            if js_path.exists():
                _gemini_node_cmd_cache = [node, str(js_path)]
                return _gemini_node_cmd_cache
    except Exception:
        pass

    # ── Layer 2 / 3: cmd_path 기준 직접 경로 구성 ─────────────────────────
    cmd_path = Path(_find_gemini_exe())
    for base in (cmd_path.parent, cmd_path.parent.parent):
        js_path = base.joinpath(*_BUNDLE)
        if js_path.exists():
            _gemini_node_cmd_cache = [node, str(js_path)]
            return _gemini_node_cmd_cache

    raise RuntimeError(
        "gemini entry.js를 찾을 수 없습니다.\n"
        f"탐색 기준 경로: {cmd_path.parent}\n"
        "npm install -g @google/gemini-cli 재설치 후 서버를 재시작하세요."
    )


def _call_gemini_cli(prompt: str, cwd: str | None = None) -> str:
    """
    시스템에 설치된 'gemini' CLI를 호출하여 응답을 받는다.
    Windows: node.exe + entry.js 직접 호출로 cmd.exe 8191자 제한 우회.
    cwd: Gemini가 파일을 탐색할 작업 디렉토리 (기본: 임시 폴더)
    """
    import tempfile as _tmp

    if sys.platform == "win32":
        # gemini.cmd 래퍼 없이 node.exe를 직접 실행 → cmd.exe 인수 길이 제한 없음
        cmd = _find_node_gemini_cmd() + ["-p", prompt]
    else:
        cmd = [_find_gemini_exe(), "-p", prompt]

    result = subprocess.run(
        cmd,
        capture_output=True,
        cwd=cwd if cwd else _tmp.gettempdir(),
        timeout=600,
    )

    if result.returncode != 0:
        err = result.stderr
        if isinstance(err, bytes):
            err = err.decode("utf-8", errors="replace")
        raise RuntimeError(f"gemini CLI 호출 실패: {err[:300]}")

    out = result.stdout
    if isinstance(out, bytes):
        out = out.decode("utf-8", errors="replace")
    return _ANSI_RE.sub("", out).strip()


@app.post("/api/chat")
async def api_chat(request: Request):
    """
    AI 채팅 엔드포인트 (gemini CLI 기반)
    """
    # ── 입력 파싱 ────────────────────────────────────────────────────────────
    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"JSON 파싱 실패: {e}")

    message = str(body.get("message", "")).strip()
    history = body.get("history", [])  # [{role, text}, ...]

    if not message:
        raise HTTPException(status_code=400, detail="message field is empty.")

    # ── 대화 이력 포맷팅 ─────────────────────────────────────────────────────
    history_ctx = ""
    if history:
        history_lines = []
        for h in history:
            role = "AI" if h.get("role") == "assistant" else "User"
            history_lines.append(f"{role}: {h.get('text', '')}")
        history_ctx = "## 이전 대화 맥락\n" + "\n".join(history_lines) + "\n\n"

    # ── 의도 분류 → 시스템 프롬프트 선택 ────────────────────────────────────
    intent = _detect_intent(message)
    if intent == "fx_modify":
        system = _SYSTEM_FX_MODIFY
    elif intent == "fx_create":
        system = _SYSTEM_FX_CREATE
    else:
        system = _SYSTEM_GENERAL

    prompt = (
        f"{system}\n\n"
        f"{history_ctx}"
        f"## 사용자 요청\n{message}\n\n"
        "반드시 JSON 형식으로만 답변해줘."
    )

    # ── Gemini (CLI) 호출 — workspace root를 cwd로 설정 ──────────────────────
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        raw = await loop.run_in_executor(
            None,
            lambda: _call_gemini_cli(prompt, cwd=str(_WORKSPACE_ROOT)),
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gemini(CLI) 호출 실패: {e}")

    # ── 응답 파싱 (JSON 추출) ─────────────────────────────────────────────────
    # 1단계: 마크다운 코드블록 안의 JSON 우선 추출
    json_block = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, re.DOTALL)
    if json_block:
        raw = json_block.group(1).strip()

    # 2단계: raw_decode — 앞뒤 자연어 텍스트 있어도 JSON 추출 가능
    first_brace = raw.find("{")
    if first_brace >= 0:
        try:
            result, _ = json.JSONDecoder().raw_decode(raw[first_brace:])
            return JSONResponse(content=result)
        except json.JSONDecodeError:
            pass

    # 3단계: 완전 실패 → 텍스트 응답으로 폴백
    return JSONResponse(content={"type": "text", "content": raw})


# ── 정적 파일 마운트 (React 빌드 or 플레이스홀더) ───────────────────────────
# FastAPI 앱 초기화 후 마운트 (editor/ 폴더가 존재할 때만)
def _mount_static():
    if _EDITOR_DIR.exists():
        app.mount("/", StaticFiles(directory=str(_EDITOR_DIR), html=True), name="editor")


# ── 서버 진입점 ──────────────────────────────────────────────────────────────

def set_project_dir(path: Path) -> None:
    """step4.py에서 프로젝트 선택 시 호출"""
    global _project_dir
    _project_dir = path


def start_server(project_dir: Path, port: int = 8000) -> None:
    """
    daemon 스레드에서 호출:
      threading.Thread(target=start_server, args=(proj_dir,), daemon=True).start()
    """
    import uvicorn

    set_project_dir(project_dir)
    _mount_static()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
