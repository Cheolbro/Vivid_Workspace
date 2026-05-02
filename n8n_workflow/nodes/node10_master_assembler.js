/**
 * Node 10 — Master Assembler (n8n Code Node, JavaScript)
 *
 * 목적: Node 3 plan + Node 9 assets(regions 스키마) + Node 2 lipsync
 *      + project_config branding + (옵션) 과제 6 편집 delta를 통합하여
 *      chapter_NN.html을 빌드.
 *
 * v4.5 보강:
 *   - assets.regions 스키마 (default 또는 split-region별 분리)
 *   - data_layer / layout / manga_effects 신규 필드 머지 (씬 0초 → 챕터 0초 변환)
 *   - emotion_timeline 폐기 (BN-1)
 *   - lazy 이미지 로드 마킹 (EF-5)
 *
 * v5.0 멀티 포맷 통합:
 *   - 4레이어 메타(bg_style, character_style, foreground_style, overlay_focus) 씬별 주입
 *   - bg_style: "solid_color" → CSS 컬러 코드 할당 (bg.solid_color_css)
 *   - source_api 에셋 경로 맵핑 (pexels MP4 / pixabay JPG/PNG)
 *   - data_layer를 HTML 스크립트 태그 주입 가능한 JSON으로 파싱
 *   - 4레이어 Z-index 통일성 확립
 *
 * 입력 (n8n items[].json — 각 챕터 1 아이템):
 *   - chapter_id: string  (예: "chapter_01")
 *   - chapter_index: number
 *   - plan_path: string         (project/plan/<chapter_id>_plan.json)
 *   - asset_path?: string       (Node 9 산출 JSON 경로. 없으면 inline asset_data 사용)
 *   - asset_data?: object       (Node 9 산출이 아이템에 직접 들어있을 때)
 *   - lipsync_path: string      (project/lipsync/<chapter_id>_lipsync.json)
 *   - edits_path?: string       (project/edits/<chapter_id>_edits.json — 선택)
 *
 * 워크플로우 전역 (Node 1):
 *   - $('Load Files').first().json.video_id
 *   - $('Load Files').first().json.project_root  (예: c:/Youtube/.../project)
 *   - $('Load Files').first().json.fps           (기본 30)
 *
 * 시간 좌표 변환표 (CL-4):
 *   | 필드                              | 입력 단위 | Node 10 변환     |
 *   | scene.start_time/end_time         | 챕터 0초  | 그대로            |
 *   | scene.lipsync[].start/end         | 챕터 0초  | 그대로            |
 *   | scene.kinetic_typography.appear_time/duration | 챕터 0초 | 그대로 |
 *   | scene.data_layer.appear_time/duration         | 씬 0초   | + scene.start_time |
 *   | scene.layout.trigger_time/duration            | 씬 0초   | + scene.start_time |
 *   | scene.manga_effects[].start_time/duration     | 씬 0초   | + scene.start_time |
 *
 * 출력: [{ json: { chapter_html_path, scene_count, duration_sec, branding } }]
 *
 * 환경: 외부 npm 모듈 불필요 (Node.js 빌트인만).
 */

const fs = require("fs");
const path = require("path");

// ──────────────────────────────────────────────
// V5.0 4레이어 Z-index 통일성 (과제 31)
// Background < Midground(character) < Foreground < Overlay
// ──────────────────────────────────────────────

const Z_INDEX = {
  BACKGROUND: 1,
  CHARACTER: 100,
  FOREGROUND: 200,
  OVERLAY: 300,
};

// ──────────────────────────────────────────────
// Deterministic RNG (cyrb53 hash + mulberry32 PRNG)
// ──────────────────────────────────────────────

function cyrb53(str, seed = 0) {
  let h1 = 0xdeadbeef ^ seed,
    h2 = 0x41c6ce57 ^ seed;
  for (let i = 0; i < str.length; i++) {
    const ch = str.charCodeAt(i);
    h1 = Math.imul(h1 ^ ch, 2654435761);
    h2 = Math.imul(h2 ^ ch, 1597334677);
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507);
  h1 ^= Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507);
  h2 ^= Math.imul(h1 ^ (h1 >>> 13), 3266489909);
  return 4294967296 * (2097151 & h2) + (h1 >>> 0);
}

function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// ──────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────

function readJson(p) {
  const raw = fs.readFileSync(p, "utf-8");
  return JSON.parse(raw);
}

function writeJson(p, obj) {
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, JSON.stringify(obj, null, 2), "utf-8");
}

