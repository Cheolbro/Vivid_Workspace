import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";

/**
 * Generic3DAssetFX — 3D 스타일의 고퀄리티 정적 이미지를 애니메이션화하여 보여주는 컴포넌트
 *
 * commonProps: startFrame, durationFrames, x, y, scale
 * specificProps: assetName (이미지 파일명)
 */

interface Generic3DAssetFXProps {
  startFrame?: number;
  durationFrames?: number;
  x?: number;
  y?: number;
  scale?: number;
  assetName: string;
}

export const Generic3DAssetFX: React.FC<Generic3DAssetFXProps> = ({
  startFrame = 0,
  durationFrames = 90,
  x = 0,
  y = 0,
  scale = 1.0,
  assetName,
}) => {
  const frame = useCurrentFrame();
  const { width, height, fps } = useVideoConfig();

  const rel = frame - startFrame;
  if (rel < 0 || rel >= durationFrames) return null;

  // 1. Entrance Animation (Spring)
  const entrance = spring({
    frame: rel,
    fps,
    config: {
      damping: 12,
    },
  });

  // 2. Floating Animation (Sin wave)
  const floatY = Math.sin(rel / 10) * 20;

  // 3. Fade Out
  const opacity = interpolate(rel, [durationFrames - 15, durationFrames - 5], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const cx = width / 2 + x;
  const cy = height / 2 + y;

  // We assume assets are in /public/assets/ or bundled.
  // In our setup, they are in shared_assets/shared_fx/assets/
  // But for Remotion to access them, we usually import them or use staticFile.

  // Since we are in shared_fx, we can't easily dynamic import with a variable string in React.
  // So we'll use a mapping or require.

  const assetUrl = require(`./assets/${assetName}`);

  return (
    <div
      style={{
        position: "absolute",
        left: cx,
        top: cy,
        transform: `translate(-50%, -50%) scale(${entrance * scale}) translateY(${floatY}px)`,
        opacity,
        pointerEvents: "none",
      }}
    >
      <img
        src={assetUrl}
        alt={assetName}
        style={{
          width: "auto",
          height: "500px", // Default large size
          objectFit: "contain",
          filter: "drop-shadow(0 20px 40px rgba(0,0,0,0.3))",
        }}
      />
    </div>
  );
};
