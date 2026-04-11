# Vivid 프로젝트 마스터 가이드: 유튜브 영상편집 자동화 GUI 프로그램

## 1. 프로젝트 목표

- 목표 : 대상: 유튜브 영상 제작 반자동화 GUI 프로그램 구축.
- 스택: PySide6(GUI) + Remotion(Alpha FX) + Vrew(Final Assembly).
- 철학: Human-in-the-loop (단계별 승인 및 검수).

## 2. 하네스 엔지니어링 (Harness Engineering) 필수 적용

클로드는 코드를 작성할 때 다음의 오류 방지 및 검증 로직을 반드시 포함해야 합니다.

1.  **무결성 + 파일명 정규화:** 업로드 파일 0바이트/포맷 유효성 즉시 검사. 에러 시 상태창 적색 출력.
    - **파일명 자동 정규화(Normalization):** `.vrew`, `.mp3`, `.srt`, `.json` 소스 파일은 업로드 경로(Drag & Drop / 버튼)에 관계없이 반드시 표준 파일명(`원본.vrew`, `TTS.mp3`, `Subtitle.srt`, `remotion_plan.json`)으로 변환하여 저장한다. 동일 파일명 존재 시 경고 없이 Overwrite.
    - **에셋 교체 시에도 동일하게 적용:** `AssetManagerDialog`의 수동 추가/교체 모드에서도 0바이트 파일은 즉시 거부하고 에러 표시. 확장자 검증(이미지/영상 구분)도 함께 수행.
2.  **FX 자동화:** src/components/fx/ 변경 시 fx_catalog.md 즉시 업데이트.
    - Custom 요청 시: 컴포넌트 코딩 → 카탈로그 등재 → JSON Props 역주입 필수.
    - 카탈로그 업데이트 시 `invalidate_cache()`(utils/fx_gallery.py) 반드시 호출하여 갤러리 캐시 초기화.
3.  **스마트 렌더:** JSON Diff-Check 기반 부분 렌더링. 변경된 요소만 타겟팅 추출.
4.  **Vrew 보호:** 원본.vrew 직접 수정 금지. 최종\_vN.vrew로 복제 후 조립.
    - project.json 내 기존 files[] 절대 경로는 `_normalize_file_paths()` 함수로 상대 경로 자동 변환.
5.  **환경 진단:** 앱 시작 시 `HealthCheckDialog`(utils/health_check.py)가 자동 실행되어
    node / ffmpeg / remotion / node_modules 설치 여부를 점검. 미설치 시 npm install 버튼 제공.

## 3. 추가 시스템 (2026-04 구현)

아래 시스템은 향후 유지보수 시 변경 금지 또는 연동 필수입니다.

### 3-A. FX 즐겨찾기 시스템 (`utils/fx_gallery.py`)

- `_catalog_cache` — 모듈 레벨 변수. 최초 1회 `_parse_catalog()` 파싱 후 재사용 (메모리 캐시).
- `invalidate_cache()` — FX 카탈로그 변경 시 반드시 호출하여 캐시 무효화.
- `_update_favorites()` — fx_catalog.md 파일 최상단 `## 즐겨찾기 (Favorites)` 섹션을 정규식으로 교체.
- 갤러리 팝업 진입점: `FxGalleryDialog(CATALOG_PATH, parent=self)`.

### 3-B. Gemini API 연동 (`steps/step4.py > GeminiWorker`)

- 모델: `gemini-2.5-flash` (google-generativeai 라이브러리 사용).
- API Key: `config.json` (workspace 루트) `gemini_api_key` 필드에 평문 저장.
- 입력: `project_dir/input/script_body_slide.txt` (슬라이드별 대본 원문).
- 출력: 슬라이드별 핵심 키워드 + 연출 분위기 요약 → QClipboard 자동 복사.
- 라이브러리 미설치 시 ImportError를 사용자 친화적 메시지로 안내.

### 3-C. Vrew 에셋 상대 경로 규칙 (`utils/backend_ext.py > _normalize_file_paths`)

- `assemble_vrew()` 호출 시 기존 `project.json`의 `files[]` 내
  `filePath / localPath / sourcePath / path` 필드가 절대 경로인 경우
  자동으로 `Path(val).name` (파일명만) 으로 변환.
- 신규 추가 에셋: `"fileLocation": "IN_MEMORY"` 방식 유지.

### 3-D. 렌더링 완료 리포트

- 렌더링 완료 시 `C_HIGHLIGHT`(골드) 색상으로 상태창에 아래 정보 출력:
  - 총 소요 시간 / 신규 렌더 FX 수 / 캐시 재사용 수 / 전체 FX 합계

### 3-E. 글로벌 FX 라이브러리 및 공유 에셋 통합 아키텍처 (2026-04 구현)

> **핵심 원칙:** 모든 공용 리소스(영상, 시각효과 코드)는 `shared_assets/` 폴더 내에서 통합 관리된다.
> FX 코드는 **심볼릭 링크**를 통해 모든 프로젝트가 단일 원본을 공유하며, 용량 낭비 없이 자산화한다.

- **경로 상수** (`utils/theme.py`):
  - `SHARED_FX_DIR = SHARED_ASSETS_DIR / "shared_fx"` — 글로벌 FX TSX 원본 저장 위치.
  - 앱 시작 시 `shared_fx/` 폴더가 없으면 자동 생성 (`mkdir`).
- **프로젝트 생성 시 심볼릭 링크** (`steps/step1.py > _setup_fx_symlink()`):
  - `copytree` 직후 프로젝트 내 `remotion/src/components/fx/` 폴더를 삭제하고 `SHARED_FX_DIR`를 가리키는 심볼릭 링크로 대체.
  - Windows 권한 오류 시 폴백(복사 방식)으로 진행하고 개발자 모드 활성화 안내.
- **Custom FX 저장** (`steps/step4.py > _process_custom_fx()`):
  - TSX 파일은 반드시 `SHARED_FX_DIR` 에 저장. 프로젝트 내부에 직접 저장하지 않는다.
  - `fx_catalog.md` 경로 표기는 `src/components/fx/` 유지 (Remotion import 경로 = 심볼릭 링크 경유).
- **Git 추적** (`shared_assets/.gitignore`):
  - 미디어 바이너리(`.mp4`, `.mp3` 등) → 추적 제외.
  - `shared_fx/*.tsx` → `!` 예외 규칙으로 Git 추적 허용 (FX 코드는 소스 자산).

## 4. 세부 매뉴얼 참조(External spec)

작업의 종류에 따라 아래 문서를 열어서(읽고) 참조하십시오.

- UI/UX: ui_ux_spec.md (화면/버전 로직/테마 컬러)
- Backend: backend_rules.md (파싱/Watchdog/Vrew 조립 로직)
- Remotion: remotion_spec.md (디자인/CSS/투명 렌더링 규칙)
- FX List: fx_catalog.md (현재 가용한 효과 명세)
