/**
 * V5.0 파이프라인 통합 검증 테스트 (과제 34)
 *
 * 실행: node n8n_workflow/tests/test_v5_pipeline.js
 *
 * 검증 항목:
 *   1. Node 3: 4레이어 JSON Schema 유효성 (bg_style, character_style 등)
 *   2. Node 4: silhouette 프롬프트 강제 주입 + API 라우팅 메타 부여
 *   3. Node 7: source_api/solid_color 아이템 ComfyUI 스킵 분기
 *   4. Node 10: Z-index 상수 + 4레이어 메타 주입 + solid_color CSS
 *   5. pipeline_chapter.json: V5.0 노드 존재 + 연결 정합성
 *   6. template.html: V5.0 키워드 존재 확인
 */

const fs = require("fs");
const path = require("path");

// ──────────────────────────────────────────────
// 유틸리티
// ──────────────────────────────────────────────
let passed = 0;
let failed = 0;

function assert(condition, label) {
  if (condition) {
    console.log(`  ✅ ${label}`);
    passed++;
  } else {
    console.error(`  ❌ ${label}`);
    failed++;
  }
}

function section(title) {
  console.log(`\n━━━ ${title} ━━━`);
}

// ──────────────────────────────────────────────
// [1] Node 3: 4레이어 JSON Schema 검증
// ──────────────────────────────────────────────
section("1. Node 3 — 4레이어 JSON Schema");

const node3Path = path.resolve(__dirname, "..", "nodes", "node3_director_prompt.js");
const node3Src = fs.readFileSync(node3Path, "utf-8");

assert(node3Src.includes("MULTI_FORMAT_LAYER_RULE"), "MULTI_FORMAT_LAYER_RULE 상수 존재");
assert(node3Src.includes("SEARCH_QUERY_RULE"), "SEARCH_QUERY_RULE 상수 존재");
assert(node3Src.includes('"bg_style"'), "OUTPUT_SCHEMA에 bg_style 필드 존재");
assert(node3Src.includes('"character_style"'), "OUTPUT_SCHEMA에 character_style 필드 존재");
assert(node3Src.includes('"foreground_style"'), "OUTPUT_SCHEMA에 foreground_style 필드 존재");
assert(node3Src.includes('"overlay_focus"'), "OUTPUT_SCHEMA에 overlay_focus 필드 존재");
assert(node3Src.includes('"search_query"'), "OUTPUT_SCHEMA에 search_query 필드 존재");

// validatePlan에 4레이어 검증 로직 확인
assert(node3Src.includes('validBg.includes(s.bg_style)'), "validatePlan: bg_style enum 검증");
assert(node3Src.includes('validChar.includes(s.character_style)'), "validatePlan: character_style enum 검증");
assert(node3Src.includes('validFg.includes(s.foreground_style)'), "validatePlan: foreground_style enum 검증");
assert(node3Src.includes('validOv.includes(s.overlay_focus)'), "validatePlan: overlay_focus enum 검증");
assert(node3Src.includes('search_query 누락'), "validatePlan: search_query 필수 체크 (실사/B-Roll)");
assert(node3Src.includes('overlay_focus=data_viz'), "validatePlan: data_viz → data_layer 연동 검증");

// buildPrompt에 룰 주입 확인
assert(node3Src.includes("MULTI_FORMAT_LAYER_RULE,"), "buildPrompt에 MULTI_FORMAT_LAYER_RULE 주입");
assert(node3Src.includes("SEARCH_QUERY_RULE,"), "buildPrompt에 SEARCH_QUERY_RULE 주입");

// ──────────────────────────────────────────────
// [2] Node 4: silhouette + API 라우팅
// ──────────────────────────────────────────────
section("2. Node 4 — Silhouette + API 라우팅");

const node4Path = path.resolve(__dirname, "..", "nodes", "node4_asset_prompt.js");
const node4Src = fs.readFileSync(node4Path, "utf-8");

assert(node4Src.includes("pure black solid silhouette"), "silhouette 프롬프트 강제 주입 문자열");
assert(node4Src.includes('character_style === "silhouette"'), "character_style silhouette 분기 조건");
assert(node4Src.includes("source_api"), "source_api 필드 출력");
assert(node4Src.includes('"pexels"'), "Pexels API 라우팅 값");
assert(node4Src.includes('"pixabay"'), "Pixabay API 라우팅 값");
assert(node4Src.includes('bg_style === "solid_color"'), "solid_color 배경 스킵 분기");
assert(node4Src.includes("solid_color_skip"), "solid_color search_log 카테고리");
assert(node4Src.includes("skip_comfyui: true"), "API/solid_color 아이템에 skip_comfyui 설정");

// ──────────────────────────────────────────────
// [3] Node 7: source_api/solid_color 스킵 분기
// ──────────────────────────────────────────────
section("3. Node 7 — API/solid_color 스킵 분기");

const node7Path = path.resolve(__dirname, "..", "nodes", "node7_comfyui_payload.js");
const node7Src = fs.readFileSync(node7Path, "utf-8");

assert(node7Src.includes("item.source_api"), "source_api 필드 체크");
assert(node7Src.includes('item.bg_style === "solid_color"'), "solid_color 스킵 조건");
assert(node7Src.includes("item.skip_comfyui && (item.source_api"), "skip_comfyui + source_api 조합 분기");

// ──────────────────────────────────────────────
// [4] Node 10: Z-index + 4레이어 메타 주입
// ──────────────────────────────────────────────
section("4. Node 10 — Z-index + 4레이어 메타 통합");

const node10Path = path.resolve(__dirname, "..", "nodes", "node10_master_assembler.js");
const node10Src = fs.readFileSync(node10Path, "utf-8");

