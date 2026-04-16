import asyncio
import json
import re
import random
from pathlib import Path
from typing import List, Dict, Literal
from urllib.parse import quote
from vivid_core.scraper import BaseScraper
from vivid_core.db_manager import db
from vivid_core.logger import logger
from vivid_core.config_loader import config
from vivid_core.ai_helper import (
    call_gemini_cli_async,
    call_gemma_async,
    ensure_ollama_running,
)

# vivid_radar 폴더 내 절대 경로 기준 (CWD 무관)
_RADAR_DIR = Path(__file__).parent

TitleModel = Literal["gemma", "gemini"]

# 전략당 목표 제목 수 / 최대 재시도 횟수
_TARGET_PER_STRATEGY = 20
_MAX_RETRY           = 2


# ─────────────────────────────────────────────────────────────────────────────
# 1단계: AI 제목 생성
# ─────────────────────────────────────────────────────────────────────────────

class TitleGenerator:
    """
    1단계: 레퍼런스 분석 후 제목 변형본 100개 생성.

    title_model 파라미터로 제목 생성 모델을 선택할 수 있습니다.
    ┌─────────────┬───────────────────────────────┬───────────┐
    │ title_model │ 제목 생성 엔진                │ 예상 시간 │
    ├─────────────┼───────────────────────────────┼───────────┤
    │ "gemma"     │ Ollama gemma4:e4b (로컬, 기본) │ 30~90초   │
    │ "gemini"    │ gemini CLI (구독 권한)         │ 5~15초    │
    └─────────────┴───────────────────────────────┴───────────┘
    전략 수립은 항상 Gemini CLI (5~10초).
    """

    def __init__(self, references: List[str], title_model: TitleModel = "gemma"):
        self.references   = references
        self.title_model  = title_model
        self.temp_file    = _RADAR_DIR / "temp_titles.txt"

    async def run(self) -> List[str]:
        # ── Gemma 선택 시 Ollama 서버 자동 기동 ──────────────────────────────
        if self.title_model == "gemma":
            logger.info("[A3] Ollama 서버 상태 확인 중...")
            ok = await asyncio.get_event_loop().run_in_executor(
                None, ensure_ollama_running, 20
            )
            if not ok:
                raise RuntimeError(
                    "Ollama 서버를 20초 내에 기동하지 못했습니다.\n"
                    "터미널에서 'ollama serve' 를 수동 실행하거나, "
                    "모델을 'gemini' 로 변경하세요."
                )
            logger.info("[A3] Ollama 서버 준비 완료.")

        # ── Step 1: Gemini CLI → 5가지 전략 수립 ─────────────────────────────
        logger.info(f"[A3] Gemini CLI: {len(self.references)}개 레퍼런스 분석 중...")
        strategies = await self._fetch_strategies()
        if not strategies:
            raise RuntimeError("Gemini CLI가 유효한 전략을 반환하지 않았습니다.")
        logger.info(
            f"[A3] {len(strategies)}가지 전략 수립 완료. "
            f"제목 생성 모델: [{self.title_model.upper()}]"
        )

        # ── Step 2: 전략별 제목 생성 (병렬) ──────────────────────────────────
        tasks = [
            self._generate_with_retry(s, idx + 1, len(strategies))
            for idx, s in enumerate(strategies)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_titles: List[str] = []
        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"[A3] 전략 {idx+1} 최종 실패: {result}")
            else:
                all_titles.extend(result)

        # ── Step 3: 중복 제거 + 100개 미달 시 보충 생성 ──────────────────────
        unique_titles = self._deduplicate(all_titles)

        shortfall = 100 - len(unique_titles)
        if shortfall > 0:
            logger.info(f"[A3] {len(unique_titles)}개 확보. {shortfall}개 보충 생성...")
            extra = await self._fill_shortfall(strategies, shortfall, set(unique_titles))
            unique_titles.extend(extra)
            logger.info(f"[A3] 보충 후 총 {len(unique_titles)}개.")

        # ── 결과 저장 ─────────────────────────────────────────────────────────
        with open(self.temp_file, "w", encoding="utf-8") as f:
            f.write("\n".join(unique_titles[:100]))

        logger.success(
            f"[A3] {min(len(unique_titles), 100)}개 제목 생성 완료 → {self.temp_file.name}"
        )
        return unique_titles[:100]

    # ── 전략 수립 (Gemini CLI) ────────────────────────────────────────────────

    async def _fetch_strategies(self) -> List[Dict]:
        """Gemini CLI → JSON 5개 전략 파싱."""
        prompt = (
            "당신은 유튜브 SEO 전략가입니다.\n"
            "아래 레퍼런스 제목들을 분석하여, 조회수를 극대화할 수 있는\n"
            "핵심 키워드 조합 전략 5가지를 수립하세요.\n\n"
            "레퍼런스 제목 목록:\n"
            + "\n".join(f"- {t}" for t in self.references)
            + "\n\n"
            "각 전략은 다음 4가지 변형 축을 반드시 명시하세요:\n"
            "  1) name     : 전략 이름 (예: '충격적 주장형', '질문 호기심형')\n"
            "  2) keywords : 핵심 키워드 3개\n"
            "  3) tone     : 감성/톤 (예: '도발적/과장적', '학술적/정보성')\n"
            "  4) mutation : 제목 변형 방향 (예: '숫자+감탄사', '질문형+반전')\n\n"
            "반드시 아래 JSON 형식으로만 응답하세요 (마크다운·설명 없이 JSON만):\n"
            '{"strategies":['
            '{"id":1,"name":"전략명","keywords":["k1","k2","k3"],"tone":"톤","mutation":"변형방향"},'
            '...]}'
        )
        raw = await call_gemini_cli_async(prompt)
        return self._parse_strategies(raw)

    @staticmethod
    def _parse_strategies(raw: str) -> List[Dict]:
        block = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, re.DOTALL)
        if block:
            raw = block.group(1)
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            logger.warning(f"[A3] 전략 JSON 파싱 실패. 원문:\n{raw[:300]}")
            return []
        try:
            return json.loads(m.group()).get("strategies", [])
        except json.JSONDecodeError as e:
            logger.warning(f"[A3] 전략 JSON 파싱 오류: {e}")
            return []

    # ── 제목 생성 (재시도 포함) ───────────────────────────────────────────────

    async def _generate_with_retry(
        self, strategy: Dict, idx: int, total: int
    ) -> List[str]:
        """전략 1개에 대해 최대 _MAX_RETRY 회 재시도하여 목표치(_TARGET_PER_STRATEGY) 확보."""
        collected: List[str] = []
        seen: set = set()

        for attempt in range(1, _MAX_RETRY + 2):  # 1회 + 최대 2회 재시도
            need = _TARGET_PER_STRATEGY - len(collected)
            if need <= 0:
                break

            logger.info(
                f"[A3] 전략 {idx}/{total} '{strategy.get('name','')}' "
                f"→ {'재시도' if attempt > 1 else '생성'} ({attempt}회차, {need}개 필요)"
            )

            try:
                titles = await self._call_model(strategy, need)
            except Exception as e:
                logger.warning(f"[A3] 전략 {idx} {attempt}회차 오류: {e}")
                if attempt > _MAX_RETRY:
                    raise
                continue

            for t in titles:
                if t and t not in seen:
                    seen.add(t)
                    collected.append(t)
                if len(collected) >= _TARGET_PER_STRATEGY:
                    break

        return collected

    async def _call_model(self, strategy: Dict, count: int) -> List[str]:
        """선택된 모델(gemma / gemini)로 제목 생성 후 파싱."""
        if self.title_model == "gemma":
            raw = await call_gemma_async(
                self._build_title_prompt(strategy, count), timeout=200
            )
        else:
            raw = await call_gemini_cli_async(
                self._build_title_prompt(strategy, count), timeout=120
            )
        return self._parse_titles(raw, count)

    # ── 보충 생성 ─────────────────────────────────────────────────────────────

    async def _fill_shortfall(
        self, strategies: List[Dict], need: int, existing: set
    ) -> List[str]:
        """100개 미달 시 전략들을 순환하며 부족분 보충."""
        extra: List[str] = []
        per_call = max(need, 10)  # 한 번에 여유 있게 요청

        for strategy in strategies:
            if len(extra) >= need:
                break
            try:
                titles = await self._call_model(strategy, per_call)
                for t in titles:
                    if t and t not in existing and t not in extra:
                        extra.append(t)
                    if len(extra) >= need:
                        break
            except Exception as e:
                logger.warning(f"[A3] 보충 생성 오류: {e}")

        return extra[:need]

    # ── 프롬프트 빌더 ─────────────────────────────────────────────────────────

    @staticmethod
    def _build_title_prompt(strategy: Dict, count: int) -> str:
        """
        Gemma 자신의 제안(Multi-Dimensional Mutation + 구조화 출력)을
        반영한 고품질 프롬프트.
        """
        name     = strategy.get("name", "제목 생성")
        keywords = ", ".join(strategy.get("keywords", []))
        tone     = strategy.get("tone", "")
        mutation = strategy.get("mutation", "")

        return (
            "당신은 유튜브 제목 최적화 전문가입니다. "
            "지금부터 '제목 변형 기계(Title Mutation Engine)' 역할을 수행합니다.\n\n"
            f"## 전략\n"
            f"- 전략명: {name}\n"
            f"- 핵심 키워드: {keywords}\n"
            f"- 톤/감성: {tone}\n"
            f"- 변형 방향: {mutation}\n\n"
            "## 변형 원칙 (다차원 조합 필수)\n"
            "각 제목은 아래 4가지 요소를 독립적으로 변형하여 서로 다른 조합을 만드세요:\n"
            "  [주제 범위] 확장(중동 전체) 또는 축소(특정 국가)\n"
            "  [강조 키워드] 감성적 치환 (망하다→초토화, 문제→재앙)\n"
            "  [관점/시점] 보고서형 / 충격형 / 질문형 / 경고형 중 선택\n"
            "  [숫자·구조] '5가지', '충격!', '지금 당장', '절대 모르는' 등 조합\n\n"
            f"## 출력 규칙 (반드시 준수)\n"
            f"- 정확히 {count}개 제목 생성\n"
            "- 각 제목은 쉼표(,)로 구분된 한 줄 리스트로만 출력\n"
            "- 형식: [제목1], [제목2], [제목3], ...\n"
            "- 제목 길이: 15~40자\n"
            "- 서론·설명·번호·마무리 문장 절대 금지\n\n"
            "지금 바로 시작하세요:"
        )

    # ── 출력 파싱 ─────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_titles(raw: str, expected: int) -> List[str]:
        """
        '[제목1], [제목2], ...' 형식 우선 파싱.
        실패 시 줄 단위 fallback.
        """
        titles: List[str] = []

        # 1차: [제목] 형식 추출
        bracket_hits = re.findall(r"\[([^\[\]]{5,}?)\]", raw)
        for t in bracket_hits:
            t = t.strip()
            if t:
                titles.append(t)

        # 2차: 괄호 없이 쉼표 구분인 경우
        if not titles:
            for part in raw.split(","):
                t = re.sub(r"^\s*\d+[\.\)]\s*", "", part).strip()
                if t and len(t) >= 8:
                    titles.append(t)

        # 3차: 줄 단위 fallback
        if not titles:
            for line in raw.splitlines():
                line = re.sub(r"^\s*\d+[\.\)]\s*", "", line).strip()
                if line and len(line) >= 8:
                    titles.append(line)

        return titles[:expected]

    @staticmethod
    def _deduplicate(titles: List[str]) -> List[str]:
        seen, out = set(), []
        for t in titles:
            t = t.strip()
            if t and t not in seen:
                seen.add(t)
                out.append(t)
        return out


