/**
 * Node 3 — Run Analysts: 총괄 연출 기획 (Gemini CLI 호출)
 *
 * 목적: 챕터 대본 + SRT 타임코드 → 연출 기획 JSON (씬 단위 객체 배열) 산출.
 *      Gemini CLI에 전달할 프롬프트와 출력 스키마를 정의하고,
 *      v4.0 9개 필수 속성 + v4.5 5개 신규 결정권 + v5.0 4레이어 포맷 결정권을 강제한다.
 *
 * v4.5 신규 결정권 (5종):
 *   - data_layer  : 지도/차트 시각화 결정 (시간은 씬 0초 기준)
 *   - layout      : 화면 분할 컷 결정 (시간은 씬 0초 기준)
 *   - manga_effects: 만화 이펙트 배열 (시간은 씬 0초 기준)
 *   - emotion_timeline: BN-1로 폐기 — 출력 금지
 *   - pose         : 라이브러리 매칭 또는 "auto"
 *
 * v5.0 멀티 포맷 4레이어 결정권 (5 필드):
 *   - bg_style         : "illustration" | "real_photo" | "b_roll_video" | "solid_color"
 *   - character_style  : "webtoon" | "silhouette" | "hidden"
 *   - foreground_style : "none" | "cinematic_depth" | "physical_object"
 *   - overlay_focus    : "none" | "typography" | "data_viz"
 *   - search_query     : bg_style이 real_photo/b_roll_video일 때 Pexels/Pixabay 검색 키워드
 *
 * 시간 좌표:
 *   - scene.start_time / end_time : 챕터 0초 기준 (절대)
 *   - scene.kinetic_typography.appear_time / duration : 챕터 0초 기준
 *   - scene.data_layer / layout / manga_effects 시간값 : 씬 0초 기준 (Node 10이 변환)
 *
 * 입력 (n8n items[].json):
 *   - chapter_id: string
 *   - script_text: string (챕터 대본)
 *   - srt_path: string (챕터 0초 기준 재계산된 SRT)
 *   - chapter_duration_sec: number
 *   - structure_logic: "INTRO" | "BUMPER" | "CHAPTER" | "OUTRO"
 *   - pose_library_path: string (shared_assets/pose_library.json)
 *
 * 워크플로우 전역 (Node 1):
 *   - $('Load Files').first().json.video_id
 *   - $('Load Files').first().json.project_root
 *
 * 출력: [{ json: { chapter_id, plan_path } }]
 *      (실제 plan JSON은 project/plan/<chapter_id>_plan.json에 저장)
 *
 * 환경: gemini CLI 시스템 PATH 가용 + 외부 npm 모듈 불필요.
 */

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

// ──────────────────────────────────────────────
// 프롬프트 빌더
// ──────────────────────────────────────────────

const SYSTEM_DIRECTIVE = `당신은 정보성 유튜브 채널의 모션 코믹 영상 총괄 연출 감독입니다.
대본을 분석하여 씬마다 캐릭터 포즈, 카메라 워킹, 키네틱 타이포그래피, 데이터 시각화, 화면 분할,
만화 이펙트를 종합 기획합니다. 출력은 반드시 지정된 JSON 스키마만 따릅니다.`;

const SCENE_SEGMENTATION_RULE = `[씬 분할 절대 규칙]
- 절대 규칙(Hard Rule): 문장 단위. 마침표(.), 느낌표(!), 물음표(?)로 종결되는 문장 경계를 절대 침범 금지.
- 보조 가이드(Soft Rule): 씬 duration 8~15초 권장.
  * 한 문장이 8초 미만이면 다음 문장과 합쳐 12~15초로 구성
  * 한 문장이 15초 초과면 단독 씬 허용
  * 짧은 대화 묶음은 8~10초 / 정보 밀도 높은 문장은 12~15초
- 챕터 평균 3분 기준 씬 12~22개 권장 (8개 미만 단조로움 / 25개 초과 GPU 부하).
- scene.start_time / end_time은 챕터 내부 0초 기준.`;

const POSE_RULE = `[pose 라이브러리 매칭 규칙]
- pose_library.json을 검색하여 가장 유사한 pose_id 매칭, 없으면 "auto".
- 강제 비율 (챕터 단위):
  * static (앵커 데스크 정적): 70% (예: pose_anchor_neutral, explaining_open, thoughtful)
  * action (강조 액션): 20% (예: pose_pointing_data, emphasis_fist) — 챕터당 최대 5씬
  * auto (라이브러리 미매칭): 10%
- pose:"auto" + character_pose 자연어 묘사로 LLM 창의 80% 보존
- pose:"<pose_id>" + character_pose 보조 묘사로 시스템 통제 20%`;

