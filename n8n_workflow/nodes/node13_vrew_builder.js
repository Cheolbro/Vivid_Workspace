/**
 * Node 13 — Vrew Project Builder (n8n Code Node, JavaScript)
 *
 * 목적: Vrew에서 TTS/자막 편집이 끝난 원본 .vrew에 챕터별 MP4 비디오 트랙을 주입하고
 *      최종_hf_vN.vrew로 재패키징.
 *
 * 정식 레퍼런스: utils/backend_ext.py > assemble_vrew_hf() — 본 코드는 그 1:1 포팅.
 * 실제 Vrew project.json 스키마 검증: vrew_check/project.json
 *
 * 환경 요구사항:
 *   - n8n: NODE_FUNCTION_ALLOW_EXTERNAL=adm-zip
 *   - 시스템 PATH: ffprobe (FFmpeg 패키지)
 *
 * 입력 (n8n items[].json):
 *   - chapter_index: number  // 0-based
 *   - chapter_mp4_path: string  // Node 12 산출물 또는 챕터별 mp4 절대 경로
 *
 * 워크플로우 전역 (Node 1에서 보존):
 *   - $('Load Files').first().json.original_vrew_path
 *   - $('Load Files').first().json.asset_dir  (선택, 없으면 원본 .vrew의 부모 디렉토리 사용)
 *
 * 출력: [{ json: { final_vrew_path: string, injected_count: number } }]
 */

const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const { execFileSync } = require("child_process");
const AdmZip = require("adm-zip");

// ──────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────

/** 10자 영숫자 랜덤 (assemble_vrew_hf의 _random_track_id 등가) */
function randomTrackId() {
  const chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_";
  let out = "";
  const bytes = crypto.randomBytes(10);
  for (let i = 0; i < 10; i++) out += chars[bytes[i] % chars.length];
  return out;
}

/** UUIDv4 */
function uuid4() {
  return crypto.randomUUID();
}

/** ffprobe로 mp4 duration(초) 추출. 실패 시 fallback 반환. */
function getMp4Duration(mp4Path, fallbackSec) {
  try {
    const out = execFileSync(
      "ffprobe",
      [
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        mp4Path,
      ],
      { timeout: 10000, encoding: "utf-8" }
    );
    const v = parseFloat(out.trim());
    if (!Number.isFinite(v) || v <= 0) throw new Error("invalid duration");
    return v;
  } catch (e) {
    if (typeof fallbackSec === "number" && fallbackSec > 0) return fallbackSec;
    return 0.0;
  }
}

/** word.duration 누적으로 각 transcript clip의 [start, end) 초 산출 */
function computeClipTimings(clips) {
  const result = [];
  let t = 0.0;
  for (const cl of clips) {
    let dur = 0.0;
    for (const w of cl.words || []) dur += w.duration || 0.0;
    result.push({
      clip_id: cl.id,
      start: round4(t),
      end: round4(t + dur),
      duration: round4(dur),
    });
    t += dur;
  }
  return result;
}

/** files[]의 절대 경로 필드를 basename으로 변환 (다른 PC 호환성) */
function normalizeFilePaths(project) {
  const PATH_FIELDS = ["filePath", "localPath", "sourcePath", "path"];
  const toRelative = (val) => {
    if (typeof val !== "string") return val;
    const isAbs =
      (val.length >= 2 && val[1] === ":") || // Windows: C:\
      val.startsWith("/") || // Unix abs
      (val.includes("\\") && val.length > 3); // backslash
    if (isAbs) return path.basename(val);
    return val;
  };
  for (const fe of project.files || []) {
    if (!fe || typeof fe !== "object") continue;
    for (const f of PATH_FIELDS) {
      if (f in fe) fe[f] = toRelative(fe[f]);
    }
  }
  return project;
}

function round3(x) {
  return Math.round(x * 1000) / 1000;
}
function round4(x) {
  return Math.round(x * 10000) / 10000;
}

// ──────────────────────────────────────────────
// Main
// ──────────────────────────────────────────────

const items = $input.all();

// 입력 검증
if (!items || items.length === 0) {
  throw new Error(
    "[Node 13] 입력 아이템이 없습니다. Node 12에서 챕터별 MP4 경로를 전달해야 합니다."
  );
}

// 워크플로우 전역에서 원본 vrew 경로 읽기 (Node 1 export)
const node1 = $("Load Files").first().json;
const originalVrewPath = node1.original_vrew_path;
if (!originalVrewPath || !fs.existsSync(originalVrewPath)) {
  throw new Error(`[Node 13] 원본 .vrew를 찾을 수 없습니다: ${originalVrewPath}`);
}
const assetDir = node1.asset_dir || path.dirname(originalVrewPath);
let fps = node1.fps || 30;

// 과제 23: project_config.json baseline.target_fps 강제 적용
try {
  const cfgPath = path.join(path.dirname(originalVrewPath), "..", "project_config.json");
  if (fs.existsSync(cfgPath)) {
    const cfg = JSON.parse(fs.readFileSync(cfgPath, "utf-8"));
    if (cfg.baseline && typeof cfg.baseline.target_fps === "number") {
      fps = cfg.baseline.target_fps;
    }
  }
} catch (e) {
  // config 읽기 실패 시 기본값 유지
}

// 챕터 mp4 목록 정렬 (chapter_index ASC, 없으면 입력 순)
const chapters = items
  .map((it) => it.json)
  .filter((j) => j && j.chapter_mp4_path && fs.existsSync(j.chapter_mp4_path))
  .sort((a, b) => (a.chapter_index ?? 0) - (b.chapter_index ?? 0));