# ─────────────────────────────────────────────────────────────────────────────
# 2단계: 시크릿 모드 본격 탐색 (Validation)
# ─────────────────────────────────────────────────────────────────────────────

class TitleVerifier(BaseScraper):
    """
    2단계: 생성된 제목 후보들을 유튜브 검색으로 검증.
    - 배치(15개) 단위 검색
    - AI 라벨 확인 및 점수 산정
    - 실시간 진행률 보고
    """
    def __init__(self, titles: List[str], user_data_dir: str = None, headless: bool = True):
        super().__init__(user_data_dir=None, headless=headless)
        self.titles = titles
        self.selected_count = 0

    async def run(self):
        total = len(self.titles)
        logger.info(f"Starting verification for {total} titles in batches of 15...")

        await self.start()

        batches = [self.titles[i:i + 15] for i in range(0, total, 15)]

        final_results = []
        current_idx = 0

        for batch_idx, batch in enumerate(batches):
            logger.info(f"Processing Batch {batch_idx + 1}/{len(batches)}...")

            for title in batch:
                current_idx += 1
                await asyncio.sleep(random.uniform(2, 5))

                score = await self._verify_title(title)
                if score >= 3:
                    self.selected_count += 1

                logger.info(f"[PROGRESS] {current_idx}/{total} (Selected: {self.selected_count})")

                if score > 0:
                    result = {"title": title, "score": score}
                    final_results.append(result)
                    self._save_to_db(result)

                if self.selected_count >= 10:
                    logger.info("Found sufficient high-score titles. Short-circuiting.")
                    break
            else:
                continue
            break

        await self.stop()
        logger.success(f"Verification finished. {self.selected_count} high-score titles found.")

    async def _verify_title(self, title: str) -> int:
        page = await self.get_page()
        try:
            search_url = (
                f"https://www.youtube.com/results?search_query={quote(title)}"
                "&sp=CAASBBABGAE%253D"
            )
            await self.safe_goto(page, search_url)
            content   = await page.content()
            ai_count  = content.count("변경되었거나 합성된 콘텐츠")
            return min(ai_count, 5)
        except Exception as e:
            logger.error(f"Error verifying '{title}': {e}")
            return 0
        finally:
            await page.close()

    def _save_to_db(self, data: Dict):
        db.execute_query(
            "INSERT INTO title_suggestions (suggested_title, score) VALUES (?, ?)",
            (data["title"], data["score"]),
        )


# 하위 호환성
class FindTitle(TitleVerifier):
    def __init__(self, original_title: str, **kwargs):
        super().__init__([original_title], **kwargs)
