# GEMINI_CONTEXT — Vivid Workspace 온보딩 가이드

> 이 파일은 Claude 한도 소진 시 Gemini가 단독으로 설계+구현할 때, 그리고 Claude 복귀 시 핸드오버 문서로 사용된다.
> **작업 전 반드시 이 파일을 읽어라.**

---

## 1. 기술 스택 요약

| 레이어     | 기술                       | 역할                                                |
| ---------- | -------------------------- | --------------------------------------------------- |
| GUI        | PySide6 (Python)           | 메인 앱 (`main.py`, `steps/`)                       |
| 편집 UI    | React + TypeScript + Vite  | `vivid_studio/` (port 4000)                         |
| 영상 FX    | Remotion (Node.js)         | `dry_test/remotion/` 또는 프로젝트 내 `remotion/`   |
| FX 공유    | `shared_assets/shared_fx/` | 심볼릭 링크로 모든 프로젝트에 공유                  |
| API 브릿지 | FastAPI (Python)           | `utils/editor_server.py` (port 8000)                |
| AI         | Gemini 2.5 Flash           | `steps/step4.py` → `google-generativeai` 라이브러리 |

---

## 2. 핵심 파일 경로

```
Vivid_Workspace/
├── main.py                  # PySide6 앱 진입점
├── steps/step4.py           # GeminiWorker, SemanticMatchWorker, CustomFX 처리
├── utils/
│   ├── editor_server.py     # FastAPI: /api/slides, /api/asset/, /api/save
│   ├── step4_workers.py     # SemanticMatchWorker (retry 로직 포함)
│   ├── fx_gallery.py        # FX 갤러리 팝업, invalidate_cache()
│   └── theme.py             # SHARED_FX_DIR, C_HIGHLIGHT 등 상수
├── vivid_studio/
│   ├── src/
│   │   ├── VividStudio.tsx  # 루트 컴포넌트, currentFrame state 소유
│   │   ├── SlideCanvas.tsx  # 640×360 프리뷰, EditWrapper 렌더링
│   │   ├── EditWrapper.tsx  # react-rnd HOC, 드래그/리사이즈
│   │   ├── EditPanel.tsx    # 우측 패널, Effect props 편집
│   │   ├── MiniTimeline.tsx # 하단 타임라인, 플레이헤드
│   │   └── types.ts         # Effect, Slide 타입 정의
│   └── vite.config.ts       # /api/* → localhost:8000 프록시
├── shared_assets/shared_fx/ # 글로벌 FX TSX 원본
├── fx_catalog.md            # 가용 FX 명세 (변경 시 invalidate_cache() 호출)
└── CLAUDE.md                # 프로젝트 마스터 가이드 (반드시 읽을 것)
```

---

## 3. 아키텍처 핵심 규칙

### 데이터 흐름

```
remotion_plan.json (flat effects[])
  → editor_server._flat_to_slides()
  → React UI (slides[{id, backgroundImage, effects[]}])
  → 편집 후 /api/save
  → remotion_plan.json 업데이트
```

### FX 파일 저장 규칙

- TSX FX 파일 → **반드시** `shared_assets/shared_fx/` 에 저장
- 프로젝트 내 `remotion/src/components/fx/`는 심볼릭 링크 (직접 생성 금지)
- `fx_catalog.md` import 경로는 `src/components/fx/` 유지 (심볼릭 링크 경유)

### React 상태 소유 원칙

- `currentFrame` → `VividStudio.tsx`가 소유, 자식에 prop으로 전달
- `selectedEffectId` → `VividStudio.tsx`가 소유
- Effect 데이터 변경 → `onEffectChange` 콜백 체인으로 버블업

---

## 4. 코딩 컨벤션

### TypeScript (vivid_studio/)

- 스타일: `const s: Record<string, React.CSSProperties> = {...}` 파일 하단에 정의
- Props interface: 컴포넌트 바로 위에 선언
- 이미지 URL: `/api/asset/{filename}` 형식 (Vite 프록시 경유)
- 타입 기본값: `withDefaults(effect)` 함수 사용 (types.ts 참조)

### Python (PySide6/FastAPI)

- 상태 출력: `self.log.emit(f"[색상] 메시지")` — C_HIGHLIGHT(골드), C_ERROR(적색)
- 파일 0바이트 검사: 업로드 즉시 검증, 에러 시 적색 출력
- Vrew 원본 보호: `원본.vrew` 직접 수정 금지 → `최종_vN.vrew`로 복제 후 조립

---

## 5. 절대 하지 말 것 (Guardrails)

1. **추상적 설명으로 코딩하지 말 것** — 기존 파일 수정은 반드시 `find`/`replace` 정확한 텍스트 치환
2. **verify 없이 완료 선언하지 말 것** — TypeScript면 `npx tsc --noEmit`, Python이면 `python -m py_compile`
3. **shared_assets/ 외부에 TSX FX 파일 생성하지 말 것**
4. **원본.vrew 직접 수정하지 말 것**
5. **fx_catalog.md 변경 후 `invalidate_cache()` 호출을 빠뜨리지 말 것**
6. **한 작업에 파일 5개 초과 수정하지 말 것** — 초과 시 task_id 분리하여 순차 실행
7. **코드 중복/쓰레기 코드 남기지 말 것** — 수정 후 원래 코드 블록 삭제 확인
8. **인터페이스에 prop 추가 없이 컴포넌트 내부에서 사용하지 말 것**

---

## 6. Gemini 단독 작업 시 워크플로우

```bash
# 1. 작업 계획 수립 (이 파일 + CLAUDE.md 참조)
# 2. .claude_instruction.json 형식으로 변경사항 정의 (find/replace 필수)
# 3. 코딩 실행
# 4. verify_after 명령어 실행 → 실패 시 수정 후 재실행 (최대 2회)
# 5. git diff로 자체 검수 → git add .
# 6. 완료 후 작업 내용 HANDOVER_NOTE.md에 기록 (Claude 복귀 시 참조용)
```

### HANDOVER_NOTE.md 작성 형식 (Claude 복귀 시 핸드오버)

```markdown
## 작업 일시: YYYY-MM-DD

## 변경 파일: [파일 목록]

## 변경 내용: [무엇을 왜 변경했는지]

## 미완료 사항: [있다면 기술]

## 주의사항: [Claude가 이어받을 때 알아야 할 것]
```

---

## 7. 참조 문서 (필요 시 열어볼 것)

- `CLAUDE.md` — 전체 프로젝트 마스터 가이드
- `fx_catalog.md` — 현재 가용 FX 목록
- `vivid_radar/radar_spec.md` — Radar 모듈 전용 spec (Radar 작업 시 최우선 참조)
- `.instruction_template.json` — 지시서 JSON 스키마
