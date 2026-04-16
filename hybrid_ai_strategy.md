# 🔀 하이브리드 AI 전략 — VIVID 시스템 모델 운용

> **최종 수정일**: 2026-04-13
> **버전**: v4.0 (Google 생태계 통일 + Qwen 조건부 도입)
> **관련 문서**: [second_brain_strategy.md](second_brain_strategy.md) — Second Brain 구축 전략

---

## 📌 1. PC 사양 및 AI 추론 능력

| 항목        | 사양                                            | AI 관점                      |
| :---------- | :---------------------------------------------- | :--------------------------- |
| **CPU**     | Intel Core Ultra 5 125H (14코어/18스레드)       | ✅ CPU 추론 가능 (llama.cpp) |
| **RAM**     | 16GB DDR5 (15.5GB 가용)                         | ⚠️ E4B 쾌적. 9B 조건부       |
| **GPU**     | Intel Arc iGPU (128MB 전용 + **최대 8GB 공유**) | ✅ IPEX-LLM iGPU 가속 가능   |
| **NPU**     | Intel AI Boost                                  | ❌ Ollama 미지원 (2026.04)   |
| **Storage** | 477GB NVMe SSD (401GB 사용 중)                  | ⚠️ 모델 저장 공간 한정적     |

> [!IMPORTANT]
> Intel Arc iGPU는 필요 시 시스템 RAM에서 **최대 8GB까지 공유 메모리로 확장** 가능하다. Gemma 4 E4B(~6GB)는 쾌적하게 구동되며, Qwen 3.5 9B(~6GB)도 조건부로 올릴 수 있다.

---

## 🏆 2. 로컬 AI 모델 전략 — Google 생태계 통일

### 모델 구성 (Gemma 우선, Qwen 조건부)

```
Tier 1 (주력)     : Gemini CLI / Claude Code (Pro 구독)
                    → 코드 작성, 기획안 생성, 심층 분석

Tier 2 (로컬 메인) : Gemma 4 E4B (Q4_K_M) via Ollama
                    → 제목 100개 생성, 요약, 분류, 검수
                    → 다른 앱과 병행 가능

Tier 3 (초경량)    : Gemma 4 E2B via Ollama
                    → 태그 분류, 키워드 추출 등 최경량 작업

Tier 4 (조건부)    : Qwen 3.5 9B (Q4_K_M)
                    → E4B 제목 품질 불만족 시에만 도입
                    → 단독 실행 모드 (다른 앱 종료 후 사용)
```

> [!NOTE]
> **「Google 생태계 통일」 원칙**: 클라우드(Gemini CLI)와 로컬(Gemma)을 같은 Google 생태계로 통일하면 프롬프트 호환성·출력 스타일이 일관된다. Qwen은 프롬프트 분기 오버헤드가 있으므로 보조로만 사용한다.

### 작업별 모델 배분 — 사용자 토글 전환 방식

| 작업                       | 기본값          | 토글 전환     | 비고                      |
| :------------------------- | :-------------- | :------------ | :------------------------ |
| 제목 100개 대량 생성 (A3)  | **Gemma E4B**   | 🔄 **Gemini** | 토글로 전환 가능          |
| 분류/태깅/검수 (A1, A2)    | **Gemma E4B**   | 🔄 **Gemini** | 토글로 전환 가능          |
| 경량 작업 (키워드 추출 등) | **Gemma E2B**   | 🔄 **Gemini** | 토글로 전환 가능          |
| 코드/기획/심층 분석        | **Gemini** only | -             | 전환 불가 (클라우드 전용) |

> [!NOTE]
> **토글 전환 이유**: Gemini 한도가 넉넉하거나, 더 신뢰할 수 있는 결과를 원하거나, 빠른 응답이 필요할 때는 경량 작업이라도 Gemini를 사용할 수 있다. UI에서 토글 버튼으로 로컬↔클라우드를 즉시 전환한다.

> [!IMPORTANT]
> **클라우드는 Gemini only**: Gemini는 Google 로그인(OAuth) 방식으로 구독 한도 내에서 프로그램 호출이 가능하다. 반면 Claude Pro 구독은 claude.ai 웹 + Claude Code CLI 전용이며, **커스텀 프로그램에서 로그인 방식 호출이 불가**하다 (별도 API 크레딧 필요). 따라서 VIVID에서 프로그래밍 방식으로 호출하는 클라우드 모델은 Gemini로 한정한다.

### 생태계 전환 로드맵

> [!IMPORTANT]
> **미래 업그레이드의 핵심은 더 큰 모델이 아니라, 같은 메모리(~6GB)에서 세대별 품질 향상이다.**

```
현재    Gemma 4 E4B (~6GB) = 품질 A
 ↓      Gemma 5 E4B (~6GB) = 품질 A+   ← 같은 메모리, 더 좋은 모델
 ↓      Gemma 6 E4B (~6GB) = 품질 S    ← MoE로 20B급 지능도 가능
 ※ 전환 비용 = ollama pull + ai_router 한 줄 변경
```

---

## ⚙️ 3. A3 FindTitle 파이프라인

```
Phase 1: 전략 수립 (Gemini API) → 키워드 5전략 생성
Phase 2: 제목 생성 (Gemma E4B)  → 100개 생성 → 모델 언로드
Phase 3: Playwright 검증        → 시크릿 유튜브 검색 → 상위 5개 선정
```

