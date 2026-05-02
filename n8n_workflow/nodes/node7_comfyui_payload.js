/**
 * Node 7 — ComfyUI Payload Builder (n8n Code Node, JavaScript)
 *
 * 목적: Node 4 출력 asset_prompts → ComfyUI API 워크플로우 JSON 빌드.
 *      Node 6 Switch가 asset_type으로 7A/7B/7C/7D로 분기한 뒤 본 Code Node를 공통 호출.
 *
 * 과제 12 (Phase E) — Node 7 ControlNet 분기:
 *   - pose:"auto"     → [Prompt + FaceID(0.85) + IP-Adapter(0.65)] 그대로 (ControlNet 미적용)
 *   - pose:"<id>"     → [Prompt + FaceID(0.85) + IP-Adapter(0.30~0.40) + ControlNet(OpenPose)]
 *   - assets/poses/<pose_id>.png 를 LoadImage로 ControlNet에 주입
 *   - character variant 자동 매칭:
 *       pose_library.json[pose_id].applicable_character_angle 참조
 *       → catalog.characters[<key>].variants 중 첫 매칭 variant 선택
 *       → 미매칭 시 is_face_anchor:true 또는 "front" variant로 폴백 (FaceID 정면 학습 안정)
 *
 * v4.5 §1.2 / §6.2 VRAM 동시 점유 정책 (Intel Arc 8.9GB 한계 방어):
 *   - Auto 모드(ControlNet 미활성)        → flux1-schnell-Q5_K_M.gguf  (≈7.5GB)
 *   - Controlled 모드(ControlNet 활성)    → flux1-schnell-Q4_K_M.gguf  (≈6.0GB) — 자동 다운그레이드 강제
 *   - background/foreground (Node 7C/7D)  → IP-Adapter 노드 자체 제거
 *   - prop with ref_image_id == "none"    → IP-Adapter weight=0 + 모델 unload (0.5GB 회수)
 *
 * L3 SHA1 캐시 키 정책 (§3 Node 7 운영 로직 0 / EF-1):
 *   - character/prop      : SHA1(ref_image_id|description_render|lora_signature)  (seed 제외)
 *   - background/foreground: SHA1(ref_image_id|seed|description_render|lora_signature)
 *   - 캐시 히트 시 ComfyUI HTTP 호출 스킵(skip_comfyui:true) + cached_path 반환.
 *
 * 입력 (n8n items[].json — Node 6 Switch 출력):
 *   - chapter_id, scene_id, asset_type, scene_asset_id, region_id
 *   - description_render, ref_image_id, reuse_asset_id, generate_asset
 *   - pose ("auto" | "pose_<id>"), seed, lora_signature, position
 *
 * 워크플로우 전역 (Node 1):
 *   - $('Load Files').first().json.video_id
 *   - $('Load Files').first().json.project_root
 *   - $('Load Files').first().json.shared_assets_root  (옵션, 미지정 시 ../../shared_assets)
 *
 * 출력 (각 입력 1:1 대응 — 메타데이터를 그대로 통과시켜 Node 8/9에서 활용):
 *   {
 *     ...item,                       // 원본 메타 통과
 *     prompt_id: "<uuid>",
 *     skip_comfyui: bool,
 *     cached_path?: "<asset_cache/...>",
 *     comfyui_payload?: { client_id, prompt: {...} },
 *     output_path: "<project/asset_cache/<sha1>.webp>",
 *     vram_policy: "Q5_K_M"|"Q4_K_M",
 *     controlnet_active: bool,
 *     ip_adapter_unloaded: bool,
 *     variant_chosen: { angle, ref_image_id, file_path, fallback_used, reason } | null
 *   }
 *
 * v5.0 멀티 포맷 Multi-Sourcing 분기:
 *   - source_api: "pexels" | "pixabay" → ComfyUI 스킵, API 라우팅 메타 통과
 *   - bg_style: "solid_color" + skip_comfyui:true → ComfyUI 스킵, CSS로 처리
 *   - 위 두 경우 comfyui_payload 를 생성하지 않고 원본 메타 그대로 반환
 *
 * 환경: Node.js 빌트인만 (fs / path / crypto). 외부 npm 모듈 불필요.
 */