const DATA_LAYER_RULE = `[데이터 시각화 절대 규칙]
- 지도, 차트, 그래프는 절대 ComfyUI(AI 이미지 생성)에 그리게 하지 마라.
- 시각화가 필요한 씬은 반드시 data_layer 필드로 출력.
- 시각화가 필요 없는 씬은 data_layer 출력 금지 (null 또는 미출력).
- 시간값(appear_time, duration)은 씬 내부 0초 기준.`;

const MANGA_EFFECTS_RULE = `[만화 이펙트 규칙]
- 사전 정의 10종: speed_lines_radial / speed_lines_horizontal / impact_flash /
  screen_shake_low / screen_shake_high / vignette_pulse / ink_splash /
  region_burst / sweat_drop / anger_vein
- 동시 발동은 5개 이내 권장 (성능). 개수 자체 제한은 없음.
- 시간값(start_time, duration)은 씬 내부 0초 기준.
- 라이브러리에 없는 이펙트는 effect:"custom" + description 자연어 묘사.`;

const LAYOUT_RULE = `[화면 분할 layout 규칙]
- 분할 종류: split_diagonal / split_vertical / split_horizontal /
  split_3regions / split_corner / split_focus_zoom
- regions[].region_id는 left/right/top/bottom/center/focus 등 자유 지정.
- Node 9가 region별 자산을 해당 region_id 키로 산출.
- layout이 필요 없는 일반 씬은 layout 필드 출력 금지 (자동으로 default region 1개 폴백).
- 시간값(trigger_time, duration)은 씬 내부 0초 기준.`;

const MULTI_FORMAT_LAYER_RULE = `[V5.0 멀티 포맷 4레이어 조합 규칙]
- 씬마다 아래 4가지 레이어 속성을 반드시 지정하여 시각적 다채로움을 확보할 것.
- bg_style: "illustration"(기본 AI) | "real_photo"(실사 사진) | "b_roll_video"(실사 영상) | "solid_color"(단색 배경)
- character_style: "webtoon"(일반 컷아웃) | "silhouette"(그림자 연출) | "hidden"(캐릭터 비노출)
- foreground_style: "none" | "cinematic_depth"(먼지/빛 번짐) | "physical_object"(물리적 전경 사물)
- overlay_focus: "none" | "typography"(키네틱 타이포 강조) | "data_viz"(차트/그래프)
- 대본 맥락에 따라 4요소를 창의적으로 조합 (예: 통계→data_viz+solid_color, 현장→b_roll_video+hidden, 2.5D→physical_object)
- 3~4씬 연속으로 완벽히 동일한 조합 금지.`;

const SEARCH_QUERY_RULE = `[API 검색 키워드 최적화 규칙]
- bg_style이 "b_roll_video" 또는 "real_photo"일 경우 search_query 필드에 영단어 키워드 1~2개 압축 출력.
- 추상적/복잡한 개념(예: 'economic crisis', 'health problem') 금지.
- 시각적으로 명확한 구체 명사·행동(예: 'money falling', 'worrying man', 'eating apple')으로 치환.
- bg_style이 "illustration" 또는 "solid_color"이면 search_query는 null.`;

const KINETIC_TYPOGRAPHY_RULE = `[키네틱 타이포그래피 정밀 타이밍 규칙]
- 10자 이내 단기 임팩트 명사구 1~2개만 추출.
- 무게감에 맞는 easing: bounce(무거움) / slide(날카로움) / fade / zoom 등.
- appear_time은 SRT의 해당 키워드 발화 시점과 일치 (챕터 0초 기준).
- appear_time + duration >= scene.end_time 이며 appear_time <= scene.end_time - 2.0
  (씬 종료 2초 전엔 완전 노출 + 씬 끝까지 화면 유지).`;

const EMOTION_TIMELINE_DEPRECATED = `[emotion_timeline 폐기 — BN-1]
- emotion_timeline 필드는 절대 출력 금지.
- 한 씬 내 표정 변화가 필요하면 씬 자체를 분리 (씬당 표정 1개).`;

