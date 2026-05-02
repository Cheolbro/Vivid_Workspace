/**
 * Node 7 단위 테스트 — 과제 12 핵심 로직 검증.
 *
 * 검증 대상:
 *   1. resolveCharacterVariant — pose:auto / pose:<id> applicable 매칭 / 미매칭 시 front 폴백
 *   2. computeCacheKey — character/prop는 seed 제외, background/foreground는 seed 포함
 *   3. processItem — controlnet_active / vram_policy / variant_chosen 종합 라우팅
 *
 * 실행: node n8n_workflow/nodes/node7_comfyui_payload.test.js
 */

const path = require("path");
const fs = require("fs");
const os = require("os");

const mod = require("./node7_comfyui_payload.js");

const {
  resolveCharacterVariant,
  computeCacheKey,
  parseCharacterKeyFromRefId,
  findCharacterEntry,
  processItem,
  constants,
} = mod;

let pass = 0;
let fail = 0;

function eq(name, actual, expected) {
  const ok = JSON.stringify(actual) === JSON.stringify(expected);
  if (ok) {
    pass++;
    console.log(`  ✔ ${name}`);
  } else {
    fail++;
    console.log(
      `  ✖ ${name}\n    expected: ${JSON.stringify(expected)}\n    actual:   ${JSON.stringify(actual)}`
    );
  }
}

function truthy(name, v) {
  if (v) {
    pass++;
    console.log(`  ✔ ${name}`);
  } else {
    fail++;
    console.log(`  ✖ ${name} (falsy)`);
  }
}

// ──────────────────────────────────────────────
// Fixtures
// ──────────────────────────────────────────────

const POSE_LIBRARY = {
  poses: {
    pose_anchor_neutral: {
      category: "static",
      applicable_character_angle: ["front"],
      file_path: "assets/poses/pose_anchor_neutral.png",
    },
    listening: {
      category: "static",
      applicable_character_angle: ["side"],
      file_path: "assets/poses/listening.png",
    },
    pose_pointing_data: {
      category: "action",
      applicable_character_angle: ["side"],
      file_path: "assets/poses/pose_pointing_data.png",
    },
    arms_crossed_authority: {
      category: "action",
      applicable_character_angle: ["front"],
      file_path: "assets/poses/arms_crossed_authority.png",
    },
  },
};

const CHAR_KIM = {
  variants: {
    front: {
      ref_image_id: "char_anchor_kim_front",
      file_path: "assets/references/char_anchor_kim_front.png",
      is_face_anchor: true,
    },
    side: {
      ref_image_id: "char_anchor_kim_side",
      file_path: "assets/references/char_anchor_kim_side.png",
      is_face_anchor: false,
    },
    back: {
      ref_image_id: "char_anchor_kim_back",
      file_path: "assets/references/char_anchor_kim_back.png",
      is_face_anchor: false,
    },
  },
};

const CHAR_NO_FACE_ANCHOR = {
  variants: {
    side: {
      ref_image_id: "char_x_side",
      file_path: "assets/references/char_x_side.png",
      is_face_anchor: false,
    },
    back: {
      ref_image_id: "char_x_back",
      file_path: "assets/references/char_x_back.png",
      is_face_anchor: false,
    },
  },
};

const CATALOG = {
  characters: { anchor_kim: { ...CHAR_KIM, appearance_anchor: "..." } },
  props: {
    newspaper_economic: {
      ref_image_id: "prop_newspaper_economic",
      file_path: "assets/references/prop_newspaper_economic.png",
    },
  },
};

// ──────────────────────────────────────────────
// 1. resolveCharacterVariant
// ──────────────────────────────────────────────

console.log("\n[1] resolveCharacterVariant");

let r = resolveCharacterVariant({
  characterEntry: CHAR_KIM,
  poseId: "auto",
  poseLibrary: POSE_LIBRARY,
});
eq("auto → is_face_anchor variant 선택 (front)", r.angle, "front");
eq("auto → fallback_used:false", r.fallback_used, false);

r = resolveCharacterVariant({
  characterEntry: CHAR_KIM,
  poseId: "listening",
  poseLibrary: POSE_LIBRARY,
});
eq("listening (applicable=side) → side variant 선택", r.angle, "side");
eq("applicable 매칭 fallback_used:false", r.fallback_used, false);

r = resolveCharacterVariant({
  characterEntry: CHAR_KIM,
  poseId: "pose_anchor_neutral",
  poseLibrary: POSE_LIBRARY,
});
eq("pose_anchor_neutral (applicable=front) → front", r.angle, "front");

r = resolveCharacterVariant({
  characterEntry: CHAR_KIM,
  poseId: "unknown_pose",
  poseLibrary: POSE_LIBRARY,
});
eq("미존재 pose_id → front 폴백 (is_face_anchor)", r.angle, "front");
eq("미존재 pose_id fallback_used:true", r.fallback_used, true);
truthy(
  "미존재 pose_id reason 포함 'pose_id_not_in_library'",
  String(r.reason).includes("pose_id_not_in_library")
);

