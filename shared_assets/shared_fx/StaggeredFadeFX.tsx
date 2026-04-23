import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, Easing } from "remotion";

/**
 * StaggeredFadeFX — 부드럽게 시차를 두고 나타나는 텍스트 효과
 *
 * 고급스러운 명언이나 감성적인 대사에 적합한 우아한 연출입니다.
 *
 * commonProps: startFrame, durationFrames, x, y
 * specificProps: text, fontSize, color, staggerDelay
 */

interface StaggeredFadeFXProps {
  startFrame?: number;
  durationFrames?: number;
  x?: number;
  y?: number;
  text: string;
  fontSize?: string;
  color?: string;
  staggerDelay?: number; // 글자 간 딜레이 (프레임)
}

export const StaggeredFadeFX: React.FC<StaggeredFadeFXProps> = ({
  startFrame = 0,
  durationFrames = 120,
  x = 0,
  y = 0,
  text,
  fontSize = "80px",
  color = "#FFFFFF",
  staggerDelay = 2,
}) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();

  const rel = frame - startFrame;
  if (rel < 0 || rel >= durationFrames) return null;

  const cx = width / 2 + x;
  const cy = height / 2 + y;

  // 글자 단위로 분할 (공백 포함)
  const chars = text.split("");

  return (
    <div
      style={{
        position: "absolute",
        left: cx,
        top: cy,
        transform: "translate(-50%, -50%)",
        pointerEvents: "none",
        textAlign: "center",
        width: "90%",
        fontFamily: "sans-serif",
      }}
    >
      {chars.map((char, i) => {
        const charStart = i * staggerDelay;
        const opacity = interpolate(rel - charStart, [0, 15], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });

        const blur = interpolate(rel - charStart, [0, 15], [20, 0], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });

        const yOffset = interpolate(rel - charStart, [0, 20], [10, 0], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
          easing: Easing.out(Easing.quad),
        });

        return (
          <span
            key={i}
            style={{
              display: "inline-block",
              fontSize,
              fontWeight: "800",
              color,
              opacity,
              filter: `blur(${blur}px)`,
              transform: `translateY(${yOffset}px)`,
              whiteSpace: char === " " ? "pre" : "normal",
            }}
          >
            {char}
          </span>
        );
      })}
    </div>
  );
};
