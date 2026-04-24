# HyperFrames 통합 구현 계획서

> 새 세션 시작 시 이 파일을 먼저 읽을 것.

---

## 현재 상태 (2026-04-24)

### 완료된 것

| 항목                           | 파일                                                                                                                                   |
| ------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------- |
| n8n 파이프라인 (5노드)         | `n8n_workflow/hyperframes_pipeline.json`                                                                                               |
| HyperFrames 렌더 엔진          | `utils/hf_renderer.py` — `render_slide()` / `render_all_slides()` + delta + 재시도                                                     |
| Health Check HyperFrames 항목  | `utils/health_check.py` — node_modules 체크 + npm install 버튼                                                                         |
| Vrew HF 조립                   | `utils/backend_ext.py` — `assemble_vrew_hf()` (mp4, H.264, zIndex=10)                                                                  |
| Step 4 HyperFrames 탭 — STEP A | `steps/step4.py` `_trigger_n8n()` — n8n 웹훅 POST 트리거 버튼                                                                          |
| Step 4 HyperFrames 탭 — STEP B | `_on_hf_plan_received()` — `hyperframes_compositions.json` 업로드·lint·슬라이드별 HTML 저장                                            |
| Step 4 HyperFrames 탭 — STEP C | `HfEditorPanel` — QWebEngineView 미리보기 + 속성 패널(X/Y/fontSize/color/text/gsap_start) + Undo/Redo + 타임라인 스크러버 + delta 저장 |
| Step 4 HyperFrames 탭 — STEP D | `_on_hf_render_click()` → `HFRenderWorker` — 슬라이드별 `.mp4` 렌더 + 진행률 표시                                                      |
| Step 4 HyperFrames 탭 — STEP E | `_on_hf_vrew_click()` → `HFVrewWorker` → `assemble_vrew_hf()` — 최종 `최종_hf_vN.vrew` 생성                                            |

### 즉시 해결 필요 (최우선 블로커)

없음. 엔드투엔드 검증 완료 (2026-04-24).

**n8n 기동 시 필수 환경변수**:

```powershell
$env:NODE_FUNCTION_ALLOW_BUILTIN="*"
$env:NODE_FUNCTION_ALLOW_EXTERNAL="*"
n8n start
```

---

## 다음 작업: Phase 4 — QWebEngineView 편집 UI

현재 Step 4 HyperFrames 탭의 **STEP C**는 `HfEditorPanel` 위젯이 자리잡고 있으나 편집 기능 미구현.

| 항목           | 결정                                                                      |
| -------------- | ------------------------------------------------------------------------- |
| 편집 가능 속성 | 위치(드래그), 크기, 색상, 텍스트, GSAP 시작 시점                          |
| 저장 방식      | `slide_NN_delta.json` (delta 파일) — `hf_renderer.py`가 렌더 시 자동 적용 |
| Undo/Redo      | 필요                                                                      |
| 타임라인       | 재생/정지/스크러빙                                                        |

`delta.json` 구조 (`_apply_delta()` — `utils/hf_renderer.py`에 이미 구현):

```json
{
  "elements": {
    ".text-1": { "x": 100, "y": -50, "fontSize": "90px", "color": "#FFD700" },
    ".bg": { "x": 0, "y": 0 }
  }
}
```

---

## 미확정

- **A-5 인트로/범퍼** — 권장: `base_timeline.json`에 `"type":"intro"` 슬라이드로 편입

---

## 아키텍처 요약

```
base_timeline.json + image_N.jpeg
        ↓ (n8n 파이프라인)
hyperframes_compositions.json   {"slide_01": "<!DOCTYPE html>...", ...}
        ↓ (Step 4 STEP B 업로드)
hyperframes/compositions/slide_NN.html
        ↓ (Step 4 STEP D 렌더)
output/hyperframes/slide_NN.mp4   (1920×1080, 30fps, H.264, 불투명)
        ↓ (Step 4 STEP E)
asset/최종_hf_vN.vrew
```

**프로젝트 폴더 구조**:

```
ProjectName/
├── asset/
│   ├── base_timeline.json       ← generate_timeline_json() 생성
│   ├── image_1.jpeg ...         ← Watchdog 수집
│   ├── hyperframes_compositions.json  ← n8n 출력 / 사용자 업로드
│   └── hf_render_report.json
├── output/hyperframes/          ← slide_NN.mp4
└── hyperframes/
    ├── package.json  {"dependencies":{"@hyperframes/cli":"^0.4.13"}}
    ├── node_modules/
    └── compositions/slide_NN.html
```

---

## 핵심 스키마

**base_timeline.json** (`generate_timeline_json()` — `utils/backend.py`):

```json
[
  {
    "slide_id": "slide_01",
    "bg_image": "image_1.jpeg",
    "start": 53.77,
    "end": 85.57,
    "duration": 31.8,
    "full_text": "대본 전문...",
    "segments": [{ "index": 21, "start": 53.77, "end": 58.03, "text": "..." }]
  }
]
```

**hyperframes_compositions.json**: `{"slide_01": "<전체 HTML>", "slide_02": "..."}`

**HTML 슬라이드 기술 상수** (Generator 출력):

- Canvas: 1920×1080, `margin:0; overflow:hidden`
- 클래스: `.bg` / `.text-1` / `.text-2` / `.text-3`
- 좌표: `left: calc(50% + Xpx); top: calc(50% + Ypx);` (캔버스 중앙 기준)
- GSAP: `https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js`
- 배경 이미지 경로: `../../asset/IMAGE_FILENAME` (상대경로, compositions/ 기준 두 단계 위)

---

## 기술 참조

| 항목              | 내용                                                                    |
| ----------------- | ----------------------------------------------------------------------- |
| n8n 실행          | `$env:NODE_FUNCTION_ALLOW_BUILTIN="*"; n8n start`                       |
| n8n 워크플로우    | `n8n_workflow/hyperframes_pipeline.json`                                |
| HyperFrames SKILL | `/c/Youtube/hyperframes/skills/hyperframes/SKILL.md`                    |
| HyperFrames CLI   | `/c/Youtube/hyperframes/skills/hyperframes-cli/SKILL.md`                |
| Gemini CLI        | `--yolo` 필수, `-m` 생략(auto), Vision = 프롬프트에 파일 경로 직접 포함 |
| `.geminiignore`   | `*.mp4 *.mp3 *.wav *.webm` 제외, `!*.jpeg !*.jpg !*.png !*.webp` 허용   |
| Windows spawn     | `bash -c "gemini --yolo \"...\""` (cmd.exe는 한글+JSON 오염)            |