function clamp(v, lo, hi) {
  return Math.max(lo, Math.min(hi, v));
}

function round2(v) {
  return Math.round(v * 100) / 100;
}

/** project_config.json의 randomization_rules 그대로 영상별 브랜딩 산출 */
function deriveBranding(config, videoId) {
  const existing = config.per_video_overrides && config.per_video_overrides[videoId];
  if (existing && !videoId.startsWith("_")) {
    return { branding: existing, configChanged: false };
  }

  const seed = cyrb53(videoId, 0xa55a) >>> 0;
  const rng = mulberry32(seed & 0xffffffff);
  const b = config.baseline;
  const wm = b.watermark;
  const acc = b.accent_color_hsl;
  const vig = b.vignette;

  const u = (lo, hi) => lo + rng() * (hi - lo);

  const watermark_x = clamp(
    Math.round(wm.position_x_baseline_px + u(-wm.position_jitter_px, wm.position_jitter_px)),
    10,
    60
  );
  const watermark_y = clamp(
    Math.round(wm.position_y_baseline_px + u(-wm.position_jitter_px, wm.position_jitter_px)),
    10,
    60
  );
  const watermark_opacity = round2(u(wm.opacity_min, wm.opacity_max));
  const accent_hue =
    ((Math.round(acc.hue_baseline + u(-acc.hue_jitter_deg, acc.hue_jitter_deg)) % 360) + 360) % 360;
  const accent_sat = clamp(
    Math.round(
      acc.saturation_baseline_pct + u(-acc.saturation_jitter_pct, acc.saturation_jitter_pct)
    ),
    0,
    100
  );
  const vignette_alpha = round2(u(vig.alpha_min, vig.alpha_max));

  // 과제 25: 프레임 지문 분산 값 생성
  const ffp = b.frame_fp || {};
  const frame_fp_micro_drift_intensity = round2(u(0.3, ffp.micro_drift_intensity || 0.5));
  const chromaMax = ffp.chroma_offset_max || 0.3;
  const frame_fp_chroma_r_offset = round2(u(-chromaMax, chromaMax));
  const frame_fp_chroma_b_offset = round2(u(-chromaMax, chromaMax));
  const bgRange = ffp.bg_offset_range || 1.5;
  const frame_fp_bg_offset_x = round2(50 + u(-bgRange, bgRange));
  const frame_fp_bg_offset_y = round2(50 + u(-bgRange, bgRange));
  const frame_fp_luminance_opacity =
    Math.round(u(0.01, ffp.luminance_opacity_max || 0.04) * 1000) / 1000;

  const branding = {
    generated_at: new Date().toISOString(),
    video_id: videoId,
    source_baseline_version: config.$schema_version || "1.0.0",
    watermark_x,
    watermark_y,
    watermark_opacity,
    accent_hue,
    accent_sat,
    vignette_alpha,
    frame_fp_micro_drift_intensity,
    frame_fp_chroma_r_offset,
    frame_fp_chroma_b_offset,
    frame_fp_bg_offset_x,
    frame_fp_bg_offset_y,
    frame_fp_luminance_opacity,
  };

  config.per_video_overrides = config.per_video_overrides || {};
  config.per_video_overrides[videoId] = branding;

  return { branding, configChanged: true };
}

/** Deep merge for delta (delta가 우선) */
function deepMerge(base, delta) {
  if (Array.isArray(delta)) return delta.slice();
  if (delta && typeof delta === "object" && !Array.isArray(delta)) {
    const out = { ...(base || {}) };
    for (const k of Object.keys(delta)) {
      out[k] = deepMerge(out[k], delta[k]);
    }
    return out;
  }
  return delta;
}

// ──────────────────────────────────────────────
// v4.5 helpers
// ──────────────────────────────────────────────

/** 씬 내부 0초 기준 시간 → 챕터 내부 0초 기준으로 오프셋 (CL-4) */
function shiftSceneTime(value, sceneStart) {
  if (typeof value !== "number" || !isFinite(value)) return value;
  return round2(value + sceneStart);
}

