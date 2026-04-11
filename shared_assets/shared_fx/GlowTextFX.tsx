import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, Easing } from "remotion";

/**
 * GlowTextFX — 박동하는 광채 텍스트 (All-in-One 시퀀스)
 *
 * [Step 1 · 0~15프레임] 텍스트 등장
 *   revealStyle='fade' : opacity 0 → 1
 *   revealStyle='blur' : opacity 0 → 1  +  blur 10px → 0px
 *
 * [Step 2 · 15프레임 이후] 광채 Pulsing 발동
 *   Math.sin 파형으로 text-shadow blur 반경이 커졌다 작아졌다 무한 반복.
 *   묵직한 경고/강조 분위기 유지 (눈부시지 않게 min 광채 유지).
 *
 * commonProps  : startFrame, durationFrames, x, y
 * specificProps: text, revealStyle, fontSize, color, glowColor, glowIntensity, cycleSeconds
 */

interface GlowTextFXProps {
  startFrame?: number;
  durationFrames?: number;
  x?: number;
  y?: number;
  text: string;
  revealStyle?: "fade" | "blur";
  fontSize?: string;
  color?: string;
  glowColor?: string;
  glowIntensity?: number; // 최대 blur 반경 (px)
  cycleSeconds?: number; // 박동 주기 (초)
}

const REVEAL_FRAMES = 15;
const EFFECT_DELAY = 15;

export const GlowTextFX: React.FC<GlowTextFXProps> = ({
  startFrame = 0,
  durationFrames = 180,
  x = 0,
  y = 0,
  text,
  revealStyle = "fade",
  fontSize = "80px",
  color = "#FFD700",
  glowColor = "#FFD700",
  glowIntensity = 22,
  cycleSeconds = 1.8,
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

  // ── Step 2: 광채 Pulsing 발동 ────────────────────────────────────
  // effectRel: EFFECT_DELAY 이전엔 0 고정 → 광채가 즉시 튀지 않음
  const effectRel = Math.max(0, rel - EFFECT_DELAY);
  const cycleFrames = fps * cycleSeconds;
  const phase = (effectRel % cycleFrames) / cycleFrames; // 0~1 루핑
  // sin 정규화: (sin(2π·phase - π/2) + 1) / 2 → 0~1
  // 0일 때(하강점) → 최소 광채(min 20%), 1일 때(상승점) → 최대 광채
  const sinNorm = (Math.sin(phase * Math.PI * 2 - Math.PI / 2) + 1) / 2;
  const glowFactor = effectRel === 0 ? 0 : 0.2 + sinNorm * 0.8; // 처음엔 0, 이후 0.2~1.0
  const blurRadius = glowFactor * glowIntensity;

  // 등장 직후 광채가 갑자기 튀지 않도록 0→full 을 8프레임에 걸쳐 램프업
  const glowRampUp = interpolate(effectRel, [0, 8], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const finalBlur = blurRadius * glowRampUp;

  // ── 퇴장 (마지막 10프레임) ──────────────────────────────────────
  const fadeOut = interpolate(rel, [durationFrames - 10, durationFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // 묵직한 레이어드 glow
  const textShadow = [
    `0 0 ${finalBlur}px ${glowColor}`,
    `0 0 ${finalBlur * 0.5}px ${glowColor}`,
    `0 0 ${finalBlur * 0.2}px ${glowColor}`,
    `2px 3px 10px rgba(0,0,0,0.75)`,
  ].join(", ");

  const cx = width / 2 + x;
  const cy = height / 2 + y;

  return (
    <div
      style={{
        position: "absolute",
        left: cx,
        top: cy,
        transform: "translate(-50%, -50%)",
        opacity: textOpacity * fadeOut,
        filter: blurPx > 0 ? `blur(${blurPx}px)` : undefined,
        fontSize,
        fontFamily: "sans-serif, 'Malgun Gothic', 'Apple SD Gothic Neo', 'Noto Sans KR'",
        fontWeight: "900",
        color,
        whiteSpace: "nowrap",
        letterSpacing: "0.04em",
        lineHeight: 1.2,
        textShadow,
        pointerEvents: "none",
      }}
    >
      {text}
    </div>
  );
};
