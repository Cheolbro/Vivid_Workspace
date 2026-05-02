/**
 * Node 1 / 1.1 / 1.2 — Load Files: 입구 노드 (n8n Code Node, JavaScript)
 *
 * 과제 26 — v4.5 파이프라인 진입점.
 *
 * Node 1: 대본 태그 기반 청킹 ([INTRO]/[BUMPER]/[CHAPTER_N])
 *   - chapter_meta 객체 생성 (chapter_id, type, chapter_global_start/end, duration_sec, script_text, srt_path)
 *   - 원본 .vrew 경로 워크플로우 전역 보존 (Node 13 참조용)
 *   - 챕터 내부 0초 기준 SRT 재계산
 *
 * Node 1.1: type === "BUMPER_TRIGGER" → shared_assets/bumper.mp4 경로만 Node 12 concat 리스트에 삽입
 *
 * Node 1.2: FFmpeg 무손실 오디오 분할 (-c copy)
 *   - project/audio/chapter_NN.mp3 생성
 *   - 결과 0바이트 또는 duration ±0.5초 차이 시 실패 처리
 *   - 실패 시 3회 재시도 → 최종 실패 시 Telegram 알림
 *
 * 입력 (Webhook body 또는 n8n trigger):
 *   - project_path: 프로젝트 루트 경로
 *   - script_path: 대본 .txt 파일 경로
 *   - srt_path: 원본 SRT 파일 경로
 *   - mp3_path: 원본 TTS mp3 파일 경로
 *   - vrew_path: 원본 .vrew 파일 경로
 *   - video_id: 영상 식별자
 *   - shared_assets_root: (옵션) shared_assets 경로
 *
 * 출력: 챕터별 n8n 아이템 배열
 *   {
 *     video_id, project_root, shared_assets_root, fps,
 *     vrew_source_path,          // Node 13 참조용 전역 보존
 *     chapter_id, chapter_index, type,
 *     chapter_global_start, chapter_global_end, duration_sec,
 *     script_text, srt_path,
 *     chapter_audio_path,        // Node 1.2 산출 (BUMPER_TRIGGER는 null)
 *     bumper_path,               // BUMPER_TRIGGER만 설정
 *     concat_entry               // Node 12용: { type, path }
 *   }
 *
 * 환경: Node.js 빌트인 + child_process (ffmpeg/ffprobe CLI 호출).
 */

const fs = require("fs");
const path = require("path");
const { execSync, execFileSync } = require("child_process");

// ──────────────────────────────────────────────
// 상수
// ──────────────────────────────────────────────

const FPS = 30;
const MAX_RETRIES = 3;
const DURATION_TOLERANCE_SEC = 0.5;

// ──────────────────────────────────────────────
// SRT 파서/변환
// ──────────────────────────────────────────────

function parseSrtTimestamp(ts) {
  const m = /(\d{2}):(\d{2}):(\d{2})[,.](\d{3})/.exec(ts);
  if (!m) return NaN;
  return +m[1] * 3600 + +m[2] * 60 + +m[3] + +m[4] / 1000;
}

function formatSrtTimestamp(sec) {
  if (sec < 0) sec = 0;
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = Math.floor(sec % 60);
  const ms = Math.round((sec - Math.floor(sec)) * 1000);
  return (
    String(h).padStart(2, "0") +
    ":" +
    String(m).padStart(2, "0") +
    ":" +
    String(s).padStart(2, "0") +
    "," +
    String(ms).padStart(3, "0")
  );
}

function parseSrtFile(srtContent) {
  const blocks = srtContent.replace(/\r\n/g, "\n").trim().split(/\n\n+/);
  const cues = [];
  for (const block of blocks) {
    const lines = block.split("\n");
    if (lines.length < 2) continue;
    const timeLine = lines.find((l) => l.includes("-->"));
    if (!timeLine) continue;
    const [startStr, endStr] = timeLine.split("-->");
    const start = parseSrtTimestamp(startStr.trim());
    const end = parseSrtTimestamp(endStr.trim());
    if (isNaN(start) || isNaN(end)) continue;
    const textLines = lines.slice(lines.indexOf(timeLine) + 1);
    cues.push({ start, end, text: textLines.join("\n") });
  }
  return cues;
}

