import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, Easing } from "remotion";

/**
 * PopupElement - 공통 팝업 이미지 컴포넌트
 * remotion_spec.md: 화면 중앙, 좌우 여백, object-fit: contain
 */

interface CommonProps {
  startFrame: number; // 노출 시작 프레임
  durationFrames: number; // 노출 지속 프레임 수
  x?: number; // 가로 위치 (px, 0=center)
  y?: number; // 세로 위치 (px, 0=center)
  width?: string | number; // 너비 (기본: 70%)
  maxHeight?: string | number; // 최대 높이 (기본: 70%)
  objectFit?: React.CSSProperties["objectFit"];
  style?: React.CSSProperties;
}

interface PopupElementProps extends CommonProps {
  src: string; // 이미지 경로 (public/ 기준)
  alt?: string;
}

export const PopupElement: React.FC<PopupElementProps> = ({
  src,
  alt = "",
  startFrame,
  durationFrames,
  x = 0,
  y = 0,
  width = "70%",
  maxHeight = "70%",
  objectFit = "contain",
  style: extraStyle,
}) => {
  const frame = useCurrentFrame();
  const { fps, width: videoW, height: videoH } = useVideoConfig();

  const relativeFrame = frame - startFrame;

  // 페이드인 (0~8 프레임) / 페이드아웃 (마지막 8 프레임)
  const fadeInFrames = Math.min(8, durationFrames * 0.15);
  const fadeOutStart = durationFrames - fadeInFrames;

  const opacity = interpolate(
    relativeFrame,
    [0, fadeInFrames, fadeOutStart, durationFrames],
    [0, 1, 1, 0],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.ease,
    }
  );

  // 팝업 스케일 애니메이션
  const popScale = interpolate(relativeFrame, [0, fadeInFrames], [0.85, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.back(1.5)),
  });

  if (relativeFrame < 0 || relativeFrame >= durationFrames) return null;

  return (
    <div
      style={{
        position: "absolute",
        left: videoW / 2 + x,
        top: videoH / 2 + y,
        width: "100%",
        height: "100%",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        opacity,
        transform: `translate(-50%, -50%) scale(${popScale})`,
        pointerEvents: "none",
        ...extraStyle,
      }}
    >
      <img
        src={src}
        alt={alt}
        style={{
          width,
          maxHeight,
          objectFit, // remotion_spec.md 기본 contain, 배경 시 cover 가능
          borderRadius: "12px",
          boxShadow: objectFit === "cover" ? "none" : "0 8px 32px rgba(0,0,0,0.5)",
        }}
      />
    </div>
  );
};
