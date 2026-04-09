## 0. 파일명 정규화 (Filename Normalization) — 전역 규칙
모든 소스 파일은 업로드·저장 시점에 아래 표준 파일명으로 **강제 변환**된다.
사용자가 어떤 이름으로 파일을 전달하더라도 시스템 내부에서는 항상 표준명으로 관리한다.

| 파일 종류 | 표준 저장명 | 적용 단계 |
|---|---|---|
| Vrew 프로젝트 파일 | `원본.vrew` | 3단계 업로드 |
| TTS 음성 파일 | `TTS.mp3` | 3단계 업로드 |
| 자막 파일 | `Subtitle.srt` | 3단계 업로드 |
| 영상 기획안 | `remotion_plan.json` | 4단계 업로드 |

- 적용 경로: Drag & Drop, 버튼 클릭 업로드 **모두** 동일하게 적용.
- 동일 이름 파일이 이미 존재할 경우 **경고 없이 덮어씌워(Overwrite) 최신 상태 유지**.
- 정규화 발생 시 상태창에 `파일명 정규화: '원본명' → '표준명'` 로그 출력.

---

## 1. 핵심 파이썬 백엔드 가공 규칙 (Data Parsing & Processing Rules)
프로그램 내에서 작동하는 파이썬 명령어(함수)들은 아래의 로직을 반드시 엄수해야 합니다.

1.  **대본 분할 (2단계 '대본 변환' 버튼 클릭 시):**
    - 입력: `script.txt` (내부에 인트로와 본문 구분자가 존재함)
    - 출력 1 (`script_intro.txt`): 인트로 영역의 텍스트만 추출.
    - 출력 2 (`script_body.txt`): 본문 영역의 텍스트만 추출 (인트로 제외).
    - 출력 3 (`script_body_slide.txt`): 본문 영역의 텍스트를 문단별로 나누고, 각 문단 시작에 `[슬라이드 1]`, `[슬라이드 2]` 등의 번호를 순차적으로 자동 부여하여 생성.

2.  **에셋 수집 및 넘버링 규칙 (자동 Watchdog + 수동 에셋 관리자 공통 적용):**

    **자동 수집 — Watchdog (3단계 'Watchdog 실행' 버튼)**
    - 사용자의 기본 '다운로드' 폴더를 0.8초 간격으로 폴링하여 신규 파일 감지.
    - 감지 시점 기준 순차 넘버링: `image_1.jpeg`, `image_2.jpeg` ... / `intro_1.mp4` ...
    - Watchdog 기능은 버튼 클릭으로 On/Off. GUI 상태 아이콘 [🔴 대기 중] / [🟢 파일 감지 중] 즉각 반영.
    - 파일 쓰기 완료 여부는 `_is_stable()` (0.5초 간격 파일 크기 2회 비교)로 확인 후 이동.

    **수동 제어 — 에셋 관리자 팝업 (3단계 '📁 에셋 관리' 버튼)**
    - `AssetManagerDialog` (steps/step3.py): Watchdog과 독립적으로 파일을 직접 제어.
    - **수동 추가 (Add) 탭:**
      - 다중 파일 선택 → `asset/` 내 `image_N.jpeg` / `intro_N.mp4` 최대 번호를 스캔.
      - 최대 번호 다음부터 순차적으로 부여하여 저장 (Watchdog 넘버링 규칙과 동일).
      - 예: `image_5.jpeg` 까지 존재 시 → 신규 파일은 `image_6.jpeg`부터 저장.
    - **번호 교체 (Replace) 탭:**
      - 타입(이미지/영상) + 교체 번호 지정 → 사용자가 선택한 파일로 강제 덮어쓰기(Overwrite).
      - 확장자 통일: 이미지→`.jpeg`, 영상→`.mp4` 저장.
    - **카운터 동기화 (`_sync_counts()`):**
      - 팝업이 닫힐 때마다 `asset/` 폴더를 재스캔하여 `_img_count` / `_vid_count` 최신화.
      - Watchdog이 실행 중이면 `WatchdogWorker.set_counts(img, vid)`를 호출하여 워커 내부 카운터도 동기화 → 자동/수동 병행 시 번호 충돌 방지.
    - **하네스:** 0바이트 파일 업로드 시 에러 메시지 출력하고 건너뜀.