/** Node 9 regions 스키마 → assets 객체 정규화 (default 폴백 + split-region 보존) */
function normalizeRegions(sceneAssetsForId, planScene) {
  const regionsIn = (sceneAssetsForId && sceneAssetsForId.regions) || null;

  // 폴백: regions 키가 없으면 평면 스키마(bg/characters/props/foreground)로 간주하고 default region 1개 구성
  if (!regionsIn) {
    const defaultRegion = {
      bg: sceneAssetsForId.bg || null,
      characters: sceneAssetsForId.characters || [],
      props: sceneAssetsForId.props || [],
    };
    if (sceneAssetsForId.foreground && sceneAssetsForId.foreground.path) {
      defaultRegion.foreground = sceneAssetsForId.foreground;
    }
    return { default: defaultRegion };
  }

  // regions 키 존재 시: 각 region에 plan의 character position/z_index 매칭
  const planCharsById = {};
  for (const pc of planScene.characters || []) {
    if (pc.scene_asset_id) planCharsById[pc.scene_asset_id] = pc;
  }

  const out = {};
  for (const regionId of Object.keys(regionsIn)) {
    const r = regionsIn[regionId] || {};
    const region = {};
    if (r.bg) region.bg = r.bg;
    region.characters = (r.characters || []).map((ac) => {
      const pc = planCharsById[ac.scene_asset_id] || {};
      return {
        scene_asset_id: ac.scene_asset_id,
        path: ac.path,
        position: ac.position || pc.position || "center",
        z_index: ac.z_index || pc.z_index || 100,
        loading_strategy: "lazy",
      };
    });
    region.props = (r.props || []).map((p) => ({
      path: p.path,
      z_index: p.z_index || 50,
      loading_strategy: "lazy",
    }));
    if (r.foreground && r.foreground.path) {
      region.foreground = {
        path: r.foreground.path,
        zoom_rate: r.foreground.zoom_rate || 1.25,
        loading_strategy: "lazy",
      };
    }
    out[regionId] = region;
  }

  return out;
}

/** lazy 마킹: bg에 loading_strategy 부여 (regions[*].bg) */
function markBgLazy(regions) {
  for (const rid of Object.keys(regions)) {
    const r = regions[rid];
    if (r && r.bg && r.bg !== "__DUMMY_BLACK__") {
      // bg를 객체로 승격 (path + loading_strategy)
      if (typeof r.bg === "string") {
        r.bg = { path: r.bg, loading_strategy: "lazy" };
      }
    }
  }
}

/** v4.5 신규 필드(scene 0초 기준) → 챕터 0초로 일괄 변환 */
function convertV45TimeFields(planScene) {
  const sceneStart = planScene.start_time || 0;
  const out = {};

  // data_layer (단일 객체 또는 null)
  if (planScene.data_layer && typeof planScene.data_layer === "object") {
    const dl = { ...planScene.data_layer };
    if ("appear_time" in dl) dl.appear_time = shiftSceneTime(dl.appear_time, sceneStart);
    if ("duration" in dl) dl.duration = dl.duration; // duration은 길이라 그대로
    out.data_layer = dl;
  }

  // layout (단일 객체 또는 null) — type / regions[] / trigger_time / duration
  if (planScene.layout && typeof planScene.layout === "object") {
    const lay = { ...planScene.layout };
    if ("trigger_time" in lay) lay.trigger_time = shiftSceneTime(lay.trigger_time, sceneStart);
    out.layout = lay;
  }

  // manga_effects (배열)
  if (Array.isArray(planScene.manga_effects)) {
    out.manga_effects = planScene.manga_effects.map((me) => ({
      ...me,
      start_time: shiftSceneTime(me.start_time, sceneStart),
    }));
  }

  return out;
}

/** {{INJECTED_JSON}} 또는 {{ INJECTED_JSON }} 한 번 정확히 치환 */
function injectIntoTemplate(templateHtml, dataObj) {
  const re = /\{\{\s*INJECTED_JSON\s*\}\}/g;
  const matches = templateHtml.match(re) || [];
  if (matches.length === 0) {
    throw new Error(
      "[Node 10] template.html 내 {{INJECTED_JSON}} 플레이스홀더를 찾을 수 없습니다."
    );
  }
  if (matches.length > 1) {
    throw new Error(
      `[Node 10] template.html 내 {{INJECTED_JSON}} 플레이스홀더가 ${matches.length}회 등장합니다 (정확히 1회여야 함).`
    );
  }
  const payload = JSON.stringify(dataObj);
  return templateHtml.replace(re, () => payload);
}

// ──────────────────────────────────────────────
// Main
// ──────────────────────────────────────────────

const items = $input.all();
if (!items || items.length === 0) {
  throw new Error("[Node 10] 입력 아이템이 없습니다.");
}

// 워크플로우 전역
const node1 = $("Load Files").first().json;
const VIDEO_ID = node1.video_id;
const PROJECT_ROOT = node1.project_root;
let FPS = node1.fps || 30; // 과제 23: config baseline에서 강제 오버라이드 (아래 config 로드 후)