const OUTPUT_SCHEMA = `[출력 JSON 스키마 — 정확히 이 형태로만 반환]
{
  "chapter_id": "<문자열, 입력값과 동일>",
  "scenes": [
    {
      "scene_id": "scene_NN",
      "start_time": <챕터 0초 기준 초>,
      "end_time": <챕터 0초 기준 초>,
      "structure_logic": "INTRO" | "BUMPER" | "CHAPTER" | "OUTRO",
      "scene_context": "<공간/분위기 묘사>",

      "bg_style": "illustration" | "real_photo" | "b_roll_video" | "solid_color",
      "character_style": "webtoon" | "silhouette" | "hidden",
      "foreground_style": "none" | "cinematic_depth" | "physical_object",
      "overlay_focus": "none" | "typography" | "data_viz",
      "search_query": null | "<구체적 영문 키워드 1~2개>",

      "character_pose": "<자연어 포즈 묘사 — pose:auto일 때 단독 영향, pose:<id>일 때 보조 묘사>",
      "pose": "auto" | "pose_<라이브러리 id>",
      "characters": [
        {
          "scene_asset_id": "character_01",
          "position": "left" | "center" | "right",
          "z_index": 100,
          "region_id": "default" | "<layout.regions[].region_id>"
        }
      ],

      "camera_choreography": { "x": 0, "y": 0, "scale": 1.0, "ease": "power2.inOut" },
      "kinetic_typography": {
        "text": "<10자 이내>",
        "easing": "bounce" | "slide" | "fade" | "zoom",
        "appear_time": <챕터 0초 기준>,
        "duration": <초>
      },
      "vfx_active": true | false,
      "ambient_effect": { "type": "rain"|"dust"|"light_rays"|"smoke"|"snow"|"none",
                          "intensity": "light"|"medium"|"heavy", "wind_angle": 0~45 },
      "scene_transition": "cut" | "fade_black" | "glitch" | "zoom_blur" | "slide_left",

      "data_layer": null | { "type": "map"|"chart", ...씬 0초 기준 시간 },
      "layout": null | { "type": "split_diagonal"|..., "regions": [...], "trigger_time": <씬 0초>, "duration": <초> },
      "manga_effects": [ { "effect": "...", "start_time": <씬 0초>, "duration": <초> } ]
    }
  ]
}

[금지 사항]
- emotion_timeline 필드 출력 금지 (BN-1 폐기).
- 씬 분할 절대 규칙(문장 경계) 위반 금지.
- pose 강제 비율(static 70 / action 20 / auto 10) 위반 금지.
- 지도/차트를 character_pose 또는 scene_context로 묘사하지 말 것 (data_layer 강제).
- JSON 외 다른 텍스트(설명, 마크다운 코드 펜스, 인사말) 출력 금지.`;

function buildPrompt(input) {
  const {
    chapter_id,
    script_text,
    srt_path,
    chapter_duration_sec,
    structure_logic,
    pose_library_path,
  } = input;

  // pose_library 인라인 주입 (LLM이 매칭 시 사용)
  let poseLibrarySnippet = "";
  if (pose_library_path && fs.existsSync(pose_library_path)) {
    const lib = JSON.parse(fs.readFileSync(pose_library_path, "utf-8"));
    poseLibrarySnippet = `\n[pose_library 가용 ID 목록]\n${JSON.stringify(lib, null, 2)}\n`;
  } else {
    poseLibrarySnippet = `\n[pose_library 미가용 — 모든 씬 pose:"auto" 강제]\n`;
  }

  // SRT 인라인 주입 (kinetic typography 타이밍 매칭용)
  let srtSnippet = "";
  if (srt_path && fs.existsSync(srt_path)) {
    srtSnippet = `\n[SRT 데이터 — 챕터 0초 기준 타임코드]\n${fs.readFileSync(srt_path, "utf-8")}\n`;
  }

  return [
    SYSTEM_DIRECTIVE,
    "",
    `[챕터 정보]`,
    `chapter_id: ${chapter_id}`,
    `chapter_duration_sec: ${chapter_duration_sec}`,
    `structure_logic: ${structure_logic}`,
    "",
    `[챕터 대본]`,
    script_text,
    srtSnippet,
    poseLibrarySnippet,
    "",
    SCENE_SEGMENTATION_RULE,
    "",
    POSE_RULE,
    "",
    DATA_LAYER_RULE,
    "",
    MANGA_EFFECTS_RULE,
    "",
    LAYOUT_RULE,
    "",
    MULTI_FORMAT_LAYER_RULE,
    "",
    SEARCH_QUERY_RULE,
    "",
    KINETIC_TYPOGRAPHY_RULE,
    "",
    EMOTION_TIMELINE_DEPRECATED,
    "",
    OUTPUT_SCHEMA,
  ].join("\n");
}

