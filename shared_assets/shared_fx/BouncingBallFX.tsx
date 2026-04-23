import React, { useMemo } from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring, Easing } from "remotion";

/**
 * BouncingBallFX — 단어를 따라 공이 통통 튀며 강조하는 효과
 *
 * 시청자가 텍스트를 읽는 속도에 맞춰 공이 가이드를 해주는 듯한 친절하고 귀여운 효과입니다.
 *
 * commonProps: startFrame, durationFrames, x, y
 * specificProps: text, fontSize, color, ballColor, bounceSpeed
 */

interface BouncingBallFXProps {
  startFrame?: number;
  durationFrames?: number;
  x?: number;
  y?: number;
  text: string;
  fontSize?: string;
  color?: string;
  ballColor?: string;
  bounceSpeed?: number;
}

export const BouncingBallFX: React.FC<BouncingBallFXProps> = ({
  startFrame = 0,
  durationFrames = 150,
  x = 0,
  y = 0,
  text,
  fontSize = "70px",
  color = "#FFFFFF",
  ballColor = "#FF2D55",
  bounceSpeed = 1.0,
}) => {
  const frame = useCurrentFrame();
  const { width, height, fps } = useVideoConfig();

  const rel = frame - startFrame;
  if (rel < 0 || rel >= durationFrames) return null;

  // 단어 단위 분할
  const words = useMemo(() => text.split(" "), [text]);
  const wordWidth = 120; // 대략적인 단어 간격 (한글 기준)

  // 전체 타이핑/바운스 진행도
  const totalSteps = words.length;
  const progressPerStep = durationFrames / totalSteps;

  const currentStep = Math.min(totalSteps - 1, Math.floor(rel / progressPerStep));
  const stepRel = (rel % progressPerStep) / progressPerStep;

  // 공의 X 위치: 선형 이동
  const ballX = interpolate(
    rel,
    [0, durationFrames],
    [-(words.length * wordWidth) / 2, (words.length * wordWidth) / 2]
  );

  // 공의 Y 위치: 포물선 바운스
  const bounceY = Math.abs(Math.sin(stepRel * Math.PI)) * -60;

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
        fontFamily: "sans-serif",
      }}
    >
      {/* 단어들 */}
      <div style={{ display: "flex", gap: "20px", position: "relative" }}>
        {words.map((word, i) => {
          const isActive = i === currentStep;
          return (
            <span
              key={i}
              style={{
                fontSize,
                fontWeight: "900",
                color,
                opacity: i <= currentStep ? 1 : 0.3,
                transform: `scale(${isActive ? 1.1 : 1})`,
                transition: "transform 0.2s ease",
              }}
            >
              {word}
            </span>
          );
        })}

        {/* 통통 튀는 공 */}
        <div
          style={{
            position: "absolute",
            left: ballX + (words.length * wordWidth) / 2, // 보정
            top: bounceY,
            width: "30px",
            height: "30px",
            backgroundColor: ballColor,
            borderRadius: "50%",
            boxShadow: `0 0 15px ${ballColor}`,
            zIndex: 20,
          }}
        />
      </div>
    </div>
  );
};