assert(node10Src.includes("Z_INDEX"), "Z_INDEX 상수 정의");
assert(node10Src.includes("BACKGROUND: 1"), "Z_INDEX.BACKGROUND 값");
assert(node10Src.includes("CHARACTER: 100"), "Z_INDEX.CHARACTER 값");
assert(node10Src.includes("FOREGROUND: 200"), "Z_INDEX.FOREGROUND 값");
assert(node10Src.includes("OVERLAY: 300"), "Z_INDEX.OVERLAY 값");
assert(node10Src.includes("sceneOut.bg_style"), "씬 데이터에 bg_style 주입");
assert(node10Src.includes("sceneOut.character_style"), "씬 데이터에 character_style 주입");
assert(node10Src.includes("sceneOut.solid_color_css"), "solid_color CSS 할당");
assert(node10Src.includes("sceneOut.source_api"), "source_api 경로 맵핑");
assert(node10Src.includes("z_index_map"), "z_index_map 주입");

// ──────────────────────────────────────────────
// [5] pipeline_chapter.json: V5.0 노드 + 연결 검증
// ──────────────────────────────────────────────
section("5. pipeline_chapter.json — V5.0 노드/연결 정합성");

const pipelinePath = path.resolve(__dirname, "..", "pipeline_chapter.json");
const pipeline = JSON.parse(fs.readFileSync(pipelinePath, "utf-8"));
const nodes = pipeline.nodes;
const connections = pipeline.connections;

const checks = [
  { test: "IF — V5 API Route 노드 존재", fn: () => nodes.some(n => n.name === "IF — V5 API Route") },
  { test: "Node V5 — API Fetch & Result Handler 노드 존재", fn: () => nodes.some(n => n.name === "Node V5 — API Fetch & Result Handler") },
  { test: "IF — V5 API Route 연결 존재", fn: () => Object.keys(connections).includes("IF — V5 API Route") },
  { test: "Node V5 — API Fetch 연결 존재", fn: () => Object.keys(connections).includes("Node V5 — API Fetch & Result Handler") },
  { test: "IF — Cache Hit Skip 연결 존재", fn: () => Object.keys(connections).includes("IF — Cache Hit Skip") },
];

checks.forEach(c => assert(c.fn(), c.test));

const cacheConn = connections["IF — Cache Hit Skip"];
if (cacheConn) {
  const trueTarget = cacheConn.main[0][0].node;
  assert(trueTarget === "IF — V5 API Route", `Cache Hit true → IF — V5 API Route (실제: ${trueTarget})`);
}

// API Result Handler → Merge 연결 확인
const resultConn = connections["Node V5 — API Fetch & Result Handler"];
if (resultConn) {
  const target = resultConn.main[0][0].node;
  assert(target === "Merge — Cache + Webhook", `API Fetch → Merge (실제: ${target})`);
}

// 환경변수 검증
const envReq = pipeline._vivid_meta.env_requirements;
assert(envReq.PEXELS_API_KEY !== undefined, "env: PEXELS_API_KEY 정의됨");
assert(envReq.PIXABAY_API_KEY !== undefined, "env: PIXABAY_API_KEY 정의됨");

// 버전 검증
assert(pipeline._vivid_meta.version === "5.0.0", "워크플로우 버전: 5.0.0");

// ──────────────────────────────────────────────
// [6] template.html: V5.0 키워드 존재 확인
// ──────────────────────────────────────────────
section("6. template.html — V5.0 렌더링 엔진 키워드");

const templatePath = path.resolve(__dirname, "..", "..", "shared_assets", "template.html");
const templateSrc = fs.readFileSync(templatePath, "utf-8");

assert(templateSrc.includes("b_roll_video"), "template: b_roll_video 분기 키워드");
assert(templateSrc.includes("real_photo"), "template: real_photo 분기 키워드");
assert(templateSrc.includes("solid_color"), "template: solid_color 분기 키워드");
assert(templateSrc.includes("anti-dup"), "template: anti-dup CSS 클래스");
assert(templateSrc.includes("data-bg-type"), "template: data-bg-type 데이터 속성");
assert(templateSrc.includes("initKenBurnsEffects"), "template: initKenBurnsEffects 함수");
assert(templateSrc.includes("video.currentTime"), "template: B-Roll 비디오 동기화 로직");
assert(templateSrc.includes("hue-rotate"), "template: Anti-Duplication hue-rotate 필터");
assert(templateSrc.includes(".bg-layer video"), "template: B-Roll 비디오 CSS 스타일");

// ──────────────────────────────────────────────
// [7] hyperframes_pipeline.json: 버전 + 환경변수
// ──────────────────────────────────────────────
section("7. hyperframes_pipeline.json — Master Pipeline");

const masterPath = path.resolve(__dirname, "..", "hyperframes_pipeline.json");
const master = JSON.parse(fs.readFileSync(masterPath, "utf-8"));

assert(master._vivid_meta.version === "5.0.0", "Master Pipeline 버전: 5.0.0");
assert(master._vivid_meta.env_requirements.PEXELS_API_KEY !== undefined, "Master env: PEXELS_API_KEY");
assert(master._vivid_meta.env_requirements.PIXABAY_API_KEY !== undefined, "Master env: PIXABAY_API_KEY");

// ──────────────────────────────────────────────
// 결과 요약
// ──────────────────────────────────────────────
console.log("\n" + "═".repeat(50));
console.log(`V5.0 통합 검증 결과: ✅ ${passed} passed, ❌ ${failed} failed`);
console.log("═".repeat(50));

if (failed > 0) {
  process.exit(1);
}
