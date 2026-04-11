import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, Easing } from "remotion";

/**
 * PopupElement - 공통 팝업 이미지 컴포넌트
 * remotion_spec.md: 화면 중앙, 좌우 여백, object-fit: contain
 */

interface CommonProps {
  startFrame: number; // 노출 시작 프레임
  durationFrames: number; // 노출 지속 프레임 수
  x?: string; // 가로 위치 (CSS, 기본: center)
  y?: string; // 세로 위치 (CSS, 기본: center)
  width?: string; // 너비 (기본: 70%)
  maxHeight?: string; // 최대 높이 (기본: 70%)
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
  width = "70%",
  maxHeight = "70%",
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

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
  const scale = interpolate(relativeFrame, [0, fadeInFrames], [0.85, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.back(1.5)),
  });

  if (relativeFrame < 0 || relativeFrame >= durationFrames) return null;

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        opacity,
        transform: `scale(${scale})`,
      }}
    >
      <img
        src={src}
        alt={alt}
        style={{
          width,
          maxHeight,
          objectFit: "contain", // remotion_spec.md 필수 규칙
          borderRadius: "12px",
          boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
        }}
      />
    </div>
  );
};
