import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate } from "remotion";

/**
 * WarningFrameFX — 위기 경고 프레임
 *
 * 경제 위기·폭락·경고 메시지 장면에서 화면 테두리에 불길한 긴장감을 부여합니다.
 * inset box-shadow + Math.sin 루핑으로 opacity가 천천히 점멸(Pulsing)합니다.
 * 화면 전체를 덮는 오버레이 div — 콘텐츠는 투명 중앙부를 통해 그대로 보입니다.
 *
 * commonProps  : startFrame, durationFrames (x, y 미사용)
 * specificProps: color, blinkSpeed, thickness
 */

interface WarningFrameFXProps {
  startFrame?: number;
  durationFrames?: number;
  color?: string; // 경고 색상 (기본: 붉은색)
  blinkSpeed?: number; // 점멸 주기 (초, 기본 1.6초)
  thickness?: number; // 테두리 두께 (px, 기본 80)
}

export const WarningFrameFX: React.FC<WarningFrameFXProps> = ({
  startFrame = 0,
  durationFrames = 180,
  color = "rgba(220, 0, 0, 0.55)",
  blinkSpeed = 1.6,
  thickness = 80,
}) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();

  const rel = frame - startFrame;
  if (rel < 0 || rel >= durationFrames) return null;

  // 등장 페이드인 (첫 20프레임)
  const fadeIn = interpolate(rel, [0, 20], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // 퇴장 페이드아웃 (마지막 15프레임)
  const fadeOut = interpolate(rel, [durationFrames - 15, durationFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // 불길한 sin 점멸: 0.35 ~ 1.0 사이 (너무 꺼지지 않게)
  const cycleFrames = fps * blinkSpeed;
  const phase = (rel % cycleFrames) / cycleFrames;
  // (sin + 1) / 2 → 0~1 정규화, 0.35~1.0 구간으로 리매핑
  const sinVal = (Math.sin(phase * Math.PI * 2 - Math.PI / 2) + 1) / 2;
  const blinkOpacity = 0.35 + sinVal * 0.65;

  const combinedOpacity = Math.min(fadeIn, fadeOut) * blinkOpacity;

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        width,
        height,
        opacity: combinedOpacity,
        pointerEvents: "none",
        // inset box-shadow: 내부에서 테두리 방향으로 번지는 그림자
        boxShadow: `inset 0 0 ${thickness * 1.5}px ${thickness * 0.6}px ${color}`,
        borderRadius: 0,
      }}
    />
  );
};