// applicable에 없는 angle만 있는 캐릭터
const POSE_NEEDING_BACK = { poses: { pose_x: { applicable_character_angle: ["back"] } } };
const CHAR_FRONT_SIDE = {
  variants: {
    front: {
      ref_image_id: "char_a_front",
      file_path: "assets/references/char_a_front.png",
      is_face_anchor: true,
    },
    side: {
      ref_image_id: "char_a_side",
      file_path: "assets/references/char_a_side.png",
      is_face_anchor: false,
    },
  },
};
r = resolveCharacterVariant({
  characterEntry: CHAR_FRONT_SIDE,
  poseId: "pose_x",
  poseLibrary: POSE_NEEDING_BACK,
});
eq("applicable=[back] 매칭 미스 → front 폴백", r.angle, "front");
eq("매칭 미스 fallback_used:true", r.fallback_used, true);
eq("매칭 미스 reason='no_applicable_variant'", r.reason, "no_applicable_variant");

// is_face_anchor 없는 캐릭터에서 front 키 폴백
r = resolveCharacterVariant({
  characterEntry: CHAR_NO_FACE_ANCHOR,
  poseId: "auto",
  poseLibrary: POSE_LIBRARY,
});
eq("face_anchor 없을 때 auto → 첫 variant", r.angle, "side");
eq("face_anchor 없을 때 fallback_used:true", r.fallback_used, true);

// ──────────────────────────────────────────────
// 2. computeCacheKey — seed 포함 정책
// ──────────────────────────────────────────────

console.log("\n[2] computeCacheKey (seed 포함 정책)");

const baseChar = {
  asset_type: "character",
  ref_image_id: "char_anchor_kim_front",
  description_render: "A 40-something Korean male anchor",
  lora_signature: "noir_webtoon_style@0.65",
  seed: 12345,
};
const charKey1 = computeCacheKey(baseChar);
const charKey2 = computeCacheKey({ ...baseChar, seed: 99999 });
eq("character 캐시 키는 seed 변경 시 동일해야 함 (영상 1편 내 동일 시드)", charKey1, charKey2);

const baseBg = { ...baseChar, asset_type: "background" };
const bgKey1 = computeCacheKey(baseBg);
const bgKey2 = computeCacheKey({ ...baseBg, seed: 99999 });
truthy("background 캐시 키는 seed 변경 시 달라야 함 (씬마다 다른 시드)", bgKey1 !== bgKey2);

// ──────────────────────────────────────────────
// 3. parseCharacterKeyFromRefId / findCharacterEntry
// ──────────────────────────────────────────────

console.log("\n[3] parseCharacterKeyFromRefId / findCharacterEntry");

eq(
  "parse char_anchor_kim_front",
  parseCharacterKeyFromRefId("char_anchor_kim_front"),
  "anchor_kim"
);
eq("parse char_x_y_z_back", parseCharacterKeyFromRefId("char_x_y_z_back"), "x_y_z");
eq("parse 잘못된 형식 → null", parseCharacterKeyFromRefId("not_a_char_id"), null);

const found = findCharacterEntry(CATALOG, "char_anchor_kim_side");
eq("findCharacterEntry: variants ref_image_id로 매칭", found && found.key, "anchor_kim");

// ──────────────────────────────────────────────
// 4. processItem — 종합 (캐시 미스 경로)
// ──────────────────────────────────────────────

console.log("\n[4] processItem (캐시 미스 경로)");

// tmp 합성 레포 루트 — assets/poses, assets/references, shared_assets 스텁 생성
const tmpRepo = fs.mkdtempSync(path.join(os.tmpdir(), "node7_test_"));
const tmpRoot = path.join(tmpRepo, "project");
const sharedRoot = path.join(tmpRepo, "shared_assets");
fs.mkdirSync(tmpRoot, { recursive: true });
fs.mkdirSync(sharedRoot, { recursive: true });
fs.mkdirSync(path.join(tmpRepo, "assets", "poses"), { recursive: true });
fs.mkdirSync(path.join(tmpRepo, "assets", "references"), { recursive: true });
// 포즈 PNG 스텁 (운영 자산 방어 로직 우회)
for (const p of [
  "pose_anchor_neutral",
  "listening",
  "pose_pointing_data",
  "arms_crossed_authority",
]) {
  fs.writeFileSync(path.join(tmpRepo, "assets", "poses", `${p}.png`), "stub");
}
// 캐릭터 ref 이미지 스텁
for (const angle of ["front", "side", "back"]) {
  fs.writeFileSync(
    path.join(tmpRepo, "assets", "references", `char_anchor_kim_${angle}.png`),
    "stub"
  );
}

const charItemAuto = {
  chapter_id: "chapter_01",
  scene_id: "scene_01",
  asset_type: "character",
  scene_asset_id: "character_01",
  region_id: "default",
  description_render: "test prompt for kim auto",
  ref_image_id: "char_anchor_kim_front",
  pose: "auto",
  seed: 1234,
  lora_signature: "noir_webtoon_style@0.65",
};

const fakePoseLib = {
  poses: {
    listening: { applicable_character_angle: ["side"] },
    arms_crossed_authority: { applicable_character_angle: ["front"] },
  },
};
const fakeCatalog = {
  characters: { anchor_kim: CHAR_KIM },
  props: {},
};

