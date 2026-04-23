import React from "react";
import { Img, staticFile, useCurrentFrame, interpolate, Easing } from "remotion";

/**
 * ImageElement - Schema v2.0 Image Background Component
 *
 * Supports kenBurns properties for smooth pan/zoom effects.
 */

interface KenBurnsProps {
  startScale?: number;
  endScale?: number;
  startX?: number;
  endX?: number;
  startY?: number;
  endY?: number;
  easing?: "easeInOutSine" | "linear" | "easeOutQuad" | string;
}

interface ImageElementProps {
  src: string;
  startFrame: number;
  durationFrames: number;
  width?: string | number;
  height?: string | number;
  kenBurns?: KenBurnsProps;
}

export const ImageElement: React.FC<ImageElementProps> = ({
  src,
  startFrame,
  durationFrames,
  width = "100%",
  height = "100%",
  kenBurns,
}) => {
  const frame = useCurrentFrame();
  const rel = frame - startFrame;

  if (rel < 0 || rel >= durationFrames) return null;

  // Default kenBurns values
  const kb = {
    startScale: 1.0,
    endScale: 1.0,
    startX: 0,
    endX: 0,
    startY: 0,
    endY: 0,
    easing: "linear",
    ...kenBurns,
  };

  const getEasing = (easingName: string) => {
    switch (easingName) {
      case "easeInOutSine":
        return Easing.inOut(Easing.sin);
      case "easeOutQuad":
        return Easing.out(Easing.quad);
      case "linear":
      default:
        return Easing.linear;
    }
  };

  const easingFn = getEasing(kb.easing);

  const scale = interpolate(rel, [0, durationFrames], [kb.startScale, kb.endScale], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: easingFn,
  });

  const translateX = interpolate(rel, [0, durationFrames], [kb.startX, kb.endX], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: easingFn,
  });

  const translateY = interpolate(rel, [0, durationFrames], [kb.startY, kb.endY], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: easingFn,
  });

  return (
    <div
      style={{
        position: "absolute",
        top: 0,
        left: 0,
        width: "100%",
        height: "100%",
        overflow: "hidden",
      }}
    >
      <Img
        src={staticFile(src)}
        style={{
          width,
          height,
          objectFit: "cover",
          transform: `translate(${translateX}px, ${translateY}px) scale(${scale})`,
          opacity: 0.85, // Same as the original hardcoded opacity in Slide
        }}
      />
    </div>
  );
};
