# Vivid 프로젝트 마스터 가이드: 유튜브 영상편집 자동화 GUI 프로그램

## 1. 프로젝트 목표

- **목표:** 유튜브 영상 제작 반자동화 GUI 프로그램 구축.
- **스택:** PySide6(GUI) + HyperFrames(슬라이드 렌더링, 주력) + Remotion(레거시 백업) + Vrew(최종 조립).
- **철학:** Human-in-the-loop (단계별 승인 및 검수).

## 2. 파이프라인 구조

4단계 스텝 위젯 (`main.py` → `QStackedWidget`):

| Step | 파일             | 역할                                      |
| ---- | ---------------- | ----------------------------------------- |
| 1    | `steps/step1.py` | 프로젝트 생성 / 템플릿 복제               |
| 2    | `steps/step2.py` | 대본 파싱 → 슬라이드 기획안               |
| 3    | `steps/step3.py` | 에셋 임포트, PDF 스토리보드, SRT 타임라인 |
| 4    | `steps/step4.py` | HyperFrames 편집/렌더 → Vrew 조립         |

보조 모듈: `utils/hf_renderer.py`(렌더), `utils/hf_editor.py`(편집 UI), `utils/step4_workers.py`(비동기 워커).

## 3. Step 4 — 핵심 워크플로우

### 3-A. HyperFrames 모듈 (주력)

- **렌더 엔진:** `utils/hf_renderer.py` — `slide_NN.html` + delta JSON → temp `index.html` → hyperframes CLI → `slide_NN.webm`
- **편집 UI:** `utils/hf_editor.py` — WebEngine 기반, GSAP 인터셉션, delta JSON 저장.
- **HyperFrames 바이너리 경로 우선순위:**
  1. 프로젝트 로컬: `project/hyperframes/node_modules/.bin/hyperframes.cmd`
  2. 템플릿 폴백: `Project_templete/hyperframes/node_modules/.bin/hyperframes.cmd`
- HyperFrames 안정 가동 확인 후 Remotion 모듈 폐기 예정.

### 3-B. Remotion 모듈 (레거시 백업 전용)

- `npx remotion studio` / `npx remotion render` 방식 (루트에 remotion/ 폴더 없음).
- **신규 기능 개발 대상 아님.** 기존 프로젝트 호환성 유지 목적만.
- 상세 규칙: `remotion_spec.md` 참조.

### 3-C. 렌더링 완료 리포트

- 완료 시 `C_HIGHLIGHT`(골드)로 상태창 출력: 총 소요시간 / 신규 렌더 수 / 캐시 재사용 수 / 전체 합계.

## 4. 하네스 엔지니어링 (Harness Engineering) 필수 적용

1. **무결성 + 파일명 정규화:** 업로드 파일 0바이트/포맷 유효성 즉시 검사. 에러 시 상태창 적색 출력.
   - `.vrew`, `.mp3`, `.srt`, `.json` 소스 파일 → 표준 파일명(`원본.vrew`, `TTS.mp3`, `Subtitle.srt`, `remotion_plan.json`)으로 자동 변환. Overwrite 경고 없음.
   - `AssetManagerDialog` 수동 추가/교체: 0바이트 즉시 거부, 확장자 검증(이미지/영상).
2. **FX 자동화:** `fx_catalog.txt` 변경 시 `invalidate_cache()`(`utils/fx_gallery.py`) 반드시 호출.
   - Custom FX: 컴포넌트 코딩 → 카탈로그 등재 → JSON Props 역주입 필수.
3. **스마트 렌더:** JSON Diff-Check 기반 부분 렌더링 (변경 슬라이드만 타겟).
4. **Vrew 보호:** `원본.vrew` 직접 수정 금지. `최종_vN.vrew`로 복제 후 조립.
   - `utils/backend_ext.py > _normalize_file_paths()`: `project.json files[]` 절대 경로 → `Path(val).name` 자동 변환.
5. **환경 진단:** 앱 시작 시 `HealthCheckDialog`(`utils/health_check.py`) 자동 실행 — node / ffmpeg / hyperframes / node_modules 점검.

## 5. 보조 시스템

### 5-A. FX 갤러리 (`utils/fx_gallery.py`)

- `_catalog_cache` — 모듈 레벨, 최초 1회 파싱 후 재사용. `invalidate_cache()`로 무효화.
- 갤러리 팝업: `FxGalleryDialog(CATALOG_PATH, parent=self)`.
- 카탈로그 파일: `fx_catalog.txt`.

### 5-B. Gemini CLI (`utils/step4_workers.py > GeminiWorker`, `utils/editor_server.py`)

- `@google/gemini-cli` npm 글로벌 패키지 (`npm install -g @google/gemini-cli`). Python 라이브러리 아님.
- Windows: `node.exe + gemini.js` 직접 호출 (cmd.exe 8191자 인수 제한 우회). 바이너리 탐색: 3계층 폴백 (`shutil.which` → AppData/npm → `require.resolve`).
- 인증: CLI 자체 OAuth (별도 API Key 불필요).
- 사용처: `GeminiWorker`(슬라이드 키워드 요약 → QClipboard), `editor_server.py > api_chat`(편집기 AI 채팅).

### 5-C. 공유 에셋 (`shared_assets/`)

- `shared_assets/shared_fx/` — 글로벌 FX TSX 원본 (`utils/theme.py > SHARED_FX_DIR`).
- `shared_fx/*.tsx` → Git 추적. 미디어 바이너리(`.mp4`, `.mp3`) → 추적 제외.

### 5-D. VIVID Radar (`vivid_radar/`)

- A1(채널 발굴) / A2(주제 탐색) / A3(제목 최적화) 통합 기획 파이프라인.
- **`vivid_radar/radar_spec.md`** = 이 파일보다 높은 우선순위의 Source of Truth.

## 6. 세부 매뉴얼 참조

| 주제              | 파일                        |
| ----------------- | --------------------------- |
| UI/UX             | `ui_ux_spec.md`             |
| Backend           | `backend_rules.md`          |
| Remotion (레거시) | `remotion_spec.md`          |
| FX 목록           | `fx_catalog.txt`            |
| Radar             | `vivid_radar/radar_spec.md` |