**Qwen 9B 도입 기준**: 100개 중 30%+ 패턴 반복 / 상위 5개 AI 라벨 노출률 저조 / 표현 다양성 체감 부족

> [!WARNING]
> **Qwen 9B 도입 시 운용 원칙**: 9B 모델과 Playwright를 동시 구동하면 RAM이 부족하다. 반드시 **순차 분리**(9B 생성 완료 → `ollama stop` 언로드 → Playwright 검증)로 실행해야 하며, 다른 무거운 앱은 종료 후 사용한다.

---

## 🎬 4. VIVID Workspace 모듈별 AI 배분

### 🟢 로컬 AI 대체 가능 영역

| 모듈                | 작업              | 로컬 모델           | 절약       |
| :------------------ | :---------------- | :------------------ | :--------- |
| A3 (FindTitle)      | 제목 100개 생성   | Gemma E4B → Qwen 9B | ⭐⭐⭐⭐⭐ |
| A3 (FindTitle)      | 제목 검수/교정    | Gemma E4B           | ⭐⭐⭐     |
| A1 (ChannelScout)   | AI 라벨 판별/분류 | Gemma E4B           | ⭐⭐⭐     |
| A2 (TopicDiscovery) | 주제 분류         | Gemma E4B           | ⭐⭐⭐     |

### 🟡 하이브리드 (클라우드 + 로컬 폴백)

| 모듈   | 작업             | 로컬 폴백          |
| :----- | :--------------- | :----------------- |
| A3     | 키워드 전략 수립 | Gemini 한도 시 E4B |
| Step 4 | AI 기획 지시문   | 키워드 추출만 E4B  |

### 🔴 클라우드 전용

| 모듈      | 작업             | 이유               |
| :-------- | :--------------- | :----------------- |
| Step 4    | 기획안/FX 코딩   | 로컬 품질 부족     |
| 전체 개발 | 시스템 코드 작성 | Gemini/Claude 전용 |

---

## 🔧 5. ai_router 모듈 설계

```python
# vivid_radar/vivid_core/ai_router.py
import requests

OLLAMA_API = "http://localhost:11434"

# 모델 전환 시 이 딕셔너리만 변경
DEFAULT_MODELS = {
    "creative":  "gemma4:e4b",    # 품질 부족 시 → "qwen3.5:9b"
    "classify":  "gemma4:e4b",
    "lighttag":  "gemma4:e2b",
}

class AIRouter:
    """Gemini API 한도 시 로컬 Ollama 자동 폴백."""

    def __init__(self, models=None):
        self._models = models or DEFAULT_MODELS

    def generate(self, prompt, task_type="creative"):
        model = self._models.get(task_type, "gemma4:e4b")
        return self._call_ollama(model, prompt)

    def generate_with_fallback(self, prompt):
        try: return self._call_gemini(prompt)
        except: return self._call_ollama(self._models["creative"], prompt)

    def unload_model(self, model):
        """RAM 해제를 위한 모델 명시적 언로드"""
        requests.post(f"{OLLAMA_API}/api/generate",
                      json={"model": model, "keep_alive": 0})

    def _call_ollama(self, model, prompt):
        resp = requests.post(f"{OLLAMA_API}/api/generate",
                             json={"model": model, "prompt": prompt, "stream": False})
        return resp.json()["response"]
```

> [!TIP]
> **모델 전환은 `DEFAULT_MODELS` 딕셔너리 한 줄 변경으로 완료된다.** 차세대 Gemma E4B가 출시되면 `ollama pull gemma5:e4b` → 딕셔너리 값 변경으로 즉시 업그레이드.

---

## 🚀 6. 액션 플랜

### Phase 1: 로컬 AI 환경 (~20분)

```powershell
winget install Ollama.Ollama
ollama pull gemma4:e4b        # 메인 로컬 모델 (~3.5GB)
ollama pull gemma4:e2b        # 초경량 태깅 (~2GB)
ollama run gemma4:e4b "유튜브 제목 5개 생성해줘: 이란 전쟁 최신 상황"
```

### Phase 2: ai_router 모듈 개발

- `vivid_radar/vivid_core/ai_router.py` 생성
- Gemini API → Ollama 자동 폴백 + 모델 언로드 구현
- A3 모듈 제목 대량 생성에 즉시 적용

### Phase 3: E4B 품질 평가

- Gemma E4B로 제목 100개 생성 테스트
- 반복률, 다양성 체크 → 기준 미달 시 Qwen 9B 도입

---

## 💡 7. 비용 최적화 요약

```
현재: Gemini CLI + Claude Code (모든 작업)
  ↓
최적화 후 (사용자 토글 전환):
  - 대량 생성 (제목 100개)  → Gemma E4B 🔄 Gemini (토글)
  - 분류/태깅/검수          → Gemma E4B 🔄 Gemini (토글)
  - 경량 작업               → Gemma E2B 🔄 Gemini (토글)
  - 코드/기획/심층 분석     → Gemini only (전환 불가)

로컬 기본 사용 시: 토큰의 ~40-50% 절약
Gemini 전환 사용 시: 구독 한도 내 무료 (속도↑ 품질↑)
속도 참고: E4B 초당 15-25 토큰 / Gemini 초당 ~100+ 토큰
```
