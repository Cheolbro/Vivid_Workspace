import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, random } from "remotion";

interface Props {
  startFrame?: number;
  durationFrames?: number;
  particleCount?: number;
  color?: string;
  speed?: number;
  size?: number;
}
export const MoneyRainFX: React.FC<Props> = ({
  startFrame = 0,
  durationFrames = 60,
  particleCount = 30,
  color = "#FFD700",
  speed = 5.0,
  size = 24,
}) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const rel = frame - startFrame;
  if (rel < 0 || rel >= durationFrames) return null;
  const opacity = interpolate(rel, [0, 8, durationFrames - 8, durationFrames], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <div style={{ position: "absolute", inset: 0, overflow: "hidden", opacity }}>
      {Array.from({ length: particleCount }).map((_, i) => {
        const x = random(`x${i}`) * width;
        const y = (random(`y${i}`) * height + rel * speed * (0.7 + random(`s${i}`) * 0.6)) % height;
        const rot = (rel * 3 + random(`r${i}`) * 360) % 360;
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: x,
              top: y,
              width: size,
              height: size,
              borderRadius: "50%",
              backgroundColor: color,
              transform: `rotate(${rot}deg)`,
              boxShadow: `0 0 ${size / 3}px ${color}`,
            }}
          >
            <span style={{ fontSize: size * 0.65, lineHeight: `${size}px` }}>💰</span>
          </div>
        );
      })}
    </div>
  );
};
