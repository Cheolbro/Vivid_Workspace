import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring, Easing } from "remotion";

/**
 * NeonPulseGlowFX — 맥동하는 네온 광채 텍스트 효과
 *
 * 시선을 집중시켜야 하는 경고, 공지, 할인 등의 키워드에 적합한 화려한 효과입니다.
 *
 * commonProps: startFrame, durationFrames, x, y
 * specificProps: text, fontSize, neonColor, pulseSpeed
 */

interface NeonPulseGlowFXProps {
  startFrame?: number;
  durationFrames?: number;
  x?: number;
  y?: number;
  text: string;
  fontSize?: string;
  neonColor?: string;
  pulseSpeed?: number;
}

export const NeonPulseGlowFX: React.FC<NeonPulseGlowFXProps> = ({
  startFrame = 0,
  durationFrames = 120,
  x = 0,
  y = 0,
  text,
  fontSize = "95px",
  neonColor = "#FF00FF", // Magenta Neon
  pulseSpeed = 1.0,
}) => {
  const frame = useCurrentFrame();
  const { width, height, fps } = useVideoConfig();

  const rel = frame - startFrame;
  if (rel < 0 || rel >= durationFrames) return null;

  // 맥동 효과 (Sine Wave)
  const pulse = (Math.sin((rel / fps) * Math.PI * 2 * pulseSpeed) + 1) / 2; // 0 ~ 1

  const glowSize = interpolate(pulse, [0, 1], [5, 25]);
  const opacity = interpolate(rel, [0, 10], [0, 1]);
  const scale = interpolate(pulse, [0, 1], [1, 1.05]);

  const cx = width / 2 + x;
  const cy = height / 2 + y;

  return (
    <div
      style={{
        position: "absolute",
        left: cx,
        top: cy,
        transform: "translate(-50%, -50%)",
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          fontSize,
          fontWeight: "900",
          color: "#FFFFFF",
          opacity,
          transform: `scale(${scale})`,
          fontFamily: "'Segoe UI', Roboto, Helvetica, Arial, sans-serif",
          textAlign: "center",
          textShadow: `
            0 0 ${glowSize}px ${neonColor},
            0 0 ${glowSize * 2}px ${neonColor},
            0 0 ${glowSize * 3}px ${neonColor}
          `,
          letterSpacing: "2px",
          whiteSpace: "nowrap",
        }}
      >
        {text}
      </div>
    </div>
  );
};