let res = processItem({
  item: charItemAuto,
  catalog: fakeCatalog,
  poseLibrary: fakePoseLib,
  projectRoot: tmpRoot,
  sharedAssetsRoot: sharedRoot,
});
eq("auto → controlnet_active=false", res.controlnet_active, false);
eq("auto → vram_policy=Q5_K_M", res.vram_policy, "Q5_K_M");
eq("auto → variant_chosen.angle=front", res.variant_chosen.angle, "front");
truthy("auto → comfyui_payload 존재", res.comfyui_payload && res.comfyui_payload.prompt);
truthy("auto → ControlNetApplyAdvanced 노드 부재", !res.comfyui_payload.prompt["22"]);

const charItemListening = { ...charItemAuto, pose: "listening" };
res = processItem({
  item: charItemListening,
  catalog: fakeCatalog,
  poseLibrary: fakePoseLib,
  projectRoot: tmpRoot,
  sharedAssetsRoot: sharedRoot,
});
eq("listening (applicable=side) → controlnet_active=true", res.controlnet_active, true);
eq("listening → vram_policy=Q4_K_M (자동 다운그레이드)", res.vram_policy, "Q4_K_M");
eq("listening → variant_chosen.angle=side", res.variant_chosen.angle, "side");
truthy("listening → ControlNetApplyAdvanced 노드 존재", !!res.comfyui_payload.prompt["22"]);
truthy(
  "listening → IP-Adapter weight=0.35 (controlled)",
  Math.abs(res.comfyui_payload.prompt["12"].inputs.weight - constants.IP_ADAPTER_CONTROLLED) < 1e-9
);

const charItemUnmatched = { ...charItemAuto, pose: "arms_crossed_authority" };
res = processItem({
  item: charItemUnmatched,
  catalog: fakeCatalog,
  poseLibrary: fakePoseLib,
  projectRoot: tmpRoot,
  sharedAssetsRoot: sharedRoot,
});
eq(
  "arms_crossed_authority (applicable=front) → variant.angle=front",
  res.variant_chosen.angle,
  "front"
);
eq("front 매칭 시 fallback_used=false", res.variant_chosen.fallback_used, false);

// background → vram_policy=Q5_K_M, controlnet 없음, ip_adapter_unloaded=true
const bgItem = {
  chapter_id: "chapter_01",
  scene_id: "scene_01",
  asset_type: "background",
  scene_asset_id: "background",
  region_id: "default",
  description_render: "studio interior",
  ref_image_id: "none",
  seed: 7777,
  lora_signature: "noir_webtoon_style@0.65",
};
res = processItem({
  item: bgItem,
  catalog: fakeCatalog,
  poseLibrary: fakePoseLib,
  projectRoot: tmpRoot,
  sharedAssetsRoot: sharedRoot,
});
eq("background → ip_adapter_unloaded=true", res.ip_adapter_unloaded, true);
eq("background → variant_chosen=null", res.variant_chosen, null);
truthy("background → ControlNet 부재", !res.comfyui_payload.prompt["22"]);
truthy("background → IPAdapterAdvanced 부재", !res.comfyui_payload.prompt["12"]);

// prop with ref_image_id="none" → ip_adapter_unloaded=true (text2img + 모델 unload)
const propNone = {
  chapter_id: "chapter_01",
  scene_id: "scene_02",
  asset_type: "prop",
  scene_asset_id: "prop_01",
  region_id: "default",
  description_render: "isolated coffee cup, transparent background",
  ref_image_id: "none",
  seed: 2222,
  lora_signature: "noir_webtoon_style@0.65",
};
res = processItem({
  item: propNone,
  catalog: fakeCatalog,
  poseLibrary: fakePoseLib,
  projectRoot: tmpRoot,
  sharedAssetsRoot: sharedRoot,
});
eq("prop ref_image_id=none → ip_adapter_unloaded=true", res.ip_adapter_unloaded, true);

// ──────────────────────────────────────────────
// 5. processItem — L3 캐시 히트 경로
// ──────────────────────────────────────────────

console.log("\n[5] processItem (L3 캐시 히트)");

const cacheKey = computeCacheKey(charItemAuto);
fs.mkdirSync(path.join(tmpRoot, "asset_cache"), { recursive: true });
fs.writeFileSync(path.join(tmpRoot, "asset_cache", `${cacheKey}.webp`), "fake-webp-bytes");

res = processItem({
  item: charItemAuto,
  catalog: fakeCatalog,
  poseLibrary: fakePoseLib,
  projectRoot: tmpRoot,
  sharedAssetsRoot: sharedRoot,
});
eq("캐시 히트 → skip_comfyui=true", res.skip_comfyui, true);
truthy("캐시 히트 → cached_path 존재", !!res.cached_path);
truthy("캐시 히트 → comfyui_payload 부재", !res.comfyui_payload);

// ──────────────────────────────────────────────
// 결과
// ──────────────────────────────────────────────

console.log(`\n결과: ${pass} pass / ${fail} fail`);
process.exit(fail === 0 ? 0 : 1);
