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
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
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


# ── AI 채팅 엔드포인트 ───────────────────────────────────────────────────────

_CHAT_SYSTEM = """\
당신은 VIVID Studio AI 어시스턴트입니다.
사용자의 remotion_plan.json을 분석하고 편집 요청에 응답합니다.

## 응답 규칙
반드시 아래 세 가지 형식 중 하나의 JSON만 반환하세요 (마크다운 없이 순수 JSON):

1. plan 수정 요청인 경우:
{"type":"plan_update","plan":{...전체 수정된 plan...},"summary":"변경 내용 한 줄 요약"}

2. 새 FX TSX 코드 요청인 경우:
{"type":"tsx_code","filename":"XxxFX.tsx","code":"// TSX 코드...","summary":"FX 설명"}

3. 일반 질문/설명인 경우:
{"type":"text","content":"답변 내용"}

## 판단 기준
- "바꿔", "수정", "변경", "이동", "설정" → plan_update
- "만들어", "작성", "추가 FX", "코드" → tsx_code
- "뭐야", "어떻게", "설명" → text
"""

_CATALOG_TRUNCATE = 2000  # fx_catalog 컨텍스트 최대 문자 수
_PLAN_TRUNCATE    = 6000  # plan 컨텍스트 최대 문자 수


def _get_gemini_client():
    """OAuth 우선, 실패 시 config.json API key 시도"""
    # 1. OAuth (client_secret.json)
    root = Path(__file__).parent.parent
    secret = root / "client_secret.json"
    token  = root / "token.json"
    if secret.exists():
        try:
            from utils.google_auth import get_genai_client  # type: ignore
            return get_genai_client(
                client_secret_path=str(secret),
                token_path=str(token),
            )
        except Exception:
            pass  # OAuth 실패 시 API key로 폴백

    # 2. API key (config.json)
    cfg_path = root / "config.json"
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            api_key = cfg.get("gemini_api_key", "")
            if api_key:
                from google import genai  # type: ignore
                return genai.Client(api_key=api_key)
        except Exception:
            pass

    raise RuntimeError(
        "Gemini 인증 정보 없음. "
        "client_secret.json (OAuth) 또는 config.json의 gemini_api_key를 확인하세요."
    )


@app.post("/api/chat")
async def api_chat(request: Request):
    """
    AI 채팅 엔드포인트
    입력: { message: str, plan?: dict }
    출력:
      { type: "plan_update", plan: {...}, summary: str }
      { type: "tsx_code",    filename: str, code: str, summary: str }
      { type: "text",        content: str }
    """
    # ── 입력 파싱 ────────────────────────────────────────────────────────────
    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"JSON 파싱 실패: {e}")

    message  = str(body.get("message", "")).strip()
    plan_raw = body.get("plan")

    if not message:
        raise HTTPException(status_code=400, detail="message 필드가 비어 있습니다.")

    # ── 컨텍스트 구성 ────────────────────────────────────────────────────────
    plan_ctx = (
        json.dumps(plan_raw, ensure_ascii=False, indent=2)[:_PLAN_TRUNCATE]
        if plan_raw else "없음"
    )

    catalog_ctx = ""
    catalog_path = Path(__file__).parent.parent / "fx_catalog.txt"
    if catalog_path.exists():
        catalog_ctx = catalog_path.read_text(encoding="utf-8")[:_CATALOG_TRUNCATE]

    prompt = (
        f"{_CHAT_SYSTEM}\n\n"
        f"## 현재 remotion_plan.json\n{plan_ctx}\n\n"
        + (f"## 등록된 FX 카탈로그\n{catalog_ctx}\n\n" if catalog_ctx else "")
        + f"## 사용자 요청\n{message}"
    )

    # ── Gemini 호출 ───────────────────────────────────────────────────────────
    try:
        client = _get_gemini_client()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        raw = response.text.strip()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gemini 호출 실패: {e}")

    # ── 응답 파싱 (JSON 추출) ─────────────────────────────────────────────────
    # 마크다운 코드블록 제거 시도
    json_block = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, re.DOTALL)
    if json_block:
        raw = json_block.group(1).strip()

    try:
        result = json.loads(raw)
        # plan_update 검증: plan 필드가 dict여야 함
        if result.get("type") == "plan_update":
            if not isinstance(result.get("plan"), dict):
                result = {"type": "text", "content": raw}
        return JSONResponse(content=result)
    except json.JSONDecodeError:
        # JSON 파싱 실패 → 텍스트 응답으로 폴백
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