3.  **스토리보드 PDF 병합 (3단계 '스토리보드 pdf 생성' 버튼 클릭 시):**
    - 입력: `asset` 폴더 내의 `image_n.jpeg` 파일들
    - 출력: 이미지들을 순서대로 병합하여 `storyboard.pdf`로 `asset` 폴더에 저장.

4.  **타임라인 생성 (3단계 '타임라인 JSON 생성' 버튼 클릭 시):**
    - 입력: Vrew에서 추출한 `Subtitle.srt`
    - 출력: `base_timeline.json` (각 대사의 시작/끝 시간, 텍스트를 파싱)

5.  **Custom 시각 효과 Batch Pre-flight Check 파이프라인 (렌더링 직전 인터셉트):**

    > ⚠️ **파이프라인 변경 (2026-04):** 기존의 '파이썬 자동 생성' 방식을 폐기.
    > 렌더링 직전에 Custom 항목을 일괄 검출하여 팝업을 띄우고,
    > **사용자가 프롬프트를 복사해 Claude Code에 수동 코딩을 지시하는 Human-in-the-loop 형태**로 변경됨.

    - **인터셉트:** `_on_render_click()` 호출 시, 렌더를 즉시 시작하지 않고 `effects[]`에서 `type: "Custom"` 항목을 먼저 전수 추출.
    - **조건 분기:**
      - Custom 항목 없음 → `_start_render()` 즉시 호출 (팝업 없음).
      - Custom 항목 있음 → `PreflightDialog` 팝업 표시 (렌더 일시 정지).
    - **PreflightDialog 역할 (`steps/step4.py`):**
      - Custom 효과 목록(id + description) 표시.
      - 통합 지시문 프롬프트 자동 조합:
        ```
        기획안에 포함된 아래 Custom 효과들을 src/components/fx/ 폴더에
        각각 TSX 컴포넌트로 코딩해 줘. commonProps와 specificProps의
        기본값을 세팅하고, 완성 후 fx_catalog.md에 등록해 줘.
        - [id: {id}] 연출 설명: {description}
        ```
      - `프롬프트 복사` 버튼 → QClipboard 복사.
      - `코딩 완료 (렌더링 계속)` 버튼 → `accept()` → `_start_render()` 호출.
      - `취소` 버튼 → `reject()` → 렌더 중단.
    - **TSX Props 규칙:** Claude가 생성하는 컴포넌트는 `commonProps`(노출 시간, x/y, 크기)와 고유 Props(`specificProps`)를 분리하여 기본값으로 설정. 파이썬이 `specificProps`를 `remotion_plan.json`에 역주입하여 기획안을 완전하게 업데이트.

6.  **스마트 부분 렌더링 (Diff Check):**
    - Remotion 렌더링 시 전체 타임라인을 단일 영상으로 뽑지 말고, 기획안(JSON)에 정의된 각 효과(Popup, FX)를 개별 파일(`fx_001.webm` 등)로 분할 렌더링하십시오.
    - 기획안이 수정되어 재렌더링 할 경우, 파이썬은 이전 JSON과 수정된 JSON을 비교하여 **내용이 변경된 특정 컴포넌트만 타겟팅하여 재렌더링(중복 렌더링 방지)**하는 최적화 로직을 반드시 구현해야 합니다.

