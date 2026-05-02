/**
 * Node 12 — Final Merge & Cleanup (n8n Code Node, JavaScript)
 *
 * 목적: 챕터별 MP4를 FFmpeg concat으로 병합, 최종 영상 생성.
 *
 * 과제 24 정책 (EF-4 + BN-2):
 *   - Intel Quick Sync h264_qsv 하드웨어 가속 인코딩
 *   - CRF 19~21 영상별 무작위 (절대 화질 방어 + 양산 검열 회피)
 *   - maxrate 14M, bufsize 28M
 *   - GOP size 90~150 챕터별 무작위
 *   - 1920x1080, 30fps, H.264 규격 강제
 *
 * 입력 (n8n items[].json — Node 11 출력):
 *   - chapter_id: string
 *   - chapter_mp4_path: string
 *   - duration_sec: number
 *
 * 워크플로우 전역 (Node 1):
 *   - $('Load Files').first().json.project_root
 *   - $('Load Files').first().json.video_id
 *
 * 출력: [{ json: { final_mp4_path, total_duration_sec, chapter_count } }]
 *
 * 환경: Node.js 빌트인 (fs / path / crypto / child_process). FFmpeg 필수.
 */

const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const { execFileSync } = require("child_process");

// ──────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────

function randomInt(min, max) {
  const buf = crypto.randomBytes(4);
  const val = buf.readUInt32BE(0);
  return min + (val % (max - min + 1));
}

// ──────────────────────────────────────────────
// Main
// ──────────────────────────────────────────────

const items = $input.all();
const node1 = $("Load Files").first().json;
const PROJECT_ROOT = node1.project_root;
const VIDEO_ID = node1.video_id;

if (!PROJECT_ROOT) throw new Error("[Node 12] project_root 누락");

// project_config.json에서 인코딩 정책 로드
let encodingConfig = {
  crf_min: 19,
  crf_max: 21,
  maxrate_mbps: 14,
  bufsize_mbps: 28,
  gop_min: 90,
  gop_max: 150,
  hw_accel: "h264_qsv",
};
let targetFps = 30;

try {
  const configPath = path.join(PROJECT_ROOT, "..", "project_config.json");
  if (fs.existsSync(configPath)) {
    const config = JSON.parse(fs.readFileSync(configPath, "utf-8"));
    if (config.baseline) {
      if (config.baseline.encoding) {
        Object.assign(encodingConfig, config.baseline.encoding);
      }
      if (typeof config.baseline.target_fps === "number") {
        targetFps = config.baseline.target_fps;
      }
    }
  }
} catch (e) {
  // config 읽기 실패 시 기본값 유지
}

// 챕터 정렬 (chapter_index 또는 chapter_id 기준)
const chapters = items
  .map((it) => it.json)
  .filter((j) => j && j.chapter_mp4_path && fs.existsSync(j.chapter_mp4_path))
  .sort((a, b) => {
    const ai = a.chapter_index ?? (parseInt((a.chapter_id || "").replace(/\D/g, "")) || 0);
    const bi = b.chapter_index ?? (parseInt((b.chapter_id || "").replace(/\D/g, "")) || 0);
    return ai - bi;
  });

if (chapters.length === 0) {
  throw new Error("[Node 12] 유효한 chapter_mp4_path가 없습니다.");
}

const renderDir = path.join(PROJECT_ROOT, "render");
fs.mkdirSync(renderDir, { recursive: true });

// FFmpeg concat 리스트 생성
const concatListPath = path.join(renderDir, "concat_list.txt");
const concatLines = chapters.map((ch) => `file '${ch.chapter_mp4_path.replace(/'/g, "'\\''")}'`);
fs.writeFileSync(concatListPath, concatLines.join("\n"), "utf-8");

// 인코딩 파라미터 무작위 (EF-4)
const crf = randomInt(encodingConfig.crf_min, encodingConfig.crf_max);
const gop = randomInt(encodingConfig.gop_min, encodingConfig.gop_max);
const maxrate = `${encodingConfig.maxrate_mbps}M`;
const bufsize = `${encodingConfig.bufsize_mbps}M`;
const codec = encodingConfig.hw_accel || "h264_qsv";

const finalMp4 = path.join(renderDir, `${VIDEO_ID}_final.mp4`);

// FFmpeg 병합 + 재인코딩
const ffmpegArgs = [
  "-f",
  "concat",
  "-safe",
  "0",
  "-i",
  concatListPath,
  "-c:v",
  codec,
  "-global_quality",
  String(crf),
  "-maxrate",
  maxrate,
  "-bufsize",
  bufsize,
  "-g",
  String(gop),
  "-r",
  String(targetFps),
  "-s",
  "1920x1080",
  "-an", // 오디오 없음 (Vrew가 TTS 트랙 담당)
  "-y",
  finalMp4,
];

try {
  execFileSync("ffmpeg", ffmpegArgs, {
    timeout: 3600000, // 1시간 타임아웃
    encoding: "utf-8",
    stdio: "pipe",
  });
} catch (e) {
  // h264_qsv 실패 시 소프트웨어 인코더 폴백
  if (codec === "h264_qsv") {
    const fallbackArgs = ffmpegArgs.map((a) => (a === "h264_qsv" ? "libx264" : a));
    // libx264는 -global_quality 대신 -crf 사용
    const gqIdx = fallbackArgs.indexOf("-global_quality");
    if (gqIdx !== -1) {
      fallbackArgs[gqIdx] = "-crf";
    }
    execFileSync("ffmpeg", fallbackArgs, {
      timeout: 3600000,
      encoding: "utf-8",
      stdio: "pipe",
    });
  } else {
    throw new Error(`[Node 12] FFmpeg 병합 실패: ${e.message}`);
  }
}

if (!fs.existsSync(finalMp4) || fs.statSync(finalMp4).size === 0) {
  throw new Error("[Node 12] 최종 MP4 생성 실패");
}

// 임시 concat 리스트 정리
try {
  fs.unlinkSync(concatListPath);
} catch (e) {
  // 무시
}

const totalDuration = chapters.reduce((sum, ch) => sum + (ch.duration_sec || 0), 0);

return [
  {
    json: {
      final_mp4_path: finalMp4,
      total_duration_sec: Math.round(totalDuration * 1000) / 1000,
      chapter_count: chapters.length,
      encoding: { codec, crf, gop, maxrate, bufsize, fps: targetFps },
    },
  },
];
