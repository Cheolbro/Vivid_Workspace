import React from "react";
import { Lottie } from "@remotion/lottie";
import { useCurrentFrame, useVideoConfig, interpolate } from "remotion";
import animationData from "./assets/dollar.json";

/**
 * DollarLottieFX — 달러 기호 애니메이션
 */

interface DollarLottieFXProps {
  startFrame?: number;
  durationFrames?: number;
  x?: number;
  y?: number;
  scale?: number;
}

export const DollarLottieFX: React.FC<DollarLottieFXProps> = ({
  startFrame = 0,
  durationFrames = 120,
  x = 0,
  y = 0,
  scale = 1.0,
}) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();

  const rel = frame - startFrame;
  if (rel < 0 || rel >= durationFrames) return null;

  const opacity = interpolate(rel, [0, 10, durationFrames - 10, durationFrames], [0, 1, 1, 0]);

  const cx = width / 2 + x;
  const cy = height / 2 + y;

  return (
    <div
      style={{
        position: "absolute",
        left: cx,
        top: cy,
        transform: `translate(-50%, -50%) scale(${scale})`,
        opacity,
        pointerEvents: "none",
        width: 600,
        height: 600,
      }}
    >
      <Lottie animationData={{ animationData }} />
    </div>
  );
};