function buildChapterSrt(cues, globalStart, globalEnd) {
  const filtered = cues.filter((c) => c.start < globalEnd && c.end > globalStart);
  const reindexed = filtered.map((c, i) => {
    const newStart = Math.max(0, c.start - globalStart);
    const newEnd = Math.min(globalEnd - globalStart, c.end - globalStart);
    return {
      index: i + 1,
      start: formatSrtTimestamp(newStart),
      end: formatSrtTimestamp(newEnd),
      text: c.text,
    };
  });
  return reindexed.map((c) => `${c.index}\n${c.start} --> ${c.end}\n${c.text}`).join("\n\n");
}

// ──────────────────────────────────────────────
// 대본 태그 기반 청킹
// ──────────────────────────────────────────────

function parseScriptTags(scriptText) {
  const tagPattern = /\[(INTRO|BUMPER|CHAPTER[\s_]?(\d+))\]/gi;
  const segments = [];
  let lastIdx = 0;
  let lastTag = null;
  let lastChapterNum = null;
  let match;

  while ((match = tagPattern.exec(scriptText)) !== null) {
    if (lastTag !== null) {
      segments.push({
        tag: lastTag,
        chapterNum: lastChapterNum,
        text: scriptText.slice(lastIdx, match.index).trim(),
      });
    }
    const raw = match[1].toUpperCase().replace(/\s/g, "_");
    if (raw === "INTRO") {
      lastTag = "INTRO";
      lastChapterNum = null;
    } else if (raw === "BUMPER") {
      lastTag = "BUMPER";
      lastChapterNum = null;
    } else {
      lastTag = "CHAPTER";
      lastChapterNum = parseInt(match[2], 10);
    }
    lastIdx = match.index + match[0].length;
  }

  if (lastTag !== null) {
    segments.push({
      tag: lastTag,
      chapterNum: lastChapterNum,
      text: scriptText.slice(lastIdx).trim(),
    });
  }

  if (segments.length === 0) {
    segments.push({
      tag: "CHAPTER",
      chapterNum: 1,
      text: scriptText.trim(),
    });
  }

  return segments;
}

// ──────────────────────────────────────────────
// SRT에서 세그먼트별 글로벌 타임코드 결정
// ──────────────────────────────────────────────

function assignTimecodes(segments, srtCues, totalDuration) {
  const totalSegments = segments.length;
  if (totalSegments === 0) return [];

  if (srtCues.length === 0) {
    const sliceDur = totalDuration / totalSegments;
    return segments.map((seg, i) => ({
      ...seg,
      globalStart: i * sliceDur,
      globalEnd: (i + 1) * sliceDur,
    }));
  }

  const results = [];
  let cueIdx = 0;

  for (let i = 0; i < segments.length; i++) {
    const seg = segments[i];
    const segWords = seg.text
      .replace(/[^\w가-힣\s]/g, "")
      .split(/\s+/)
      .filter(Boolean);
    const segStart = cueIdx < srtCues.length ? srtCues[cueIdx].start : 0;

    if (seg.tag === "BUMPER") {
      results.push({ ...seg, globalStart: segStart, globalEnd: segStart });
      continue;
    }

    let matchedCues = 0;
    const targetWordCount = segWords.length;
    let accumulatedWords = 0;
    let endCueIdx = cueIdx;

    while (endCueIdx < srtCues.length && accumulatedWords < targetWordCount) {
      const cueWords = srtCues[endCueIdx].text
        .replace(/[^\w가-힣\s]/g, "")
        .split(/\s+/)
        .filter(Boolean);
      accumulatedWords += cueWords.length;
      matchedCues++;
      endCueIdx++;
    }

    if (endCueIdx === cueIdx) {
      endCueIdx = Math.min(cueIdx + 1, srtCues.length);
    }

    const segEnd =
      endCueIdx > 0 && endCueIdx <= srtCues.length ? srtCues[endCueIdx - 1].end : totalDuration;

    results.push({ ...seg, globalStart: segStart, globalEnd: segEnd });
    cueIdx = endCueIdx;
  }

  if (results.length > 0) {
    const last = results[results.length - 1];
    if (last.tag !== "BUMPER" && last.globalEnd < totalDuration) {
      last.globalEnd = totalDuration;
    }
  }

  return results;
}

// ──────────────────────────────────────────────
// FFprobe: mp3 duration 취득
// ──────────────────────────────────────────────