// ──────────────────────────────────────────────
// 출력 검증
// ──────────────────────────────────────────────

function validatePlan(plan, input) {
  const errors = [];
  if (!plan || typeof plan !== "object") errors.push("plan이 객체가 아님");
  if (plan.chapter_id !== input.chapter_id)
    errors.push(`chapter_id 불일치: ${plan.chapter_id} vs ${input.chapter_id}`);
  if (!Array.isArray(plan.scenes) || plan.scenes.length === 0)
    errors.push("scenes 배열 누락 또는 비어 있음");

  let staticCount = 0,
    actionCount = 0,
    autoCount = 0;
  const sceneCount = (plan.scenes || []).length;

  for (let i = 0; i < (plan.scenes || []).length; i++) {
    const s = plan.scenes[i];
    const tag = `scenes[${i}]`;

    if (typeof s.start_time !== "number") errors.push(`${tag}.start_time 누락`);
    if (typeof s.end_time !== "number") errors.push(`${tag}.end_time 누락`);
    if (s.start_time >= s.end_time) errors.push(`${tag}.start_time >= end_time`);

    // V5.0 4레이어 필드 검증
    const validBg = ["illustration", "real_photo", "b_roll_video", "solid_color"];
    if (!validBg.includes(s.bg_style)) errors.push(`${tag}.bg_style 형식 오류: ${s.bg_style}`);
    const validChar = ["webtoon", "silhouette", "hidden"];
    if (!validChar.includes(s.character_style)) errors.push(`${tag}.character_style 형식 오류: ${s.character_style}`);
    const validFg = ["none", "cinematic_depth", "physical_object"];
    if (!validFg.includes(s.foreground_style)) errors.push(`${tag}.foreground_style 형식 오류: ${s.foreground_style}`);
    const validOv = ["none", "typography", "data_viz"];
    if (!validOv.includes(s.overlay_focus)) errors.push(`${tag}.overlay_focus 형식 오류: ${s.overlay_focus}`);
    // search_query: 실사/B-Roll이면 필수, 아니면 null 허용
    if ((s.bg_style === "real_photo" || s.bg_style === "b_roll_video") && !s.search_query)
      errors.push(`${tag}.search_query 누락 (bg_style=${s.bg_style}이면 필수)`);
    // overlay_focus가 data_viz이면 data_layer 필수
    if (s.overlay_focus === "data_viz" && !s.data_layer)
      errors.push(`${tag}.overlay_focus=data_viz인데 data_layer 누락`);

    // emotion_timeline 폐기 — 출력 금지
    if ("emotion_timeline" in s) errors.push(`${tag}.emotion_timeline 출력 금지 (BN-1 폐기)`);

    // pose 카테고리 카운트
    if (s.pose === "auto") autoCount++;
    else if (typeof s.pose === "string" && s.pose.startsWith("pose_")) {
      if (
        s.pose.includes("_pointing_") ||
        s.pose.includes("_emphasis_") ||
        s.pose.includes("_doc_") ||
        s.pose.includes("_concerned_") ||
        s.pose.includes("_arms_crossed") ||
        s.pose.includes("_facepalm")
      ) {
        actionCount++;
      } else {
        staticCount++;
      }
    } else {
      errors.push(`${tag}.pose 형식 오류 (auto 또는 pose_<id>): ${s.pose}`);
    }

    // kinetic_typography 시간 제약
    if (s.kinetic_typography && typeof s.kinetic_typography === "object") {
      const kt = s.kinetic_typography;
      if (kt.appear_time + kt.duration < s.end_time - 0.01)
        errors.push(`${tag}.kinetic appear_time + duration < scene.end_time (씬 끝까지 노출 위반)`);
      if (kt.appear_time > s.end_time - 2.0)
        errors.push(`${tag}.kinetic appear_time > scene.end_time - 2.0 (2초 전 노출 위반)`);
    }

    // data_layer / layout / manga_effects 시간값 검증 (씬 0초 기준)
    const sceneDur = s.end_time - s.start_time;
    if (s.data_layer && typeof s.data_layer.appear_time === "number") {
      if (s.data_layer.appear_time < 0 || s.data_layer.appear_time > sceneDur)
        errors.push(`${tag}.data_layer.appear_time 씬 0초 기준 범위 벗어남`);
    }
    if (s.layout && typeof s.layout.trigger_time === "number") {
      if (s.layout.trigger_time < 0 || s.layout.trigger_time > sceneDur)
        errors.push(`${tag}.layout.trigger_time 씬 0초 기준 범위 벗어남`);
    }
    if (Array.isArray(s.manga_effects)) {
      for (const me of s.manga_effects) {
        if (me.start_time < 0 || me.start_time > sceneDur)
          errors.push(`${tag}.manga_effects start_time 씬 0초 기준 범위 벗어남`);
      }
    }
  }

  // pose 비율 검증 (sceneCount 5개 이상일 때만)
  if (sceneCount >= 5) {
    const staticRatio = staticCount / sceneCount;
    const actionRatio = actionCount / sceneCount;
    if (actionRatio > 0.35)
      errors.push(`pose action 비율 ${(actionRatio * 100).toFixed(0)}% > 35% (권장 20%)`);
    if (actionCount > 5) errors.push(`pose action 수 ${actionCount} > 챕터당 최대 5씬 위반`);
    if (staticRatio < 0.5)
      errors.push(`pose static 비율 ${(staticRatio * 100).toFixed(0)}% < 50% (권장 70%)`);
  }

  return errors;
}

