/**
 * Node 9 — Asset Packager (n8n Code Node, JavaScript)
 *
 * 목적: ComfyUI 출력 PNG를 WebP lossless로 변환, 규격화된 파일명으로 rename,
 *       챕터/씬 계층 폴더로 정리, 에셋 경로 메타데이터 생성.
 *
 * 과제 24 (BN-2): WebP lossless 변환 — 알파 채널 무손실 보존, 파일 크기 50% 감소.
 *   - cwebp CLI 사용 (sharp는 optional, 미설치 시 cwebp 폴백)
 *   - 변환 실패 시 원본 PNG 유지 (안전 폴백)
 *   - 디스크 압박 시 lossy 95% 전환 가능 (project_config.json image_format 참조)
 *
 * 입력 (n8n items[].json — Node 8 Webhook 또는 캐시 히트 출력):
 *   - chapter_id, scene_id, asset_type, scene_asset_id, region_id
 *   - output_path: ComfyUI 산출 PNG 절대 경로 (또는 캐시 경로)
 *   - skip_comfyui: bool (캐시 히트 시 true)
 *   - position, z_index, zoom_rate (메타 통과)
 *
 * 워크플로우 전역 (Node 1):
 *   - $('Load Files').first().json.project_root
 *
 * 출력: { chapter_id, scenes: { <scene_id>: { regions: { <region_id>: { bg, characters[], props[], foreground? } } } } }
 *
 * 환경: Node.js 빌트인 (fs / path / child_process). cwebp CLI 필수.
 */

const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");

// ──────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function convertToWebP(srcPng, dstWebp, lossless) {
  try {
    const args = lossless
      ? [srcPng, "-lossless", "-o", dstWebp]
      : [srcPng, "-q", "95", "-o", dstWebp];
    execFileSync("cwebp", args, { timeout: 30000 });
    if (fs.existsSync(dstWebp) && fs.statSync(dstWebp).size > 0) {
      return true;
    }
  } catch (e) {
    // cwebp 실패 — 폴백
  }
  return false;
}

// ──────────────────────────────────────────────
// Main
// ──────────────────────────────────────────────

const items = $input.all();
const node1 = $("Load Files").first().json;
const PROJECT_ROOT = node1.project_root;

if (!PROJECT_ROOT) throw new Error("[Node 9] project_root 누락");

// project_config.json에서 image_format 정책 읽기
let useLossless = true;
try {
  const configPath = path.join(PROJECT_ROOT, "..", "project_config.json");
  if (fs.existsSync(configPath)) {
    const config = JSON.parse(fs.readFileSync(configPath, "utf-8"));
    const fmt = config.baseline && config.baseline.image_format;
    if (fmt && fmt.primary !== "webp_lossless") {
      useLossless = false;
    }
  }
} catch (e) {
  // config 읽기 실패 시 lossless 기본값 유지
}

// 챕터별 씬별 에셋 수집
const chapterMap = {}; // chapter_id → { scenes: { scene_id: { regions: { region_id: { ... } } } } }

for (const it of items) {
  let item = it.json;

  // [버그 수정] Wait Webhook(Node 8) 노드 통과 시 n8n이 기존 데이터를 전부 날리고 
  // webhook body만 반환하는 문제 방어:
  // webhook body에 prompt_id가 있다면 Node 7 원본 데이터에서 메타데이터 복원
  if (!item.chapter_id && (item.prompt_id || (item.body && item.body.prompt_id))) {
    const pId = item.prompt_id || item.body.prompt_id;
    try {
      const n7Items = $items("Node 7 — ComfyUI Payload");
      const orig = n7Items.find(o => o.json.prompt_id === pId);
      if (orig) {
        item = { ...orig.json, ...(item.body || item) }; // 원본 메타 + 웹훅 응답 병합
      }
    } catch (e) {
      console.warn(`[Node 9] 원본 데이터 복구 실패 (prompt_id=${pId})`);
    }
  }

  if (!item || !item.output_path) continue;

  const chapterId = item.chapter_id;
  const sceneId = item.scene_id;
  const assetType = item.asset_type;
  const sceneAssetId = item.scene_asset_id;
  const regionId = item.region_id || "default";

  // 대상 폴더: project/asset/<chapter_id>/<scene_id>/
  const assetDir = path.join(PROJECT_ROOT, "asset", chapterId, sceneId);
  ensureDir(assetDir);

  // 파일명 규격화
  let baseName;
  if (assetType === "background") {
    baseName = `${sceneId}_bg`;
  } else if (assetType === "foreground") {
    baseName = `${sceneId}_foreground`;
  } else {
    baseName = `${sceneId}_${sceneAssetId}`;
  }

  const srcPath = item.output_path;
  const srcExt = path.extname(srcPath).toLowerCase();
  let finalPath;

  // WebP 변환 시도
  if (srcExt === ".png") {
    const webpPath = path.join(assetDir, `${baseName}.webp`);
    if (convertToWebP(srcPath, webpPath, useLossless)) {
      finalPath = webpPath;
    } else {
      // 폴백: PNG 그대로 복사
      finalPath = path.join(assetDir, `${baseName}.png`);
      fs.copyFileSync(srcPath, finalPath);
    }
  } else if (srcExt === ".webp") {
    finalPath = path.join(assetDir, `${baseName}.webp`);
    if (srcPath !== finalPath) fs.copyFileSync(srcPath, finalPath);
  } else {
    finalPath = path.join(assetDir, `${baseName}${srcExt}`);
    if (srcPath !== finalPath) fs.copyFileSync(srcPath, finalPath);
  }

  // 상대 경로 (project_root 기준)
  const relPath = path.relative(PROJECT_ROOT, finalPath).replace(/\\/g, "/");

  // chapterMap 구조 구축
  if (!chapterMap[chapterId]) {
    chapterMap[chapterId] = { scenes: {} };
  }
  const ch = chapterMap[chapterId];
  if (!ch.scenes[sceneId]) {
    ch.scenes[sceneId] = { regions: {} };
  }
  if (!ch.scenes[sceneId].regions[regionId]) {
    ch.scenes[sceneId].regions[regionId] = { characters: [], props: [] };
  }
  const region = ch.scenes[sceneId].regions[regionId];

  if (assetType === "background") {
    region.bg = relPath;
  } else if (assetType === "foreground") {
    region.foreground = {
      path: relPath,
      zoom_rate: item.zoom_rate || 1.0,
    };
  } else if (assetType === "character") {
    region.characters.push({
      scene_asset_id: sceneAssetId,
      path: relPath,
      position: item.position || "center",
      z_index: item.z_index || 100,
    });
  } else if (assetType === "prop") {
    region.props.push({
      path: relPath,
      z_index: item.z_index || 50,
    });
  }
}

// 출력: 챕터별 1 아이템
const output = [];
for (const [chapterId, data] of Object.entries(chapterMap)) {
  output.push({
    json: {
      chapter_id: chapterId,
      scenes: data.scenes,
    },
  });
}

return output;