const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

// ──────────────────────────────────────────────
// 상수: VRAM 모델 / 가중치 / 경로
// ──────────────────────────────────────────────

const MODEL_AUTO = "flux1-schnell-Q5_K_M.gguf";
const MODEL_CONTROLLED = "flux1-schnell-Q4_K_M.gguf";

const FACEID_WEIGHT = 0.85;
const IP_ADAPTER_AUTO = 0.65;
const IP_ADAPTER_CONTROLLED = 0.35; // 0.30~0.40 범위 중앙
const CONTROLNET_OPENPOSE_STRENGTH = 0.7;
const PROP_DENOISE_STRENGTH = 0.5;
const LORA_STRENGTH_DEFAULT = 0.65;

const CONTROLNET_OPENPOSE_MODEL = "control_v11p_sd15_openpose.pth";
const FACEID_IPADAPTER_MODEL = "ip-adapter-faceid-portrait_sd15.bin";
const STYLE_IPADAPTER_MODEL = "ip-adapter_sd15.safetensors";

const POSES_DIR = "assets/poses";
const REFERENCES_DIR = "assets/references";

const FALLBACK_VARIANT_KEY = "front"; // §4.2.3: 미매칭 시 front_neutral 폴백 (FaceID 정면 학습 가장 안정)

// 과제 24: project_config.json에서 ComfyUI 정책 로드 (BN-1)
const SAMPLING_STEPS_AUTO = 3;
const SAMPLING_STEPS_CONTROLLED = 4;

const NEGATIVE_PROMPT =
  "watermark, text, signature, low quality, blurry, deformed, extra limbs, bad anatomy";

// ──────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────

function sha1Hex(s) {
  return crypto.createHash("sha1").update(s).digest("hex");
}

