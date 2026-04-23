import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring, Easing } from "remotion";

/**
 * BoldImpactSlideFX — 바닥에서 강하게 튀어 올라오는 묵직한 텍스트 효과
 *
 * 강력한 결론이나 충격적인 사실을 전달할 때 시각적 무게감을 줍니다.
 *
 * commonProps: startFrame, durationFrames, x, y
 * specificProps: text, fontSize, color, impactPower
 */

interface BoldImpactSlideFXProps {
  startFrame?: number;
  durationFrames?: number;
  x?: number;
  y?: number;
  text: string;
  fontSize?: string;
  color?: string;
  impactPower?: number;
}

export const BoldImpactSlideFX: React.FC<BoldImpactSlideFXProps> = ({
  startFrame = 0,
  durationFrames = 80,
  x = 0,
  y = 0,
  text,
  fontSize = "120px",
  color = "#FFFFFF",
  impactPower = 1.0,
}) => {
  const frame = useCurrentFrame();
  const { width, height, fps } = useVideoConfig();

  const rel = frame - startFrame;
  if (rel < 0 || rel >= durationFrames) return null;

  // 강력한 바운스를 위한 스프링 설정
  const spr = spring({
    frame: rel,
    fps,
    config: { damping: 10, stiffness: 150, mass: 2 },
  });

  const translateY = interpolate(spr, [0, 1], [300 * impactPower, 0]);
  const scale = interpolate(spr, [0, 0.2, 1], [0.5, 1.1, 1]);
  const opacity = interpolate(rel, [0, 10], [0, 1]);

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
        textAlign: "center",
      }}
    >
      <div
        style={{
          fontSize,
          fontWeight: "1000", // 초강력 굵기
          color,
          opacity,
          transform: `translateY(${translateY}px) scale(${scale})`,
          fontFamily: "Impact, sans-serif",
          letterSpacing: "-2px",
          textShadow: "0 10px 30px rgba(0,0,0,0.5)",
          whiteSpace: "nowrap",
        }}
      >
        {text}
      </div>
    </div>
  );
};
