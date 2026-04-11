import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring, Easing } from "remotion";

/**
 * HighlighterFX — 형광펜 강조 (All-in-One 시퀀스)
 *
 * [Step 1 · 0~15프레임] 텍스트 등장
 *   revealStyle='fade' : opacity 0 → 1
 *   revealStyle='blur' : opacity 0 → 1  +  blur 10px → 0px
 *
 * [Step 2 · 15프레임 이후] 형광펜 발동
 *   텍스트 뒤(z-index 아래)에서 노란 배경이 width 0% → 100% 로 뻗어 나감.
 *   spring Overshoot으로 살짝 튀어나왔다 안착하는 경쾌한 느낌.
 *
 * commonProps  : startFrame, durationFrames, x, y
 * specificProps: text, revealStyle, fontSize, highlightColor, opacity, textColor
 */

interface HighlighterFXProps {
  startFrame?: number;
  durationFrames?: number;
  x?: number;
  y?: number;
  text: string;
  revealStyle?: "fade" | "blur"; // 텍스트 등장 방식
  fontSize?: string;
  highlightColor?: string; // 형광펜 색상
  opacity?: number; // 형광펜 투명도 (0~1)
  textColor?: string;
}

const REVEAL_FRAMES = 15;
const EFFECT_DELAY = 15;

export const HighlighterFX: React.FC<HighlighterFXProps> = ({
  startFrame = 0,
  durationFrames = 120,
  x = 0,
  y = 0,
  text,
  revealStyle = "fade",
  fontSize = "72px",
  highlightColor = "#FFE500",
  opacity = 0.55,
  textColor = "#1A1A1A",
}) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();

  // text prop 누락 방어
  if (!text) return null;

  const rel = frame - startFrame;
  if (rel < 0 || rel >= durationFrames) return null;

  // ── Step 1: 텍스트 등장 ─────────────────────────────────────────
  const textOpacity = interpolate(rel, [0, REVEAL_FRAMES], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.quad),
  });

  const blurPx =
    revealStyle === "blur"
      ? interpolate(rel, [0, REVEAL_FRAMES], [10, 0], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
          easing: Easing.out(Easing.quad),
        })
      : 0;

  // ── Step 2: 형광펜 발동 ──────────────────────────────────────────
  // spring Overshoot: width가 살짝 튀어나왔다 안착하는 경쾌함
  const highlightSpring = spring({
    fps,
    frame: Math.max(0, rel - EFFECT_DELAY),
    config: { damping: 11, stiffness: 90, mass: 0.55 },
    durationInFrames: 35,
  });
  // 110% cap: Overshoot이 너무 크게 벌어지지 않게
  const highlightWidthPct = Math.min(highlightSpring * 100, 110);

  // ── 퇴장 (마지막 10프레임) ──────────────────────────────────────
  const fadeOut = interpolate(rel, [durationFrames - 10, durationFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const cx = width / 2 + x;
  const cy = height / 2 + y;

  return (
    <div
      style={{
        position: "absolute",
        left: cx,
        top: cy,
        transform: "translate(-50%, -50%)",
        opacity: fadeOut,
        pointerEvents: "none",
        display: "inline-block",
      }}
    >
      {/* 형광펜 배경 — 텍스트 뒤에 위치 (zIndex: 0) */}
      <div
        style={{
          position: "absolute",
          left: "-4px",
          top: "12%",
          height: "78%",
          width: `${highlightWidthPct}%`,
          background: highlightColor,
          opacity,
          borderRadius: "2px",
          zIndex: 0,
          overflow: "hidden",
          transformOrigin: "left center",
        }}
      />

      {/* 텍스트 본체 — 형광펜 위 (zIndex: 1) */}
      <span
        style={{
          position: "relative",
          zIndex: 1,
          display: "block",
          fontSize,
          fontFamily: "sans-serif, 'Malgun Gothic', 'Apple SD Gothic Neo', 'Noto Sans KR'",
          fontWeight: "900",
          color: textColor,
          opacity: textOpacity,
          filter: blurPx > 0 ? `blur(${blurPx}px)` : undefined,
          whiteSpace: "nowrap",
          letterSpacing: "0.02em",
          lineHeight: 1.25,
          textShadow: "1px 2px 8px rgba(0,0,0,0.15)",
          padding: "0 6px",
        }}
      >
        {text}
      </span>
    </div>
  );
};