function uuid() {
  // RFC 4122 v4 (간이 구현 — n8n Code Node 외부 의존 회피)
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

function readJsonSafe(p, label) {
  if (!fs.existsSync(p)) throw new Error(`[Node 7] ${label} 누락: ${p}`);
  try {
    return JSON.parse(fs.readFileSync(p, "utf-8"));
  } catch (e) {
    throw new Error(`[Node 7] ${label} 파싱 실패 (${p}): ${e.message}`);
  }
}

function toPosixPath(p) {
  return p.replace(/\\/g, "/");
}

// ──────────────────────────────────────────────
// 캐릭터 키 추출 (ref_image_id "char_<key>_<angle>" → <key>)
// 카탈로그가 있는데 직접 매칭이 더 안전한 경우 fallback으로 사용.
// ──────────────────────────────────────────────

function parseCharacterKeyFromRefId(refImageId) {
  const m = /^char_(.+)_(front|side|back)$/.exec(refImageId || "");
  return m ? m[1] : null;
}

function findCharacterEntry(catalog, refImageId) {
  const characters = catalog.characters || {};
  // 1차: variants[*].ref_image_id 정확 매칭
  for (const [key, entry] of Object.entries(characters)) {
    if (key.startsWith("_")) continue;
    const variants = entry.variants || {};
    for (const v of Object.values(variants)) {
      if (v.ref_image_id === refImageId) return { key, entry };
    }
  }
  // 2차: ref_image_id에서 key 파싱 후 catalog.characters[key] 직접 조회
  const parsed = parseCharacterKeyFromRefId(refImageId);
  if (parsed && characters[parsed]) return { key: parsed, entry: characters[parsed] };
  return null;
}

// ──────────────────────────────────────────────
// 과제 12: character variant 자동 매칭
// ──────────────────────────────────────────────

function resolveCharacterVariant({ characterEntry, poseId, poseLibrary }) {
  const variants = characterEntry.variants || {};
  if (Object.keys(variants).length === 0) {
    throw new Error("[Node 7] character.variants 비어 있음 — 폴백 불가");
  }

  // pose:"auto" → is_face_anchor 우선, 없으면 첫 variant
  if (!poseId || poseId === "auto") {
    const anchor = Object.entries(variants).find(([, v]) => v.is_face_anchor);
    if (anchor) {
      return {
        angle: anchor[0],
        variant: anchor[1],
        fallback_used: false,
        reason: "auto_face_anchor",
      };
    }
    const first = Object.entries(variants)[0];
    return {
      angle: first[0],
      variant: first[1],
      fallback_used: true,
      reason: "auto_no_face_anchor",
    };
  }

  // pose:"<id>" → pose_library의 applicable_character_angle 중 첫 매칭 variant
  const poseEntry = (poseLibrary.poses || {})[poseId];
  if (!poseEntry) {
    return tryFrontFallback(variants, `pose_id_not_in_library:${poseId}`);
  }

  const applicable = poseEntry.applicable_character_angle || [];
  for (const angle of applicable) {
    if (variants[angle]) {
      return { angle, variant: variants[angle], fallback_used: false, reason: "applicable_match" };
    }
  }

  // 매칭 미스 → front 폴백 (FaceID 정면 학습 안정)
  return tryFrontFallback(variants, "no_applicable_variant");
}

function tryFrontFallback(variants, reason) {
  // 1차: is_face_anchor:true variant
  const faceAnchor = Object.entries(variants).find(([, v]) => v.is_face_anchor);
  if (faceAnchor) {
    return { angle: faceAnchor[0], variant: faceAnchor[1], fallback_used: true, reason };
  }
  // 2차: "front" 키
  if (variants[FALLBACK_VARIANT_KEY]) {
    return {
      angle: FALLBACK_VARIANT_KEY,
      variant: variants[FALLBACK_VARIANT_KEY],
      fallback_used: true,
      reason: `${reason}__front_key_fallback`,
    };
  }
  // 3차: 첫 variant
  const first = Object.entries(variants)[0];
  return {
    angle: first[0],
    variant: first[1],
    fallback_used: true,
    reason: `${reason}__first_variant`,
  };
}

// ──────────────────────────────────────────────
// L3 SHA1 캐시 키 (§3 Node 7 운영 로직 0 / EF-1)
// ──────────────────────────────────────────────

function computeCacheKey(item) {
  const { asset_type, ref_image_id, description_render, lora_signature, seed } = item;
  if (asset_type === "character" || asset_type === "prop") {
    return sha1Hex(`${ref_image_id}|${description_render}|${lora_signature}`);
  }
  return sha1Hex(`${ref_image_id}|${seed}|${description_render}|${lora_signature}`);
}

// ──────────────────────────────────────────────
// ComfyUI 워크플로우 빌더 (분기별)
// ──────────────────────────────────────────────

function commonHead({ model, prompt }) {
  return {
    1: { class_type: "UnetLoaderGGUF", inputs: { unet_name: model } },
    "1c": {
      class_type: "DualCLIPLoaderGGUF",
      inputs: { clip_name1: "t5xxl_fp8.gguf", clip_name2: "clip_l.safetensors", type: "flux" },
    },
    "1v": { class_type: "VAELoader", inputs: { vae_name: "ae.safetensors" } },
    2: { class_type: "CLIPTextEncode", inputs: { text: prompt, clip: ["1c", 0] } },
    3: { class_type: "CLIPTextEncode", inputs: { text: NEGATIVE_PROMPT, clip: ["1c", 0] } },
    4: { class_type: "EmptyLatentImage", inputs: { width: 1024, height: 1024, batch_size: 1 } },
  };
}

function attachKSamplerAndDecode(wf, { modelOut, positiveOut, negativeOut, seed, steps }) {
  wf["30"] = {
    class_type: "KSampler",
    inputs: {
      model: modelOut,
      positive: positiveOut,
      negative: negativeOut,
      latent_image: ["4", 0],
      seed,
      steps: steps || SAMPLING_STEPS_AUTO,
      cfg: 1.0,
      sampler_name: "euler",
      scheduler: "simple",
      denoise: 1.0,
    },
  };
  wf["31"] = { class_type: "VAEDecode", inputs: { samples: ["30", 0], vae: ["1v", 0] } };
}

function attachLayerDiffusionAndSave(wf, { item, sourceNode = "31", cacheKey, projectRoot }) {
  // LayerDiffusion alpha 분리
  wf["40"] = {
    class_type: "LayeredDiffusionDecode",
    inputs: { image: [sourceNode, 0], samples: ["30", 0] },
  };
  // 캐시 키 기반 파일명 — 이후 운영에서 동일 SHA1 식별 용이
  wf["50"] = {
    class_type: "SaveImage",
    inputs: {
      images: ["40", 0],
      filename_prefix: toPosixPath(`asset_cache/${cacheKey}`),
    },
  };
  // ComfyUI 완료 → n8n 웹훅 (Node 8 resume)
  wf["99"] = {
    class_type: "WebhookOnComplete",
    inputs: {
      url: "{{N8N_RESUME_WEBHOOK}}",
      body_json: {
        resumeKey: "{{PROMPT_ID}}",
        file_path: `${projectRoot}/asset_cache/${cacheKey}.webp`,
      },
      images: ["50", 0],
    },
  };
}

// ── 7A: Character (text2img + FaceID + IP-Adapter + optional ControlNet + Alpha) ──
function buildCharacterWorkflow({
  item,
  variant,
  controlled,
  posePngAbsPath,
  refImageAbsPath,
  projectRoot,
  cacheKey,
}) {
  const model = controlled ? MODEL_CONTROLLED : MODEL_AUTO;
  const ipWeight = controlled ? IP_ADAPTER_CONTROLLED : IP_ADAPTER_AUTO;

  const wf = commonHead({ model, prompt: item.description_render });

  // LoadImage (FaceID/IP-Adapter 레퍼런스 — 선택된 variant)
  wf["10"] = { class_type: "LoadImage", inputs: { image: toPosixPath(refImageAbsPath) } };

  // FaceID
  wf["11"] = {
    class_type: "IPAdapterFaceID",
    inputs: {
      model: ["1", 0],
      ipadapter: FACEID_IPADAPTER_MODEL,
      image: ["10", 0],
      weight: FACEID_WEIGHT,
    },
  };

  // IP-Adapter (style)
  wf["12"] = {
    class_type: "IPAdapterAdvanced",
    inputs: {
      model: ["11", 0],
      ipadapter: STYLE_IPADAPTER_MODEL,
      image: ["10", 0],
      weight: ipWeight,
    },
  };

  // LoRA
  wf["13"] = {
    class_type: "LoraLoader",
    inputs: {
      model: ["12", 0],
      clip: ["1c", 0],
      lora_name: `${(item.lora_signature || "noir_webtoon_style").split("@")[0]}.safetensors`,
      strength_model: LORA_STRENGTH_DEFAULT,
      strength_clip: LORA_STRENGTH_DEFAULT,
    },
  };

  let modelOut = ["13", 0];
  let positiveOut = ["2", 0];
  let negativeOut = ["3", 0];

  // 과제 12 — ControlNet 분기 (controlled 모드만)
  if (controlled) {
    wf["20"] = { class_type: "LoadImage", inputs: { image: toPosixPath(posePngAbsPath) } };
    wf["21"] = {
      class_type: "ControlNetLoader",
      inputs: { control_net_name: CONTROLNET_OPENPOSE_MODEL },
    };
    wf["22"] = {
      class_type: "ControlNetApplyAdvanced",
      inputs: {
        positive: positiveOut,
        negative: negativeOut,
        control_net: ["21", 0],
        image: ["20", 0],
        strength: CONTROLNET_OPENPOSE_STRENGTH,
        start_percent: 0.0,
        end_percent: 1.0,
      },
    };
    positiveOut = ["22", 0];
    negativeOut = ["22", 1];
  }

  attachKSamplerAndDecode(wf, {
    modelOut,
    positiveOut,
    negativeOut,
    seed: item.seed,
    steps: controlled ? SAMPLING_STEPS_CONTROLLED : SAMPLING_STEPS_AUTO,
  });
  attachLayerDiffusionAndSave(wf, { item, sourceNode: "31", cacheKey, projectRoot });
  return wf;
}

// ── 7B: Prop (img2img + IP-Adapter + Alpha, ref_image_id="none"이면 IP-Adapter unload) ──
function buildPropWorkflow({ item, refImageAbsPath, projectRoot, cacheKey }) {
  const model = MODEL_AUTO;
  const wf = commonHead({ model, prompt: item.description_render });

  const isNoneRef = !item.ref_image_id || item.ref_image_id === "none" || !refImageAbsPath;

  if (isNoneRef) {
    // text2img + IP-Adapter weight=0 + 모델 unload (0.5GB 회수)
    wf["13"] = {
      class_type: "LoraLoader",
      inputs: {
        model: ["1", 0],
        clip: ["1c", 0],
        lora_name: `${(item.lora_signature || "noir_webtoon_style").split("@")[0]}.safetensors`,
        strength_model: LORA_STRENGTH_DEFAULT,
        strength_clip: LORA_STRENGTH_DEFAULT,
      },
    };
    attachKSamplerAndDecode(wf, {
      modelOut: ["13", 0],
      positiveOut: ["2", 0],
      negativeOut: ["3", 0],
      seed: item.seed,
    });
    attachLayerDiffusionAndSave(wf, { item, sourceNode: "31", cacheKey, projectRoot });
    return wf;
  }

  // img2img: VAEEncode → KSampler with denoise=0.5
  wf["10"] = { class_type: "LoadImage", inputs: { image: toPosixPath(refImageAbsPath) } };
  wf["10e"] = { class_type: "VAEEncode", inputs: { pixels: ["10", 0], vae: ["1v", 0] } };
  // EmptyLatentImage 대체: 노드 4를 VAEEncode 출력으로 교체
  wf["4"] = { class_type: "PassThrough", inputs: { latent: ["10e", 0] } };

  wf["12"] = {
    class_type: "IPAdapterAdvanced",
    inputs: {
      model: ["1", 0],
      ipadapter: STYLE_IPADAPTER_MODEL,
      image: ["10", 0],
      weight: IP_ADAPTER_AUTO, // prop 실루엣 일관성
    },
  };
  wf["13"] = {
    class_type: "LoraLoader",
    inputs: {
      model: ["12", 0],
      clip: ["1c", 0],
      lora_name: `${(item.lora_signature || "noir_webtoon_style").split("@")[0]}.safetensors`,
      strength_model: LORA_STRENGTH_DEFAULT,
      strength_clip: LORA_STRENGTH_DEFAULT,
    },
  };

  // KSampler — denoise 0.5 (img2img)
  wf["30"] = {
    class_type: "KSampler",
    inputs: {
      model: ["13", 0],
      positive: ["2", 0],
      negative: ["3", 0],
      latent_image: ["10e", 0],
      seed: item.seed,
      steps: SAMPLING_STEPS_AUTO,
      cfg: 1.0,
      sampler_name: "euler",
      scheduler: "simple",
      denoise: PROP_DENOISE_STRENGTH,
    },
  };
  wf["31"] = { class_type: "VAEDecode", inputs: { samples: ["30", 0], vae: ["1v", 0] } };
  attachLayerDiffusionAndSave(wf, { item, sourceNode: "31", cacheKey, projectRoot });
  return wf;
}

// ── 7C: Background (pure FLUX, no Alpha, no IP-Adapter) ──
function buildBackgroundWorkflow({ item, projectRoot, cacheKey }) {
  const model = MODEL_AUTO;
  const wf = commonHead({ model, prompt: item.description_render });

  // 16:9 (1920x1088 — 64 정렬). FLUX 권장 1024 멀티 변형.
  wf["4"] = {
    class_type: "EmptyLatentImage",
    inputs: { width: 1920, height: 1088, batch_size: 1 },
  };

  wf["13"] = {
    class_type: "LoraLoader",
    inputs: {
      model: ["1", 0],
      clip: ["1c", 0],
      lora_name: `${(item.lora_signature || "noir_webtoon_style").split("@")[0]}.safetensors`,
      strength_model: LORA_STRENGTH_DEFAULT,
      strength_clip: LORA_STRENGTH_DEFAULT,
    },
  };
  attachKSamplerAndDecode(wf, {
    modelOut: ["13", 0],
    positiveOut: ["2", 0],
    negativeOut: ["3", 0],
    seed: item.seed,
  });
  // 배경은 Alpha 없음 — VAEDecode 결과를 바로 저장
  wf["50"] = {
    class_type: "SaveImage",
    inputs: {
      images: ["31", 0],
      filename_prefix: toPosixPath(`asset_cache/${cacheKey}`),
    },
  };
  wf["99"] = {
    class_type: "WebhookOnComplete",
    inputs: {
      url: "{{N8N_RESUME_WEBHOOK}}",
      body_json: {
        resumeKey: "{{PROMPT_ID}}",
        file_path: `${projectRoot}/asset_cache/${cacheKey}.webp`,
      },
      images: ["50", 0],
    },
  };
  return wf;
}

// ── 7D: Foreground (text2img + Alpha, FaceID/IP-Adapter 비활성, zoom_rate 메타) ──
function buildForegroundWorkflow({ item, projectRoot, cacheKey }) {
  const model = MODEL_AUTO;
  const wf = commonHead({ model, prompt: item.description_render });
  wf["13"] = {
    class_type: "LoraLoader",
    inputs: {
      model: ["1", 0],
      clip: ["1c", 0],
      lora_name: `${(item.lora_signature || "noir_webtoon_style").split("@")[0]}.safetensors`,
      strength_model: LORA_STRENGTH_DEFAULT,
      strength_clip: LORA_STRENGTH_DEFAULT,
    },
  };
  attachKSamplerAndDecode(wf, {
    modelOut: ["13", 0],
    positiveOut: ["2", 0],
    negativeOut: ["3", 0],
    seed: item.seed,
  });
  attachLayerDiffusionAndSave(wf, { item, sourceNode: "31", cacheKey, projectRoot });
  return wf;
}

// ──────────────────────────────────────────────
// 단일 아이템 처리
// ──────────────────────────────────────────────

function processItem({ item, catalog, poseLibrary, projectRoot, sharedAssetsRoot }) {
  // ── V5.0: source_api 또는 solid_color 스킵 아이템은 ComfyUI 호출 없이 통과 ──
  if (item.skip_comfyui && (item.source_api || item.bg_style === "solid_color")) {
    return {
      ...item,
      prompt_id: uuid(),
      skip_comfyui: true,
      output_path: null,
      cache_key: null,
      vram_policy: null,
      controlnet_active: false,
      ip_adapter_unloaded: false,
      variant_chosen: null,
    };
  }

  const errors = [];
  if (!item.asset_type) errors.push("asset_type 누락");
  if (!item.scene_id) errors.push("scene_id 누락");
  if (!item.description_render) errors.push("description_render 누락");
  if (typeof item.seed !== "number") errors.push("seed 누락");
  if (errors.length > 0) {
    throw new Error(`[Node 7] 입력 검증 실패: ${errors.join(" / ")}`);
  }

  const cacheKey = computeCacheKey(item);
  const cacheDir = path.join(projectRoot, "asset_cache");
  fs.mkdirSync(cacheDir, { recursive: true });
  const cachedPath = path.join(cacheDir, `${cacheKey}.webp`);

  // L3 캐시 히트 — ComfyUI 호출 스킵
  if (fs.existsSync(cachedPath)) {
    return {
      ...item,
      prompt_id: uuid(),
      skip_comfyui: true,
      cached_path: toPosixPath(cachedPath),
      output_path: toPosixPath(cachedPath),
      cache_key: cacheKey,
      vram_policy: null,
      controlnet_active: false,
      ip_adapter_unloaded: false,
      variant_chosen: null,
    };
  }

  const promptId = uuid();
  const outputPath = toPosixPath(cachedPath);

  // ── 분기별 워크플로우 생성 ──
  if (item.asset_type === "character") {
    const found = findCharacterEntry(catalog, item.ref_image_id);
    if (!found) {
      throw new Error(`[Node 7] character 카탈로그 미매칭: ref_image_id=${item.ref_image_id}`);
    }

    const resolved = resolveCharacterVariant({
      characterEntry: found.entry,
      poseId: item.pose,
      poseLibrary,
    });

    const refImageAbsPath = path.resolve(sharedAssetsRoot, "..", resolved.variant.file_path);
    const controlled = item.pose && item.pose !== "auto";
    const posePngAbsPath = controlled
      ? path.resolve(sharedAssetsRoot, "..", `${POSES_DIR}/${item.pose}.png`)
      : null;

    if (controlled && posePngAbsPath && !fs.existsSync(posePngAbsPath)) {
      // 포즈 PNG 미존재 → auto 폴백 (운영 자산 미준비 상태 방어)
      const wf = buildCharacterWorkflow({
        item,
        variant: resolved.variant,
        controlled: false,
        posePngAbsPath: null,
        refImageAbsPath,
        projectRoot,
        cacheKey,
      });
      return {
        ...item,
        prompt_id: promptId,
        skip_comfyui: false,
        comfyui_payload: { client_id: promptId, prompt: wf },
        output_path: outputPath,
        cache_key: cacheKey,
        vram_policy: "Q5_K_M",
        controlnet_active: false,
        ip_adapter_unloaded: false,
        variant_chosen: {
          angle: resolved.angle,
          ref_image_id: resolved.variant.ref_image_id,
          file_path: resolved.variant.file_path,
          fallback_used: true,
          reason: `pose_png_missing:${item.pose}__auto_fallback`,
        },
      };
    }

    const wf = buildCharacterWorkflow({
      item,
      variant: resolved.variant,
      controlled,
      posePngAbsPath,
      refImageAbsPath,
      projectRoot,
      cacheKey,
    });

    return {
      ...item,
      prompt_id: promptId,
      skip_comfyui: false,
      comfyui_payload: { client_id: promptId, prompt: wf },
      output_path: outputPath,
      cache_key: cacheKey,
      vram_policy: controlled ? "Q4_K_M" : "Q5_K_M",
      controlnet_active: controlled,
      ip_adapter_unloaded: false,
      variant_chosen: {
        angle: resolved.angle,
        ref_image_id: resolved.variant.ref_image_id,
        file_path: resolved.variant.file_path,
        fallback_used: resolved.fallback_used,
        reason: resolved.reason,
      },
    };
  }

  if (item.asset_type === "prop") {
    const isNoneRef = !item.ref_image_id || item.ref_image_id === "none";
    let refImageAbsPath = null;
    if (!isNoneRef) {
      // catalog.props에서 file_path 조회
      const props = catalog.props || {};
      let propFilePath = null;
      for (const [key, p] of Object.entries(props)) {
        if (key.startsWith("_")) continue;
        if (p.ref_image_id === item.ref_image_id) {
          propFilePath = p.file_path;
          break;
        }
      }
      if (propFilePath) {
        refImageAbsPath = path.resolve(sharedAssetsRoot, "..", propFilePath);
        if (!fs.existsSync(refImageAbsPath)) refImageAbsPath = null;
      }
    }
    const wf = buildPropWorkflow({ item, refImageAbsPath, projectRoot, cacheKey });
    return {
      ...item,
      prompt_id: promptId,
      skip_comfyui: false,
      comfyui_payload: { client_id: promptId, prompt: wf },
      output_path: outputPath,
      cache_key: cacheKey,
      vram_policy: "Q5_K_M",
      controlnet_active: false,
      ip_adapter_unloaded: !refImageAbsPath, // none이면 IP-Adapter 모델 unload
      variant_chosen: null,
    };
  }

  if (item.asset_type === "background") {
    const wf = buildBackgroundWorkflow({ item, projectRoot, cacheKey });
    return {
      ...item,
      prompt_id: promptId,
      skip_comfyui: false,
      comfyui_payload: { client_id: promptId, prompt: wf },
      output_path: outputPath,
      cache_key: cacheKey,
      vram_policy: "Q5_K_M",
      controlnet_active: false,
      ip_adapter_unloaded: true, // IP-Adapter 노드 자체 제거
      variant_chosen: null,
    };
  }

  if (item.asset_type === "foreground") {
    const wf = buildForegroundWorkflow({ item, projectRoot, cacheKey });
    return {
      ...item,
      prompt_id: promptId,
      skip_comfyui: false,
      comfyui_payload: { client_id: promptId, prompt: wf },
      output_path: outputPath,
      cache_key: cacheKey,
      vram_policy: "Q5_K_M",
      controlnet_active: false,
      ip_adapter_unloaded: true,
      variant_chosen: null,
    };
  }

  throw new Error(`[Node 7] 알 수 없는 asset_type: ${item.asset_type}`);
}

// ──────────────────────────────────────────────
// Main (n8n Code Node entry)
// ──────────────────────────────────────────────

// 단위 테스트 모드: NODE7_TEST=1 환경변수 시 module.exports만 노출.
if (typeof $input === "undefined") {
  module.exports = {
    resolveCharacterVariant,
    tryFrontFallback,
    computeCacheKey,
    parseCharacterKeyFromRefId,
    findCharacterEntry,
    buildCharacterWorkflow,
    buildPropWorkflow,
    buildBackgroundWorkflow,
    buildForegroundWorkflow,
    processItem,
    constants: {
      MODEL_AUTO,
      MODEL_CONTROLLED,
      FACEID_WEIGHT,
      IP_ADAPTER_AUTO,
      IP_ADAPTER_CONTROLLED,
      CONTROLNET_OPENPOSE_STRENGTH,
      FALLBACK_VARIANT_KEY,
    },
  };
} else {
  const items = $input.all();
  if (!items || items.length === 0) throw new Error("[Node 7] 입력 아이템 없음");

  const node1 = $("Load Files").first().json;
  const PROJECT_ROOT = node1.project_root;
  if (!PROJECT_ROOT) throw new Error("[Node 7] project_root 누락");
  const SHARED_ASSETS_ROOT =
    node1.shared_assets_root || path.resolve(__dirname, "..", "..", "shared_assets");

  const catalogPath = path.resolve(SHARED_ASSETS_ROOT, "references_catalog.json");
  const poseLibPath = path.resolve(SHARED_ASSETS_ROOT, "pose_library.json");
  const catalog = readJsonSafe(catalogPath, "references_catalog.json");
  const poseLibrary = readJsonSafe(poseLibPath, "pose_library.json");

  const out = [];
  for (const it of items) {
    const j = it.json || {};
    const result = processItem({
      item: j,
      catalog,
      poseLibrary,
      projectRoot: PROJECT_ROOT,
      sharedAssetsRoot: SHARED_ASSETS_ROOT,
    });
    out.push({ json: result });
  }

  return out;
}