if (!VIDEO_ID) throw new Error("[Node 10] video_id가 워크플로우 전역에 없습니다.");
if (!PROJECT_ROOT) throw new Error("[Node 10] project_root가 워크플로우 전역에 없습니다.");

// project_config.json 로드 (브랜딩 산출용) — 1회만, 모든 챕터 공유
const configPath = path.join(PROJECT_ROOT, "..", "project_config.json");
const fallbackConfigPath = path.resolve(__dirname, "..", "..", "project_config.json");
let configFilePath = fs.existsSync(configPath) ? configPath : fallbackConfigPath;
if (!fs.existsSync(configFilePath)) {
  throw new Error(
    `[Node 10] project_config.json을 찾을 수 없습니다: ${configPath} / ${fallbackConfigPath}`
  );
}
const config = readJson(configFilePath);

// 과제 23: baseline.target_fps 강제 적용 (MO-6)
if (config.baseline && typeof config.baseline.target_fps === "number") {
  FPS = config.baseline.target_fps;
}

const { branding, configChanged } = deriveBranding(config, VIDEO_ID);
if (configChanged) {
  writeJson(configFilePath, config);
}

// template.html 로드 (1회만, 모든 챕터 공유)
const templatePath = path.resolve(__dirname, "..", "..", "shared_assets", "template.html");
if (!fs.existsSync(templatePath)) {
  throw new Error(`[Node 10] shared_assets/template.html을 찾을 수 없습니다: ${templatePath}`);
}
const TEMPLATE_HTML = fs.readFileSync(templatePath, "utf-8");

const compositionsDir = path.join(PROJECT_ROOT, "compositions");
fs.mkdirSync(compositionsDir, { recursive: true });

// 챕터별 처리
const results = [];