// ──────────────────────────────────────────────
// Gemini CLI 호출
// ──────────────────────────────────────────────

function callGeminiCli(prompt, retries = 3) {
  for (let attempt = 1; attempt <= retries; attempt++) {
    const result = spawnSync("gemini", ["--prompt", prompt, "--format", "json"], {
      encoding: "utf-8",
      maxBuffer: 50 * 1024 * 1024,
      timeout: 180000,
    });
    if (result.status === 0 && result.stdout) {
      try {
        return JSON.parse(
          result.stdout
            .trim()
            .replace(/^```json\s*/, "")
            .replace(/```$/, "")
        );
      } catch (e) {
        if (attempt === retries)
          throw new Error(`[Node 3] JSON 파싱 실패 (${retries}회 후): ${e.message}`);
      }
    } else if (attempt === retries) {
      throw new Error(
        `[Node 3] Gemini CLI 호출 실패 (${retries}회 후): ${result.stderr || "unknown"}`
      );
    }
  }
}

// ──────────────────────────────────────────────
// Main
// ──────────────────────────────────────────────

const items = $input.all();
if (!items || items.length === 0) throw new Error("[Node 3] 입력 아이템 없음");

const node1 = $("Load Files").first().json;
const PROJECT_ROOT = node1.project_root;
if (!PROJECT_ROOT) throw new Error("[Node 3] project_root 누락");

const planDir = path.join(PROJECT_ROOT, "plan");
fs.mkdirSync(planDir, { recursive: true });

const results = [];
for (const item of items) {
  const j = item.json || {};
  const input = {
    chapter_id: j.chapter_id,
    script_text: j.script_text,
    srt_path: j.srt_path,
    chapter_duration_sec: j.chapter_duration_sec,
    structure_logic: j.structure_logic || "CHAPTER",
    pose_library_path:
      j.pose_library_path ||
      path.resolve(__dirname, "..", "..", "shared_assets", "pose_library.json"),
  };

  if (!input.chapter_id) throw new Error("[Node 3] chapter_id 누락");
  if (!input.script_text) throw new Error(`[Node 3][${input.chapter_id}] script_text 누락`);

  // 캐시 재사용 (Stop & Resume)
  const planPath = path.join(planDir, `${input.chapter_id}_plan.json`);
  if (fs.existsSync(planPath)) {
    results.push({ json: { chapter_id: input.chapter_id, plan_path: planPath, cached: true } });
    continue;
  }

  // Gemini 호출
  const prompt = buildPrompt(input);
  const plan = callGeminiCli(prompt);

  // 검증
  const errors = validatePlan(plan, input);
  if (errors.length > 0) {
    throw new Error(`[Node 3][${input.chapter_id}] 출력 검증 실패:\n  - ${errors.join("\n  - ")}`);
  }

  // 저장
  fs.writeFileSync(planPath, JSON.stringify(plan, null, 2), "utf-8");
  results.push({
    json: {
      chapter_id: input.chapter_id,
      plan_path: planPath,
      scene_count: plan.scenes.length,
      cached: false,
    },
  });
}

return results;