7.  **Vrew 프로젝트 조립 (4단계 '최종 Vrew 파일 생성' 버튼 클릭 시):**
    - 입력: 투명 렌더링 된 개별 Remotion 영상들, 사용자가 업로드한 `원본.vrew`, 다운로드된 이미지/인트로 에셋.
    - 출력: 파이썬이 `원본.vrew` 내부 JSON 구조를 파싱하여 기존 타임라인 위에 위 에셋들을 새로운 트랙 및 클립으로 매칭 삽입한 `최종_v0.vrew` 파일 생성.
    - **경로 정규화:** 조립 전 `_normalize_file_paths()` 함수가 기존 `files[]`의 절대 경로 필드(`filePath`, `localPath`, `sourcePath`, `path`)를 파일명만으로 자동 변환. 다른 PC에서 열 때 경로 오류 방지.

8.  **환경 자동 진단 (앱 시작 시 자동 실행):**
    - 구현: `utils/health_check.py > HealthCheckDialog`
    - 체크 항목: `node --version` / `ffmpeg -version` / `npx remotion --version` / `node_modules` 폴더 존재 여부
    - 미설치 항목은 ❌ 표시. `node_modules` 미설치 시 `npm install 실행` 버튼 제공 (백그라운드 QThread 실행).
    - `main.py`에서 `QTimer.singleShot(300, _show_health_check)`로 메인 윈도우 렌더 후 1회 자동 실행.

9.  **FX 갤러리 팝업 및 즐겨찾기 (`utils/fx_gallery.py`):**
    - 4단계 UI의 `🎨 FX 카탈로그 보기` 버튼으로 진입.
    - `fx_catalog.md`를 파싱하여 FX 카드 목록 표시 (툴팁: Props 상세정보).
    - **메모리 캐시:** 모듈 레벨 `_catalog_cache` 변수에 최초 1회 파싱 결과 저장. 이후 재진입 시 파일 I/O 없이 즉시 표시.
    - **즐겨찾기:** ★ 체크박스 선택 후 `즐겨찾기 적용` 클릭 → `fx_catalog.md` 최상단 `## 즐겨찾기 (Favorites)` 섹션 자동 갱신.
    - **캐시 무효화:** fx_catalog.md 변경 시 `invalidate_cache()` 반드시 호출 (Custom FX 자동 등재 직후 포함).

10. **AI 기획 지시문 생성 (Gemini API, 4단계 STEP D):**
    - 라이브러리: `google-generativeai` (`pip install google-generativeai`)
    - 모델: `gemini-2.5-flash`
    - API Key: workspace 루트 `config.json`의 `gemini_api_key` 필드에 저장 (평문). 앱 재시작 시 자동 로드.
    - 입력 소스: `project_dir/input/script_body_slide.txt` (시간 정보가 없는 대본 원문 — JSON보다 문맥 보존 우수)
    - 출력: 슬라이드별 핵심 키워드 + 연출 분위기 + 권장 시각 효과 요약 → `QClipboard`에 자동 복사.
    - 라이브러리 미설치 시 `ImportError`를 사용자 친화적 메시지(`pip install` 안내)로 표시.

11. **렌더링 완료 리포트 (4단계 상태창):**
    - 렌더링 완료 시 `C_HIGHLIGHT` 골드 색상으로 아래 정보를 상태창에 출력:
      - 총 소요 시간 / 신규 렌더 FX 수 / 캐시 재사용 수(Diff-Check 절약분) / 전체 FX 합계
    - 구현: `_render_start_time` (float), `_render_done_count`, `_skip_count` 인스턴스 변수로 추적.

