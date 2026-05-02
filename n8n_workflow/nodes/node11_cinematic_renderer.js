/**
 * Node 11 — Cinematic Renderer (n8n Code Node, JavaScript)
 *
 * 목적: Node 10이 생성한 chapter_NN.html을 HyperFrames CLI로 MP4 영상으로 렌더링.
 *
 * 과제 24 정책:
 *   - boil 필터: template.html에서 RENDER_MODE일 때 자동 비활성 (코드 변경 완료)
 *   - Stateless 렌더링: 챕터마다 Chromium 인스턴스 재시작 (EF-3)
 *   - Stop & Resume: mp4 존재 + HTML SHA256 해시 검사 → 변경 없으면 스킵 (§1.3 Node 11 (6))
 *   - 렌더 실패 시 최대 2회 재시도
 *
 * 입력 (n8n items[].json — Node 10 출력):
 *   - chapter_id: string
 *   - html_path: string (chapter_NN.html 절대 경로)
 *   - duration_sec: number
 *
 * 워크플로우 전역 (Node 1):
 *   - $('Load Files').first().json.project_root
 *   - $('Load Files').first().json.video_id
 *
 * 출력: [{ json: { chapter_id, chapter_mp4_path, skipped, duration_sec } }]
 *
 * 환경: Node.js 빌트인 (fs / path / crypto / child_process). HyperFrames CLI 필수.
 */

const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const { execFileSync } = require("child_process");

// ──────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────

function sha256File(filePath) {
  const data = fs.readFileSync(filePath);
  return crypto.createHash("sha256").update(data).digest("hex");
}

function readMetaFile(metaPath) {
  try {
    if (!fs.existsSync(metaPath)) return null;
    return JSON.parse(fs.readFileSync(metaPath, "utf-8"));
  } catch (e) {
    return null;
  }
}

function writeMetaFile(metaPath, htmlHash, hfVersion) {
  const meta = {
    html_sha256: htmlHash,
    rendered_at: new Date().toISOString(),
    hyperframes_version: hfVersion || "unknown",
  };
  fs.writeFileSync(metaPath, JSON.stringify(meta, null, 2), "utf-8");
}

function findHyperframesBin(projectRoot) {
  const candidates = [
    path.join(projectRoot, "hyperframes", "node_modules", ".bin", "hyperframes.cmd"),
    path.join(projectRoot, "hyperframes", "node_modules", ".bin", "hyperframes"),
    path.join(
      projectRoot,
      "..",
      "Project_templete",
      "hyperframes",
      "node_modules",
      ".bin",
      "hyperframes.cmd"
    ),
    path.join(
      projectRoot,
      "..",
      "Project_templete",
      "hyperframes",
      "node_modules",
      ".bin",
      "hyperframes"
    ),
  ];
  for (const c of candidates) {
    if (fs.existsSync(c)) return c;
  }
  return "hyperframes"; // PATH 폴백
}

function getHyperframesVersion(bin) {
  try {
    return execFileSync(bin, ["--version"], { timeout: 5000, encoding: "utf-8" }).trim();
  } catch (e) {
    return "unknown";
  }
}

// ──────────────────────────────────────────────
// Main
// ──────────────────────────────────────────────

const MAX_RETRIES = 2;
const items = $input.all();
const node1 = $("Load Files").first().json;
const PROJECT_ROOT = node1.project_root;

if (!PROJECT_ROOT) throw new Error("[Node 11] project_root 누락");

const renderDir = path.join(PROJECT_ROOT, "render");
fs.mkdirSync(renderDir, { recursive: true });

const hfBin = findHyperframesBin(PROJECT_ROOT);
const hfVersion = getHyperframesVersion(hfBin);

const output = [];

for (const it of items) {
  const item = it.json;
  const chapterId = item.chapter_id;
  const htmlPath = item.html_path;

  if (!htmlPath || !fs.existsSync(htmlPath)) {
    throw new Error(`[Node 11] HTML 파일 없음: ${htmlPath}`);
  }

  const mp4Path = path.join(renderDir, `${chapterId}.mp4`);
  const metaPath = `${mp4Path}.meta`;

  // Stop & Resume 검사
  const htmlHash = sha256File(htmlPath);
  const existingMeta = readMetaFile(metaPath);

  if (
    fs.existsSync(mp4Path) &&
    fs.statSync(mp4Path).size > 0 &&
    existingMeta &&
    existingMeta.html_sha256 === htmlHash
  ) {
    // 입력 변경 없음 — 스킵
    output.push({
      json: {
        chapter_id: chapterId,
        chapter_mp4_path: mp4Path,
        skipped: true,
        duration_sec: item.duration_sec || 0,
      },
    });
    continue;
  }

  // 렌더링 실행 (최대 2회 재시도)
  let success = false;
  let lastError = null;

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    try {
      execFileSync(hfBin, ["render", htmlPath, "--output", mp4Path], {
        timeout: 600000, // 10분 타임아웃 (챕터당)
        encoding: "utf-8",
        stdio: "pipe",
      });

      if (fs.existsSync(mp4Path) && fs.statSync(mp4Path).size > 0) {
        success = true;
        break;
      }
    } catch (e) {
      lastError = e.message || String(e);
    }
  }

  if (!success) {
    console.error(`[Node 11] 렌더 실패 (${chapterId}): ${lastError}`);
    output.push({
      json: {
        chapter_id: chapterId,
        chapter_mp4_path: null,
        skipped: false,
        render_error: lastError,
        duration_sec: item.duration_sec || 0,
      },
    });
    continue;
  }

  // 성공 — meta 기록
  writeMetaFile(metaPath, htmlHash, hfVersion);

  output.push({
    json: {
      chapter_id: chapterId,
      chapter_mp4_path: mp4Path,
      skipped: false,
      duration_sec: item.duration_sec || 0,
    },
  });
}

return output;
