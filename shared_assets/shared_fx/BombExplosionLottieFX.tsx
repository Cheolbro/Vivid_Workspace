import React from "react";
import { Lottie } from "@remotion/lottie";
import { useCurrentFrame, useVideoConfig, interpolate } from "remotion";
import animationData from "./assets/bomb.json";

/**
 * BombExplosionLottieFX — 폭탄 투하 및 폭발 — 위기, 충격, 폭락
 */

interface BombExplosionLottieFXProps {
  startFrame?: number;
  durationFrames?: number;
  x?: number;
  y?: number;
  scale?: number;
}

export const BombExplosionLottieFX: React.FC<BombExplosionLottieFXProps> = ({
  startFrame = 0,
  durationFrames = 150,
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
        width: 800,
        height: 800,
      }}
    >
      <Lottie animationData={{ animationData }} />
    </div>
  );
};
