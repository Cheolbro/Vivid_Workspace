작성일 : 2026-04-16
수행 모델 : Claude code sonnet 4.6
제목 : VIVID 프로그램 개발을 통한 insight

[범용 개발 인사이트 — 다음 프로젝트에 적용할 원칙]

1. AI 도구 활용 전략
✅ 적용할 것
- AI마다 강점이 다르다 — 역할을 명확히 분리하라
이번 세션에서 Claude, Gemini CLI, Gemma4 e4b를 각각 다른 역할에 배치했을 때 효율이 가장 높았다.
AI	잘하는 것	못하는 것
Claude	기존 코드 수정, 논리 판단, 검수	대량 반복 생성
Gemini CLI	전략 수립, 구조화 분석, JSON 출력	코드 파일 직접 수정
Gemma (로컬)	대량 창의적 생성	복잡한 논리, 코드
적용 원칙: 신규 boilerplate 생성은 위임 가능, 기존 파일 수정은 직접 하라. AI가 수정한 파일은 반드시 diff 검수.

- AI에게 "어떻게 해야 잘 하냐"고 직접 물어라
이번 세션에서 Gemma에게 "제목 생성을 잘 수행하려면 프롬프트를 어떻게 줘야 하냐"고 물었더니 최적 프롬프트 구조, 출력 형식, 변형 축까지 스스로 설계해줬다. 이것을 그대로 코드에 반영했을 때 파싱 안정성이 크게 향상됐다.
원칙: AI 프롬프트를 사람이 설계하기 전에, 해당 AI에게 먼저 물어보라.

- AI 응답 파싱은 항상 3단계 fallback으로 설계하라
AI 출력은 지시해도 형식이 흔들린다. 파싱 로직을 단층으로 짜면 하나가 실패할 때 전체가 깨진다.
1차: 가장 엄격한 형식 (JSON, 괄호 패턴 등)
2차: 중간 형식 (쉼표 구분 등)
3차: 가장 관대한 형식 (줄 단위)