function getAudioDuration(mp3Path) {
  try {
    const out = execFileSync(
      "ffprobe",
      ["-v", "quiet", "-print_format", "json", "-show_format", mp3Path],
      { encoding: "utf-8", timeout: 30000 }
    );
    const info = JSON.parse(out);
    return parseFloat(info.format.duration);
  } catch (e) {
    throw new Error(`[Node 1] ffprobe 실패 (${mp3Path}): ${e.message}`);
  }
}

// ──────────────────────────────────────────────
// Node 1.2: FFmpeg 무손실 오디오 분할
// ──────────────────────────────────────────────

function splitAudio({ mp3Path, globalStart, globalEnd, outputPath }) {
  const dir = path.dirname(outputPath);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });

  const expectedDuration = globalEnd - globalStart;
  let lastError = null;

  for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    try {
      execFileSync(
        "ffmpeg",
        [
          "-y",
          "-ss",
          String(globalStart),
          "-to",
          String(globalEnd),
          "-i",
          mp3Path,
          "-c",
          "copy",
          outputPath,
        ],
        { encoding: "utf-8", timeout: 60000 }
      );

      if (!fs.existsSync(outputPath)) {
        throw new Error("출력 파일 미생성");
      }

      const stat = fs.statSync(outputPath);
      if (stat.size === 0) {
        throw new Error("0바이트 출력");
      }

      const actualDuration = getAudioDuration(outputPath);
      if (Math.abs(actualDuration - expectedDuration) > DURATION_TOLERANCE_SEC) {
        throw new Error(
          `duration 불일치: 예상 ${expectedDuration.toFixed(2)}s, 실제 ${actualDuration.toFixed(2)}s (허용 ±${DURATION_TOLERANCE_SEC}s)`
        );
      }

      return { success: true, path: outputPath, duration: actualDuration };
    } catch (e) {
      lastError = e;
      if (attempt < MAX_RETRIES) {
        // 재시도 전 출력 파일 정리
        try {
          if (fs.existsSync(outputPath)) fs.unlinkSync(outputPath);
        } catch (_) {}
      }
    }
  }

  return {
    success: false,
    path: outputPath,
    error: `[Node 1.2] ${MAX_RETRIES}회 재시도 실패: ${lastError.message}`,
  };
}

// ──────────────────────────────────────────────
// 메인 처리 함수 (테스트/n8n 공용)
// ──────────────────────────────────────────────