12. **글로벌 FX 라이브러리 및 공유 에셋 통합 아키텍처 (2026-04 구현):**

    > **핵심 원칙:** 모든 공용 리소스(영상, 시각효과 코드)는 `shared_assets/` 폴더 내에서 통합 관리된다.
    > FX 코드는 **심볼릭 링크(Symbolic Link)**를 통해 모든 프로젝트가 단일 원본을 공유한다.

    **폴더 구조:**
    ```
    Vivid_Workspace/
    ├── shared_assets/
    │   ├── shared_fx/          ← 글로벌 FX TSX 원본 (Git 추적 O)
    │   │   ├── RainFX.tsx
    │   │   └── ...
    │   ├── bumper.mp4          ← 채널 공용 영상 (Git 추적 X)
    │   └── .gitignore          ← *.tsx 추적 허용, *.mp4 등 제외
    └── {ProjectName}/
        └── remotion/src/components/fx/  ← shared_fx/ 를 가리키는 심볼릭 링크
    ```

    **심볼릭 링크 구축 (`steps/step1.py > _setup_fx_symlink()`):**
    - 프로젝트 폴더 생성(`copytree`) 직후 자동 실행.
    - 프로젝트 내 `remotion/src/components/fx/` 폴더를 삭제.
    - `os.symlink(SHARED_FX_DIR, fx_dir, target_is_directory=True)` 로 심볼릭 링크 생성.
    - **Windows 권한 처리:** `OSError` 발생 시 폴백으로 `shared_fx/` 내용을 복사하고 안내 메시지 출력.
      (해결: Windows '개발자 모드' 활성화 또는 PowerShell 관리자 권한 실행)
    - 링크 대상 `SHARED_FX_DIR`가 없으면 자동 생성 (`mkdir(parents=True, exist_ok=True)`).

    **Custom FX 저장 경로 (`steps/step4.py > _process_custom_fx()`):**
    - Custom FX TSX 파일은 **반드시 `SHARED_FX_DIR`(`shared_assets/shared_fx/`)에 저장**.
    - 프로젝트별 `fx_dir`에 직접 저장하지 않는다.
    - `fx_catalog.md` 경로 표기는 `src/components/fx/{fileName}` 유지 (심볼릭 링크를 통한 Remotion import 경로).

    **Git 추적 규칙 (`shared_assets/.gitignore`):**
    - `*.mp4`, `*.mp3`, `*.webm` 등 미디어 바이너리 → 추적 제외.
    - `shared_fx/`, `shared_fx/**`, `shared_fx/*.tsx` → `!` 예외 규칙으로 명시적 추적 허용.


## 2. UI/UX 및 기능 요구사항

**1단계 화면) 프로그램 생성**
- 화면 상단 제목 : '1. 프로그램 생성'
- 화면 구성 : ① '상태창', ② '입력창', ③ 'NEXT' 버튼
1) 프로그램 실행 시 상태창에 '프로젝트 폴더명(영문)을 입력하세요' 출력.
2) 입력창에 폴더명 입력 시 Project_templete 폴더가 복제되고 폴더명 변경. 상태창에 '프로젝트 폴더가 생성되었습니다. 다음 단계로 넘어가세요' 출력.
3) 사용자가 'NEXT' 버튼을 클릭하면, 2단계로 넘어간다.

**2단계 화면) 대본 기획**
- 화면 상단 제목 : '2. 대본 기획'
- 화면 구성 : ① '상태창', ② Drag&Drop 영역, ③ '대본 업로드' 버튼, ④ '대본 변환' 버튼, ⑤ 'NEXT' 버튼
1) 상태창에 '대본 파일(script.txt)을 입력하세요' 출력.
2) 사용자가 script.txt 업로드 시 프로젝트 폴더 내 저장 후 '대본 파일이 저장되었습니다' 출력.
3) '대본 변환' 버튼 활성화. 클릭 시 Python 명령어 실행되어 분할 텍스트 3종('script_intro.txt', 'script_body.txt', 'script_body_slide.txt') 생성 후 '대본 변환이 완료되었습니다. 다음 단계로 넘어가세요' 출력.
4) 사용자가 'NEXT' 버튼을 클릭하면, 3단계로 넘어간다.