❌ 지양할 것
- AI가 수정한 파일을 검수 없이 사용하지 마라
이번 세션에서 Gemini가 Python 파일의 모든 따옴표를 escape(" → \")시켜 SyntaxError를 유발했고, TypeScript 파일에 Python 문법(try:)을 삽입했다. 발견하기 전까지 원인을 모른다. git diff로 반드시 확인하라.

- AI에게 책임을 위임하지 마라
"이걸 바탕으로 알아서 고쳐줘" 방식은 실패한다. AI는 컨텍스트가 없으면 범용적인 방향으로 처리한다. 파일 경로, 라인 번호, 변경할 내용을 명시하면 실수가 줄어든다.

2. 인증 / 외부 서비스 연동
✅ 적용할 것
- 인증 방식의 실제 동작을 코드로 검증하고 문서화하라
이번 세션에서 OAuth peruserquota 스코프가 "사용자 구독 한도를 우회할 것"이라고 기대했지만 실제로는 프로젝트 무료 티어 한도가 그대로 적용됐다. 공식 문서와 실제 동작이 다른 경우가 많다.
원칙: 외부 서비스 연동 시 "이렇게 될 것이다"가 아니라 실제 응답의 에러 메시지, quota ID, scope를 직접 확인하라.

- CLI 도구를 API 대신 사용하는 옵션을 검토하라
이번 케이스에서 API 키 방식은 quota 한도가 있었지만, 동일 서비스의 CLI 도구는 로그인 구독 권한을 그대로 사용했다. 서비스에 따라 CLI가 더 높은 권한을 갖는 경우가 있다.
서비스 연동 실패는 절대 silent swallow하지 마라
* ❌ 나쁜 예 — OAuth 실패를 무시하고 fallback
try:
    return get_genai_client()
except Exception:
    pass  # 조용히 API 키로 fallback
* ✅ 좋은 예 — 실패를 노출
if secret.exists():
    return get_genai_client()  # 실패 시 에러 그대로 전파
except: pass 패턴은 "왜 안 되지?"를 디버깅하는 데 몇 시간을 낭비하게 만든다.

❌ 지양할 것
- OAuth 토큰 캐시 만료를 사용자가 직접 관리하게 하지 마라
token.json이 만료된 줄 모르고 "왜 한도에 걸리지?"를 몇 번씩 시도했다. 캐시 토큰을 사용할 때는 만료 여부를 앱 시작 시 자동 확인하고 재발급 흐름을 자동화하라.

3. 프로세스 간 통신 (subprocess / IPC)
✅ 적용할 것
- Windows에서 외부 CLI 실행 시 PATH를 믿지 마라
터미널에서 되는 명령이 Python 서버에서 [WinError 2]로 실패하는 경우가 흔하다. npm, conda, pyenv 등으로 설치된 도구는 특히 취약하다.
def _find_exe(name: str) -> str:
    # 1. 일반 PATH 탐색
    found = shutil.which(name) or shutil.which(f"{name}.cmd")
    if found: return found
    # 2. Windows npm 글로벌 경로 직접 확인
    appdata = os.environ.get("APPDATA", "")
    candidate = Path(appdata) / "npm" / f"{name}.cmd"
    if candidate.exists(): return str(candidate)
    raise RuntimeError(f"{name} not found")

- async 서버에서 블로킹 I/O는 반드시 스레드풀로 분리하라
FastAPI, asyncio 기반 서버에서 subprocess.run()이나 파일 I/O 같은 블로킹 호출을 직접 실행하면 해당 시간 동안 서버 전체가 멈춘다.

* ✅
raw = await asyncio.get_event_loop().run_in_executor(None, blocking_fn, arg)

- 외부 프로세스 출력에는 항상 ANSI 제거를 적용하라
CLI 도구 출력에는 색상 코드(\x1b[32m 등)가 포함될 수 있다. 특히 JSON 파싱 전에 반드시 제거하지 않으면 조용히 실패한다.

_ANSI = re.compile(r"\x1b\[[0-9;]*[mGKHF]")
clean = _ANSI.sub("", raw).strip()

❌ 지양할 것
- CLI 도구의 interactive 플래그를 자동화에 쓰지 마라
 '--yolo' 처럼 "모두 자동 승인" 플래그는 interactive 환경 전용이다. 자동화 파이프라인에서 사용하면 도구가 주변 파일을 스캔하거나 예기치 않은 동작을 할 수 있다. 항상 non-interactive 옵션(-p, --no-input 등)을 탐색하라.

4. 파일 수정 / 되돌리기 패턴
✅ 적용할 것
- 사용자가 확인하기 전에는 원본을 덮어쓰지 마라 — staged editing 패턴
파일을 즉시 수정하는 대신 3단계를 거치면 실수를 방지할 수 있다:

1. preview  → .bak 백업 생성 후 새 내용 저장 (사용자가 결과 확인)
2. revert   → .bak 복원 (마음에 안 들면)
3. commit   → .bak 삭제 (영구 확정)
AI가 코드를 생성하고 즉시 적용하는 워크플로우, 설정 파일 마이그레이션, 데이터 변환 등 "되돌리고 싶어질 수 있는 모든 작업"에 적용 가능하다.

- 백업 파일명은 .with_suffix() 대신 .name + ".bak"을 써라

* ❌ OilLeakFX.tsx → OilLeakFX.bak (확장자 유실)
backup = fx_path.with_suffix(".bak")

* ✅ OilLeakFX.tsx → OilLeakFX.tsx.bak
backup = fx_path.parent / (fx_path.name + ".bak")

5. 상태 없는 API에 맥락 붙이기
✅ 적용할 것
- Stateless API에 대화 맥락을 붙이는 가장 단순한 방법 — 슬라이딩 윈도우
서버가 세션 상태를 관리하지 않아도, 클라이언트가 최근 N개 메시지를 매 요청에 포함시키면 맥락이 유지된다. 파일 저장, DB 불필요.
전체 히스토리를 보내면 토큰/응답 시간이 증가하므로 최근 6~10개가 적당
system 메시지는 제외하고 user / assistant 역할만 포함
서버는 이를 User: ... / AI: ... 텍스트로 프롬프트 앞에 붙이기만 하면 됨

6. 로컬 AI 서버 통합
✅ 적용할 것
- 로컬 모델은 비용 없는 대량 생성에, 클라우드 모델은 품질이 중요한 판단에 분리 배치하라

역할	적합한 모델
전략 수립, 코드 생성, 구조 분석	클라우드 (Gemini, Claude)
대량 반복 생성, 창의적 변형	로컬 (Gemma, Llama 등)
비용과 속도 트레이드오프를 작업 특성에 맞게 배분하면 전체 파이프라인 효율이 올라간다.

- 외부 서버 의존 기능은 항상 자동 기동 + 상태 확인 로직을 포함하라
def ensure_service_running(check_fn, start_fn, wait_sec=15) -> bool:
    if check_fn(): return True
    start_fn()  # 백그라운드 기동
    deadline = time.time() + wait_sec
    while time.time() < deadline:
        time.sleep(1)
        if check_fn(): return True
    return False
사용자가 서비스 상태를 직접 확인하게 하면 UX가 나빠진다. 앱이 알아서 기동하고 안 되면 명확한 에러 메시지를 주는 것이 맞다.

7. 가장 중요한 단일 원칙
이번 세션 전체를 관통하는 핵심 교훈 하나를 꼽으면:

"조용히 실패하는 코드는 디버깅 시간을 몇 배로 늘린다."

OAuth가 실패해도 except: pass로 묻었고, Gemini가 파일을 오염시켜도 에러 없이 통과했다. 모든 외부 의존성(API, CLI, 파일, 서버)은 실패 시 명확하게 알려야 한다. silent fallback은 편리해 보이지만 결국 근본 원인을 숨겨서 추후 더 큰 비용을 초래한다.

8. 타입 정의 전에 반드시 실제 API 응답부터 확인하라
- 이번 세션 최대 낭비 원인: TypeScript Effect 인터페이스를 eff.props, eff.x, eff.y 기준으로 작성했지만, 실제 API는 commonProps, specificProps, text, src를 반환했다. 타입 오류도 없고 런타임 에러도 없이 조용히 undefined가 흘러 FX가 전혀 렌더링되지 않았다.

- UI 코드 작성 전 먼저 실행하라
curl http://localhost:8000/api/plan | python -m json.tool | head -60
원칙: 인터페이스를 설계할 때 "이렇게 올 것이다"가 아니라 실제 응답을 먼저 복사하고 그것을 타입으로 역산하라.

9. 좌표계는 반드시 컴포넌트 소스 1개를 읽고 검증하라
- EditWrapper의 FX 위치가 전부 틀렸던 원인: FX x/y가 절대 좌표라고 가정했지만 실제로는 CENTER-RELATIVE였다. 수십 줄의 좌표 변환 코드를 작성하고 나서야 HighlighterFX.tsx 두 줄을 보고 발견했다:

// HighlighterFX.tsx line 89
const cx = width / 2 + x;  // x는 화면 중앙 기준 오프셋
원칙: 외부 컴포넌트와 좌표 연동 코드를 짜기 전, 해당 컴포넌트 소스에서 x/y가 실제로 어떻게 쓰이는지 1분만 확인하라. 문서보다 소스가 정확하다.

10. 동일 라이브러리가 여러 패키지에 걸쳐 있으면 번들러에서 강제 단일화하라
- useCurrentFrame() 같은 React Context 기반 훅은 호출 측과 Provider 측이 동일한 라이브러리 인스턴스를 사용해야 한다. vivid_studio와 dry_test/remotion이 각각 별도 node_modules/remotion을 가지면 FX가 아무런 에러 없이 null을 반환한다.

// vite.config.ts
resolve: {
  alias: {
    "remotion": path.resolve(__dirname, "node_modules/remotion"),  // 단일 인스턴스 강제
    "react":    path.resolve(__dirname, "node_modules/react"),
  }
}
원칙: 모노레포나 cross-package 컴포넌트 재사용 시, React/Remotion 등 Context 기반 라이브러리는 번들러 alias로 단일 인스턴스를 보장하라. 인스턴스 분리는 에러 없이 조용히 기능이 죽는다 — 찾는 데 가장 오래 걸리는 버그 유형 중 하나.

11. 인터랙티브 위젯의 onChange는 부모를 즉시 건드리지 않도록 설계하라 — Draft 상태 패턴
- 드래그형 UI 위젯(ColorPicker, Slider 등)에서 onChange → 부모 setState → 트리 재렌더링 루프는 드래그 중 picker 위치가 초기값으로 튀는 시각적 버그를 유발한다.

// ❌ 문제 패턴: onChange마다 부모 상태 즉시 업데이트
<HexColorPicker color={value} onChange={onChange} />

// ✅ Draft 패턴: 로컬 상태로 보관, 완료 시점에만 커밋
const [draft, setDraft] = useState(value);
// 팝업 닫힐 때만 onChange(draft) 호출
<HexColorPicker color={draft} onChange={setDraft} />
적용 범위: 색상 피커, 오디오 볼륨 슬라이더, canvas 드래그 등 "빠른 연속 이벤트 + 무거운 부모 재렌더링"이 겹치는 모든 위젯.

12. 렌더링 엔진과 인터랙션 레이어는 DOM 트리에서 완전히 분리하라
- Remotion Player (렌더링)와 react-rnd (드래그 핸들) 혼합 시도는 실패했다. Player 내부는 Remotion의 Context와 좌표계를 쓰고, react-rnd는 DOM 픽셀 기반 이벤트를 쓴다. 두 개를 같은 서브트리에 넣으면 좌표 변환과 이벤트 핸들링이 충돌한다.

┌─ canvas container (640×360) ──────────────────────┐
│  z:3  Player (렌더링 전용, pointerEvents: none)   │  ← 건드리지 마라
│  z:10 react-rnd overlay (인터랙션 전용, 투명)      │  ← 여기서만 이벤트
└────────────────────────────────────────────────────┘
원칙: 서드파티 렌더링 엔진을 UI 에디터에 임베드할 때, 렌더링과 인터랙션은 별도 z-index 레이어로 완전히 분리하라. 렌더 레이어에는 pointerEvents: none.

13. 확장 가능한 컴포넌트 시스템엔 glob 자동 레지스트리를 써라
- 새 FX를 추가할 때마다 DynamicSlide.tsx에 import와 switch case를 추가하는 패턴은 파일이 늘어날수록 유지보수 부채가 된다.

// import.meta.glob으로 자동 레지스트리 구성
const FX_MODULES = import.meta.glob("@rfx/fx/*.tsx", { eager: true });
const FX_REGISTRY: Record<string, React.ComponentType<any>> = {};
Object.entries(FX_MODULES).forEach(([path, mod]: [string, any]) => {
  const name = path.split("/").pop()?.replace(".tsx", "");
  if (name && (mod[name] || mod.default)) FX_REGISTRY[name] = mod[name] || mod.default;
});
// 이후 FX 추가 = 파일만 넣으면 끝. 코드 수정 불필요.
주의사항: import.meta.glob은 Vite 전용. Webpack은 require.context(), Node.js는 fs.readdirSync()로 대체. tsconfig.json에 "types": ["vite/client"] 추가 필요.

14. AI에게 기존 파일 수정 지시 시 find/replace 정확한 텍스트 치환 형식을 써라
기존 목록의 "파일 경로, 라인 번호, 변경할 내용을 명시하라"는 원칙의 구체적 구현 방법이다.

❌ 추상 설명 방식: "extractText 함수를 추가하고 EditWrapper가 텍스트를 렌더링하게 수정" → AI가 자유 해석 → 기존 코드 위에 중복 블록 추가, props 누락
✅ find/replace 방식: 수정할 코드 블록을 원문 그대로 find 필드에 복사하고, 교체할 내용을 replace 필드에 명시
{
  "type": "modify",
  "file": "vivid_studio/src/EditWrapper.tsx",
  "find": "interface EditWrapperProps {\n  effect: Effect;",
  "replace": "interface EditWrapperProps {\n  effect: Effect;\n  active?: boolean;"
}
원칙: AI 지시서에서 "무엇을 해야 한다"는 설명은 해석 여지를 준다. "이 텍스트를 이 텍스트로 교체하라"는 기계적 치환은 해석 여지가 없다. 기존 파일 수정 = 무조건 find/replace 형식.

15. 검증(verify)은 코드를 작성한 AI가 직접 실행하고 자기 수정까지 완료하게 하라
이번 세션에서 Gemini가 MiniTimeline을 잘못 작성한 후, Claude가 TypeScript 검증을 실행했다. 이는 비효율적이다.

왜 builder가 verify를 해야 하는가: 코드를 작성한 직후 컨텍스트가 살아있는 상태에서 수정하는 것이 가장 빠르다. Claude가 하면 다시 파일을 읽고 오류 위치를 파악하는 round-trip이 추가된다.
max 2회 자기 수정 루프: 무한 루프 방지. 2회 내에 통과하지 못하면 Claude에게 에스컬레이션.
# 지시서 형식
"verify_after": "cd vivid_studio && npx tsc --noEmit"

# Gemini 호출 시 프롬프트에 포함
"완료 후 verify_after를 실행. 실패 시 에러를 수정하고 재실행. 최대 2회."
원칙: 검수(reviewer)와 검증(verifier)은 다른 역할이다. 검증은 builder에게, 검수(의미 판단)는 reviewer에게.

16. TypeScript 컴파일러를 AI 코드 생성의 의무 게이트로 활용하라
이번 세션에서 tsc --noEmit이 두 가지 버그를 잡아냈다:

currentFrame이 SlideCanvasProps 인터페이스에 없는 채로 컴포넌트 내부에서 사용됨
active prop이 EditWrapperProps에 선언되지 않은 채로 렌더 로직에서 참조됨
두 버그 모두 런타임 에러 없음, 빌드 에러 없음, 콘솔 경고 없음 — 조용히 undefined를 흘려보냈다. tsc --noEmit만이 잡아냈다.

# AI 코드 생성 후 의무 실행
npx tsc --noEmit      # TypeScript
python -m py_compile target.py  # Python
원칙: "동작하는 것처럼 보임"과 "타입이 맞음"은 다르다. AI가 생성한 TypeScript 코드는 반드시 컴파일러로 검증하라. props 누락, 타입 불일치는 런타임보다 컴파일러가 먼저 발견한다.

17. AI 도구 간 핸드오버 문서는 사람이 아닌 AI가 읽는 것으로 설계하라
이번 세션에서 GEMINI_CONTEXT.md를 만들었다. 일반 개발 문서(README, ADR)와 구조적으로 다르다.

항목	인간용 문서	AI용 핸드오버 문서
분량	충분히 설명	1페이지 이내 압축
내용	왜(WHY) 중심	무엇/어디서/어떻게(WHAT/WHERE/HOW) 중심
규칙	산문체 설명	규칙 목록 + 코드 예시
금지사항	암묵적	명시적 목록화 (절대 하지 말 것 N개)
핵심 구성 요소:

기술 스택 테이블 (AI, 프레임워크, 포트)
핵심 파일 경로 트리 (전체 구조 아님, 자주 건드리는 파일만)
아키텍처 규칙 (데이터 흐름, 상태 소유권)
코딩 컨벤션 (실제 코드 패턴 예시)
Guardrails — 절대 하지 말 것 (숫자로 열거)
원칙: AI는 문서에서 패턴을 추론하지 못한다. "이 컨벤션을 따르면 된다"가 아니라 "이 형태로 써야 한다"고 명시해야 한다. 모호함이 없는 규칙 목록이 인간이 공감하는 서술보다 AI에게 훨씬 효과적이다.

18. 개발 중 자동 포맷터가 AI 코드 수정 루프를 오염시킨다
이번 세션에서 Claude가 파일을 읽은 직후 Prettier auto-save가 실행되어 "file has been modified since read" 에러가 반복 발생했다. 해결 방법을 찾는 데 불필요한 시간이 소요됐다.

근본 원인: 읽기 → AI 수정 계획 → 수정 적용 사이에 포맷터가 파일을 변경
해결 옵션:
AI 작업 세션 중 에디터 auto-save 끄기
Python 스크립트로 atomic read+write (읽기와 쓰기를 단일 작업으로)
.editorconfig에 AI 생성 파일 제외 규칙 추가
# Atomic read+write 패턴
content = Path(target).read_text(encoding="utf-8")
content = content.replace(old_str, new_str)
Path(target).write_text(content, encoding="utf-8")
# 중간에 포맷터 개입 불가
원칙: AI 보조 개발 환경에서 자동 포맷터는 협력자가 아니라 방해자가 될 수 있다. 특히 여러 파일을 순차 수정하는 작업에서는 auto-save를 명시적으로 비활성화하라.