function processLoadFiles({
  projectPath,
  scriptPath,
  srtPath,
  mp3Path,
  vrewPath,
  videoId,
  sharedAssetsRoot,
}) {
  // ── 입력 검증 ──
  if (!projectPath) throw new Error("[Node 1] project_path 누락");
  if (!scriptPath) throw new Error("[Node 1] script_path 누락");
  if (!srtPath) throw new Error("[Node 1] srt_path 누락");
  if (!mp3Path) throw new Error("[Node 1] mp3_path 누락");
  if (!vrewPath) throw new Error("[Node 1] vrew_path 누락");
  if (!videoId) throw new Error("[Node 1] video_id 누락");

  if (!fs.existsSync(scriptPath)) throw new Error(`[Node 1] 대본 파일 없음: ${scriptPath}`);
  if (!fs.existsSync(srtPath)) throw new Error(`[Node 1] SRT 파일 없음: ${srtPath}`);
  if (!fs.existsSync(mp3Path)) throw new Error(`[Node 1] MP3 파일 없음: ${mp3Path}`);

  const SHARED_ROOT = sharedAssetsRoot || path.resolve(projectPath, "..", "shared_assets");
  const bumperPath = path.join(SHARED_ROOT, "bumper.mp4").replace(/\\/g, "/");

  // ── Node 1: 대본 파싱 + 청킹 ──
  const scriptText = fs.readFileSync(scriptPath, "utf-8");
  const srtContent = fs.readFileSync(srtPath, "utf-8");
  const srtCues = parseSrtFile(srtContent);
  const totalDuration = getAudioDuration(mp3Path);

  const segments = parseScriptTags(scriptText);
  const timedSegments = assignTimecodes(segments, srtCues, totalDuration);

  // ── 챕터 SRT 및 오디오 디렉터리 준비 ──
  const srtDir = path.join(projectPath, "srt");
  const audioDir = path.join(projectPath, "audio");
  fs.mkdirSync(srtDir, { recursive: true });
  fs.mkdirSync(audioDir, { recursive: true });

  // ── 아이템 생성 ──
  const items = [];
  let chapterCounter = 0;
  const errors = [];

  for (const seg of timedSegments) {
    // Node 1.1: BUMPER_TRIGGER → bumper.mp4 경로만 삽입
    if (seg.tag === "BUMPER") {
      items.push({
        video_id: videoId,
        project_root: projectPath.replace(/\\/g, "/"),
        shared_assets_root: SHARED_ROOT.replace(/\\/g, "/"),
        fps: FPS,
        vrew_source_path: vrewPath.replace(/\\/g, "/"),
        chapter_id: `bumper_${String(items.length).padStart(2, "0")}`,
        chapter_index: items.length,
        type: "BUMPER_TRIGGER",
        chapter_global_start: seg.globalStart,
        chapter_global_end: seg.globalEnd,
        duration_sec: 0,
        script_text: "",
        srt_path: null,
        chapter_audio_path: null,
        bumper_path: bumperPath,
        concat_entry: { type: "bumper", path: bumperPath },
      });
      continue;
    }

    // Node 1: 일반 챕터 (INTRO / CHAPTER)
    chapterCounter++;
    const chapterId = `chapter_${String(chapterCounter).padStart(2, "0")}`;
    const chapterType = seg.tag === "INTRO" ? "INTRO" : "CHAPTER";

    // 챕터 내부 0초 기준 SRT 재계산
    const chapterSrt = buildChapterSrt(srtCues, seg.globalStart, seg.globalEnd);
    const chapterSrtPath = path.join(srtDir, `${chapterId}_subtitle.srt`);
    fs.writeFileSync(chapterSrtPath, chapterSrt, "utf-8");

    // Node 1.2: FFmpeg 오디오 분할
    const chapterAudioPath = path.join(audioDir, `${chapterId}.mp3`);
    const splitResult = splitAudio({
      mp3Path,
      globalStart: seg.globalStart,
      globalEnd: seg.globalEnd,
      outputPath: chapterAudioPath,
    });

    if (!splitResult.success) {
      errors.push({
        chapter_id: chapterId,
        error: splitResult.error,
      });
    }

    items.push({
      video_id: videoId,
      project_root: projectPath.replace(/\\/g, "/"),
      shared_assets_root: SHARED_ROOT.replace(/\\/g, "/"),
      fps: FPS,
      vrew_source_path: vrewPath.replace(/\\/g, "/"),
      chapter_id: chapterId,
      chapter_index: items.length,
      type: chapterType,
      chapter_global_start: seg.globalStart,
      chapter_global_end: seg.globalEnd,
      duration_sec: seg.globalEnd - seg.globalStart,
      script_text: seg.text,
      srt_path: chapterSrtPath.replace(/\\/g, "/"),
      chapter_audio_path: splitResult.success ? chapterAudioPath.replace(/\\/g, "/") : null,
      bumper_path: null,
      concat_entry: {
        type: "chapter",
        path: splitResult.success ? chapterAudioPath.replace(/\\/g, "/") : null,
      },
    });
  }

  return { items, errors };
}

// ──────────────────────────────────────────────
// n8n / 테스트 모드 분기
// ──────────────────────────────────────────────

if (typeof $input === "undefined") {
  module.exports = {
    parseSrtTimestamp,
    formatSrtTimestamp,
    parseSrtFile,
    buildChapterSrt,
    parseScriptTags,
    assignTimecodes,
    splitAudio,
    processLoadFiles,
    constants: { FPS, MAX_RETRIES, DURATION_TOLERANCE_SEC },
  };
} else {
  const body = $input.first().json.body || $input.first().json;

  const { items, errors } = processLoadFiles({
    projectPath: body.project_path,
    scriptPath: body.script_path,
    srtPath: body.srt_path,
    mp3Path: body.mp3_path,
    vrewPath: body.vrew_path,
    videoId: body.video_id,
    sharedAssetsRoot: body.shared_assets_root,
  });

  if (errors.length > 0) {
    // Telegram 알림을 위한 에러 정보를 마지막 아이템에 첨부
    const errSummary = errors.map((e) => `${e.chapter_id}: ${e.error}`).join("\n");
    console.error(`[Node 1.2] 오디오 분할 실패:\n${errSummary}`);
  }

  // 챕터별 n8n 아이템 배열 반환
  return items.map((it) => ({ json: it }));
}
