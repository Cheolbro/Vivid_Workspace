# HyperFrames 모듈 현황 (2026-04-25)

> 새 세션 시작 시 이 파일을 먼저 읽을 것.

---

## 시스템 아키텍처

```
base_timeline.json + image_N.jpeg
        ↓  n8n_workflow/hyperframes_pipeline.json
hyperframes_compositions.json   {"slide_01": "<HTML>", ...}
        ↓  Step 4 STEP B — 업로드·lint·슬라이드별 HTML 저장
hyperframes/compositions/slide_NN.html
        ↓  Step 4 STEP C — HfEditorPanel (QWebEngineView 편집)
hyperframes/compositions/slide_NN_delta.json  (위치/크기/색상 수정값)
        ↓  Step 4 STEP D — HFRenderWorker → utils/hf_renderer.py
output/hyperframes/slide_NN.mp4  (1920×1080, 30fps, H.264)
        ↓  Step 4 STEP E — HFVrewWorker → utils/backend_ext.py
asset/최종_hf_vN.vrew
```

---

## 주요 파일

| 파일                                     | 역할                                                             |
| ---------------------------------------- | ---------------------------------------------------------------- |
| `steps/step4.py`                         | STEP A~E UI, `_GSAP_INTERCEPT_JS`, `_EDITOR_JS`, `HfEditorPanel` |
| `utils/hf_renderer.py`                   | `render_slide()` / `render_all_slides()` + delta 적용 + 재시도   |
| `utils/backend_ext.py`                   | `assemble_vrew_hf()` — 최종 .vrew 조립                           |
| `utils/health_check.py`                  | node_modules 체크 + npm install 버튼                             |
| `n8n_workflow/hyperframes_pipeline.json` | n8n 5-노드 파이프라인                                            |

---

## STEP C 편집 UI — JS 주입 순서

```
DocumentCreation (페이지 생성 직후)
  ├─ qwebchannel.js          (Qt 브릿지)
  └─ _GSAP_INTERCEPT_JS      (steps/step4.py 상단 상수)
       └─ Object.defineProperty(window, 'gsap', { set: ... })
            → GSAP CDN 번들 실행 시 가로채기
            → autoRemoveChildren = false  (타임라인 보존)
            → window.__capturedTl = tl   (타임라인 레퍼런스 저장)

loadFinished (페이지 완전 로드 후)
  └─ _EDITOR_JS              (steps/step4.py 상단 상수)
       ├─ viewport meta 강제: width=1920  (좌표 2배 오차 방지)
       ├─ _getMainTl() → window.__capturedTl 우선 반환
       ├─ _forceVisible() — querySelectorAll('*')로 전체 요소 표시
       ├─ drag: setZoomFactor 내부 변환으로 별도 보정 불필요
       ├─ resize: text-common → fontSize, 그 외 → transform:scale()
       └─ play() — 타임라인 없으면 hf-editor-visible 제거 안 함
```

---

## delta.json 구조 (`_apply_delta()` — utils/hf_renderer.py)

```json
{
  "elements": {
    ".text-1": { "x": 100, "y": -50, "fontSize": "90px", "color": "#FFD700" },
    ".bg": { "x": 0, "y": 0 },
    ".fx-box": { "scale": "1.4" }
  }
}
```

---

## 프로젝트 폴더 구조

```
ProjectName/
├── asset/
│   ├── base_timeline.json
│   ├── image_N.jpeg
│   ├── hyperframes_compositions.json
│   └── hf_render_report.json
├── output/hyperframes/slide_NN.mp4
└── hyperframes/
    ├── package.json  {"dependencies":{"@hyperframes/cli":"^0.4.13"}}
    ├── node_modules/
    └── compositions/
        ├── slide_NN.html
        └── slide_NN_delta.json
```

---

## HTML 슬라이드 기술 상수 (n8n Generator 출력)

- Canvas: 1920×1080, `margin:0; overflow:hidden`
- 클래스: `.bg` / `.text-common .text-1` / `.text-common .text-2` / `.text-common .text-3`
- 좌표: `left: calc(50% + Xpx); top: calc(50% + Ypx);` (캔버스 중앙 기준)
- GSAP: `https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js`
- 배경 이미지: `../../asset/IMAGE_FILENAME` (compositions/ 기준 두 단계 위)

---

## n8n 기동 필수 환경변수

```powershell
$env:NODE_FUNCTION_ALLOW_BUILTIN="*"
$env:NODE_FUNCTION_ALLOW_EXTERNAL="*"
n8n start
```

---

## 미해결 문제

### [블로커] FX 효과 미표시 — n8n 파이프라인 갭

**증상**: STEP C 미리보기에 `.bg`(배경)와 `.text-common`(텍스트)만 표시됨.  
`shared_assets/shared_fx/*.tsx`의 FX 효과 (MoneyRainFX, GoldenRayFX 등)가 보이지 않음.

**근본 원인**: n8n이 생성하는 slide HTML에 FX 요소가 없음.  
기존 FX는 Remotion/React 기반 TSX 컴포넌트 — 순수 HTML/JS 환경에서 직접 실행 불가.

**해결 방향 (장기)**:

1. `shared_assets/shared_fx_hf/` — TSX FX를 바닐라 JS로 포팅
2. `hf_fx_runtime.js` 작성 — Remotion API 순수 JS 구현
   - `interpolate(frame, [in, out], [from, to])` 함수
   - `seededRandom(seed)` 함수
   - `requestAnimationFrame` 기반 프레임 루프
3. n8n 파이프라인 확장 — FX 메타데이터를 HTML `<script data-fx>` 태그로 포함
4. `HfEditorPanel._on_load_finished` — FX 런타임 스크립트 자동 주입

**단기 대안**: 현재는 텍스트+배경만 편집 가능. FX는 최종 렌더 단계에서만 반영 가능.

---

## 기술 참조

| 항목              | 내용                                                                    |
| ----------------- | ----------------------------------------------------------------------- |
| HyperFrames SKILL | `/c/Youtube/hyperframes/skills/hyperframes/SKILL.md`                    |
| HyperFrames CLI   | `/c/Youtube/hyperframes/skills/hyperframes-cli/SKILL.md`                |
| Gemini CLI        | `--yolo` 필수, `-m` 생략(auto), Vision = 프롬프트에 파일 경로 직접 포함 |