if (chapters.length === 0) {
  throw new Error("[Node 13] 유효한 chapter_mp4_path가 하나도 없습니다.");
}

// 출력 파일 자동 버저닝: 최종_hf_v0.vrew, 최종_hf_v1.vrew, ...
let v = 0;
let outPath;
while (true) {
  outPath = path.join(assetDir, `최종_hf_v${v}.vrew`);
  if (!fs.existsSync(outPath)) break;
  v++;
}

// 과제 24: 디스크 임시 추출 (인메모리 ZIP 금지 — RAM 폭발 방어)
const tmpDir = path.join(assetDir, `_vrew_tmp_${Date.now()}`);
fs.mkdirSync(tmpDir, { recursive: true });

try {
  const srcZip = new AdmZip(originalVrewPath);
  srcZip.extractAllTo(tmpDir, true);
} catch (e) {
  throw new Error(`[Node 13] 원본 .vrew 언팩 실패: ${e.message}`);
}

const projectJsonPath = path.join(tmpDir, "project.json");
if (!fs.existsSync(projectJsonPath)) {
  throw new Error("[Node 13] project.json이 .vrew 내부에 없습니다.");
}
let project;
try {
  project = JSON.parse(fs.readFileSync(projectJsonPath, "utf-8"));
} catch (e) {
  throw new Error(`[Node 13] project.json 파싱 실패: ${e.message}`);
}

// 기존 files[] 절대 경로 정규화
project = normalizeFilePaths(project);

// 클립 타이밍 산출
const clips = (project.transcript && project.transcript.clips) || [];
const clipTimings = computeClipTimings(clips);
const clipById = Object.fromEntries(clips.map((c) => [c.id, c]));

// 신규 등록 작업
project.props = project.props || {};
project.props.tracks = project.props.tracks || {};
project.props.assets = project.props.assets || {};
project.files = project.files || [];

const newMediaMap = {}; // mediaId → mp4 absolute path
let cumulativeSec = 0.0;

for (const ch of chapters) {
  const mp4Path = ch.chapter_mp4_path;
  const fallbackDur = ch.duration_sec || 0.0;
  const durSec = getMp4Duration(mp4Path, fallbackDur);
  const startSec = cumulativeSec;
  cumulativeSec += durSec;

  const mediaId = uuid4();
  const trackId = randomTrackId();
  const assetId = uuid4();

  // clip 매칭: startSec ∈ [clip.start, clip.end)
  let targetClipId = null;
  for (const ct of clipTimings) {
    if (ct.start <= startSec && startSec < ct.end) {
      targetClipId = ct.clip_id;
      break;
    }
  }
  if (targetClipId === null && clipTimings.length > 0) {
    targetClipId = clipTimings[clipTimings.length - 1].clip_id;
  }

  // files[] 등록
  project.files.push({
    version: 1,
    mediaId: mediaId,
    sourceOrigin: "USER",
    fileSize: fs.statSync(mp4Path).size,
    name: `${mediaId}.mp4`,
    type: "AVMedia",
    videoAudioMetaInfo: {
      duration: round3(durSec),
      videoInfo: { codec: "h264", frameRate: fps },
    },
    sourceFileType: "VIDEO_ONLY",
    fileLocation: "IN_MEMORY",
  });

  // tracks{} 등록
  project.props.tracks[trackId] = {
    trackId: trackId,
    mediaId: mediaId,
    xPos: 0.0,
    yPos: 0.0,
    height: 1.0,
    width: 1.0,
    rotation: 0,
    zIndex: 10,
    type: "video",
    sourceIn: 0,
    sourceOut: round3(durSec),
    hasAlphaChannel: false,
    isTrimmable: true,
    editInfo: {},
    fillType: "cut",
  };

  // assets{} 등록
  project.props.assets[assetId] = {
    trackIds: [trackId],
    role: "sub",
  };

  // clip.assetIds 연결
  if (targetClipId && clipById[targetClipId]) {
    clipById[targetClipId].assetIds = clipById[targetClipId].assetIds || [];
    clipById[targetClipId].assetIds.push(assetId);
  }

  newMediaMap[mediaId] = mp4Path;
}

// 디스크에서 project.json 갱신 + media/ mp4 복사 후 재패키징
fs.writeFileSync(projectJsonPath, JSON.stringify(project), "utf-8");

const mediaDir = path.join(tmpDir, "media");
fs.mkdirSync(mediaDir, { recursive: true });
for (const [mediaId, mp4Path] of Object.entries(newMediaMap)) {
  fs.copyFileSync(mp4Path, path.join(mediaDir, `${mediaId}.mp4`));
}

// 임시 디렉토리 → .vrew ZIP 재패키징
const outZip = new AdmZip();
(function addDirRecursive(dir, zipPrefix) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const fullPath = path.join(dir, entry.name);
    const zipPath = zipPrefix ? `${zipPrefix}/${entry.name}` : entry.name;
    if (entry.isDirectory()) {
      addDirRecursive(fullPath, zipPath);
    } else {
      outZip.addLocalFile(fullPath, zipPrefix || "");
    }
  }
})(tmpDir, "");
outZip.writeZip(outPath);

// 임시 디렉토리 정리
fs.rmSync(tmpDir, { recursive: true, force: true });

return [
  {
    json: {
      final_vrew_path: outPath,
      injected_count: chapters.length,
      total_duration_sec: round3(cumulativeSec),
      output_version: v,
    },
  },
];