**3단계 화면) 소스 제작 및 Vrew 데이터 추출**
- 화면 상단 제목 : '3. 소스 제작'
- 화면 구성 : ① '상태창', ② 'Watchdog 실행' 버튼, ③ '스토리보드 pdf 생성' 버튼, ④ Drag&Drop 영역, ⑤ 'Vrew 원본, MP3, SRT 업로드' 버튼, ⑥ '타임라인 JSON 생성', ⑦ 'NEXT' 버튼
1) 상태창: 'Flow 웹사이트에서 인트로 이미지를 생성 후 Watchdog을 활성화 하세요'.
2) 사용자는 Flow 웹사이트에서 인트로 이미지를 생성하고, 'Watchdog 실행'버튼을 클릭한다. 그러면 상태창에 '스토리보드 이미지와 인트로 영상을 다운받으세요' 라는 메세지가 출력된다.
3) 사용자가 Flow/Grok에서 에셋 다운로드 시 Watchdog이 image_n.jpeg, intro_n.mp4로 변환하여 저장. 상태창에 실시간 카운트 출력.
4) 상태창에는 '스토리보드 이미지 *장, 인트로영상 *개 확인되었습니다. 모두 생성되었으면 스토리보드 pdf 생성을 진행하세요' 라는 메세지가 출력된다.
5) '스토리보드 pdf 생성' 버튼을 누르면, Python 명령어가 실행되어 스토리보드 이미지(image_n.jpeg)가 병합되어 하나의 pdf파일이 생성된다(storyboard.pdf 로 저장). 
6) 상태창: 'Vrew에서 대본을 붙여넣고 초안을 만든 뒤, [원본.vrew], [TTS.mp3], [Subtitle.srt] 3개 파일을 업로드하세요'.
7) 사용자 3개 파일 업로드 시 저장소 이동 및 상태창에 '파일 3개 모두 확인되었습니다. 타임라인을 생성해주세요' 출력. 
8) 사용자가 '타임라인 JSON 생성' 클릭 시 base_timeline.json 생성. 상태창에 '타임라인이 생성되었습니다. 다음 단계로 넘어가세요' 출력.
9) 사용자가 'NEXT' 버튼을 클릭하면, 4단계로 넘어간다.

**4단계 화면) 기획안 입력 및 최종 Vrew 생성**
- 화면 상단 제목 : '4. 영상 기획안 및 조립'
- 화면 구성 : ① '상태창', ② Drag&Drop 영역, ③ '기획안 업로드' 버튼, ④ 'Remotion 미리보기' 버튼, ⑤ 'Remotion 투명 렌더링' 버튼, ⑥ '최종 Vrew 파일 생성' 버튼, ⑦ 'Vrew 열기' 버튼
1) 상태창: '제미나이(웹)에 storyboard.pdf와 fx_catalog.md를 참고하여 만든 영상 기획안(remotion_plan.json)을 업로드 하세요'.
2) 사용자 파일 업로드 완료 시, 'Remotion 미리보기' 및 'Remotion 투명 렌더링' 버튼 활성화.
3) 'Remotion 미리보기' 버튼 클릭 시, 로컬 브라우저가 열리며 렌더링 전 시각 효과의 타이밍과 디자인을 즉시 검수할 수 있음.
4) 검수 완료 후 'Remotion 투명 렌더링' 버튼 클릭 시 Remotion 엔진이 실행되어 배경이 투명한 시각 효과 오버레이 영상 렌더링 진행. (Diff Check에 의해 변경된 클립만 타겟 렌더링됨. 상태창에 진행률 표시)
5) 렌더링 완료 후 '최종 Vrew 파일 생성' 버튼 활성화. 클릭 시 파이썬 백엔드가 원본.vrew와 렌더링된 오버레이 영상, 에셋들을 결합하여 최종_v0.vrew를 생성.
6) 'Vrew 열기' 버튼 활성화. 클릭 시 PC에 설치된 Vrew 프로그램이 실행되며 최종_v0.vrew 파일이 열림.
7) (수정이 필요한 경우) 사용자는 수정된 기획안을 다시 업로드하고 4~6 과정을 반복할 수 있으며, 이때 파일은 최종_v1.vrew, v2.vrew 형태로 자동 넘버링되어 저장됨.