for (const item of items) {
  const j = item.json || {};
  const chapter_id = j.chapter_id;
  if (!chapter_id) {
    throw new Error("[Node 10] 입력 아이템에 chapter_id가 없습니다.");
  }

  // 입력 파일 로드
  if (!j.plan_path || !fs.existsSync(j.plan_path)) {
    throw new Error(`[Node 10][${chapter_id}] plan_path 누락 또는 파일 없음: ${j.plan_path}`);
  }
  if (!j.lipsync_path || !fs.existsSync(j.lipsync_path)) {
    throw new Error(`[Node 10][${chapter_id}] lipsync_path 누락 또는 파일 없음: ${j.lipsync_path}`);
  }

  const plan = readJson(j.plan_path);
  const lipsync = readJson(j.lipsync_path);

  let assetData;
  if (j.asset_data) {
    assetData = j.asset_data;
  } else if (j.asset_path && fs.existsSync(j.asset_path)) {
    assetData = readJson(j.asset_path);
  } else {
    throw new Error(`[Node 10][${chapter_id}] asset_data/asset_path 모두 누락`);
  }
  const sceneAssets = assetData.scenes || {};

  let edits = null;
  if (j.edits_path && fs.existsSync(j.edits_path)) {
    edits = readJson(j.edits_path);
  }

  // (2) 씬 단위 머지
  const planScenes = Array.isArray(plan.scenes) ? plan.scenes : [];
  const lipsyncCues = Array.isArray(lipsync) ? lipsync : lipsync.cues || [];

  const scenesOut = planScenes
    .slice()
    .sort((a, b) => (a.start_time || 0) - (b.start_time || 0))
    .map((s) => {
      const sid = s.scene_id;
      const a = sceneAssets[sid] || {};

      // assets.regions 정규화 (default 폴백 또는 split-region 분리)
      const regions = normalizeRegions(a, s);

      // 빈 default region에 더미 배경 (파이프라인 완주 보장)
      if (regions.default && !regions.default.bg) {
        regions.default.bg = "__DUMMY_BLACK__";
      } else {
        for (const rid of Object.keys(regions)) {
          if (!regions[rid].bg) regions[rid].bg = "__DUMMY_BLACK__";
        }
      }

      // bg lazy 마킹 (bg를 path/loading_strategy 객체로 승격)
      markBgLazy(regions);

      // lipsync 필터 (cue.start ∈ [start_time, end_time)) — 챕터 0초 기준 그대로
      const sceneLipsync = lipsyncCues.filter(
        (cue) => cue.start >= s.start_time && cue.start < s.end_time
      );

      // v4.5 시간 필드 변환 (씬 0초 → 챕터 0초)
      const v45 = convertV45TimeFields(s);

      const sceneOut = {
        scene_id: sid,
        start_time: s.start_time,
        end_time: s.end_time,
        assets: { regions: regions },
        camera_choreography: s.camera_choreography || {
          x: 0,
          y: 0,
          scale: 1.0,
          ease: "power2.inOut",
        },
        kinetic_typography: s.kinetic_typography || null,
        lipsync: sceneLipsync,
        vfx_active: !!s.vfx_active,
        ambient_effect: s.ambient_effect || { type: "none" },
        scene_transition: s.scene_transition || "cut",
        structure_logic: s.structure_logic,
        scene_context: s.scene_context,
      };

      // v4.5 신규 필드 — 존재 시에만 머지
      if (v45.data_layer) sceneOut.data_layer = v45.data_layer;
      if (v45.layout) sceneOut.layout = v45.layout;
      if (v45.manga_effects) sceneOut.manga_effects = v45.manga_effects;

      // ── V5.0 멀티 포맷 4레이어 메타 주입 (과제 31) ──
      sceneOut.bg_style = s.bg_style || "illustration";
      sceneOut.character_style = s.character_style || "webtoon";
      sceneOut.foreground_style = s.foreground_style || "none";
      sceneOut.overlay_focus = s.overlay_focus || "none";
      sceneOut.search_query = s.search_query || null;
      sceneOut.z_index_map = Z_INDEX;

      // V5.0: bg_style · source_api에 따른 배경 데이터 보강
      if (sceneOut.bg_style === "solid_color") {
        // CSS 컬러 코드 할당 (plan에 지정된 것이 없으면 기본 진한 회색)
        sceneOut.solid_color_css = s.solid_color_css || "#1A1A2E";
      }
      if (a.source_api) {
        // Pexels/Pixabay 에셋 경로 (Node 33이 다운로드한 파일)
        sceneOut.api_asset_path = a.api_asset_path || null;
        sceneOut.source_api = a.source_api;
      }

      // emotion_timeline은 BN-1로 폐기 — plan에 들어와도 버린다
      // (의도적 미반영. 향후 LLM 출력에 잔존하더라도 무시.)

      return sceneOut;
    });

  // (3) edits delta 머지
  let scenesFinal = scenesOut;
  if (edits && edits.scenes && typeof edits.scenes === "object") {
    scenesFinal = scenesOut.map((sc) => {
      const d = edits.scenes[sc.scene_id];
      return d ? deepMerge(sc, d) : sc;
    });
  }

  // (5) 최종 DATA
  const totalDuration = scenesFinal.length > 0 ? scenesFinal[scenesFinal.length - 1].end_time : 0;

  const DATA = {
    meta: {
      video_id: VIDEO_ID,
      chapter_id: chapter_id,
      fps: FPS,
      duration: totalDuration,
      render_mode_default: false,
    },
    branding: {
      watermark_x: branding.watermark_x,
      watermark_y: branding.watermark_y,
      watermark_opacity: branding.watermark_opacity,
      vignette_alpha: branding.vignette_alpha,
      accent_hue: branding.accent_hue,
      accent_sat: branding.accent_sat,
      frame_fp: {
        micro_drift_intensity: branding.frame_fp_micro_drift_intensity,
        chroma_r_offset: branding.frame_fp_chroma_r_offset,
        chroma_b_offset: branding.frame_fp_chroma_b_offset,
        bg_offset_x: branding.frame_fp_bg_offset_x,
        bg_offset_y: branding.frame_fp_bg_offset_y,
        luminance_opacity: branding.frame_fp_luminance_opacity,
      },
    },
    scenes: scenesFinal,
  };

  // (5-1) 과제 6 편집기 delta 주입 — template.html의 VIVID_SET_EDIT_DELTA()가 소비
  if (edits && edits.edit_delta && typeof edits.edit_delta === "object") {
    DATA.edit_delta = edits.edit_delta;
  }

  // (6) 템플릿 주입
  const html = injectIntoTemplate(TEMPLATE_HTML, DATA);

  // (7) 디스크 저장
  const outPath = path.join(compositionsDir, `${chapter_id}.html`);
  fs.writeFileSync(outPath, html, "utf-8");

  results.push({
    json: {
      chapter_id: chapter_id,
      chapter_html_path: outPath,
      scene_count: scenesFinal.length,
      duration_sec: totalDuration,
      branding: DATA.branding,
      had_edits: !!edits,
    },
  });
}

return results;
