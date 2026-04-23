import React, { useMemo } from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring, random } from "remotion";

/**
 * SparkleTrailFX — 텍스트 주변을 감싸는 화려한 스파클 효과
 *
 * 축제, 보상, 혹은 아주 중요한 강조 사항에 사용하면 효과적입니다.
 *
 * commonProps: startFrame, durationFrames, x, y
 * specificProps: text, fontSize, color, sparkleColor, sparkleCount
 */

interface SparkleTrailFXProps {
  startFrame?: number;
  durationFrames?: number;
  x?: number;
  y?: number;
  text: string;
  fontSize?: string;
  color?: string;
  sparkleColor?: string;
  sparkleCount?: number;
}

export const SparkleTrailFX: React.FC<SparkleTrailFXProps> = ({
  startFrame = 0,
  durationFrames = 90,
  x = 0,
  y = 0,
  text,
  fontSize = "90px",
  color = "#FFFFFF",
  sparkleColor = "#FFD700",
  sparkleCount = 40,
}) => {
  const frame = useCurrentFrame();
  const { width, height, fps } = useVideoConfig();

  const rel = frame - startFrame;
  if (rel < 0 || rel >= durationFrames) return null;

  // 파티클 데이터 생성 (메모이제이션)
  const particles = useMemo(() => {
    return Array.from({ length: sparkleCount }).map((_, i) => ({
      id: i,
      angle: random(`angle-${i}`) * Math.PI * 2,
      radius: 50 + random(`radius-${i}`) * 150,
      size: 5 + random(`size-${i}`) * 15,
      delay: random(`delay-${i}`) * 20,
      speed: 0.5 + random(`speed-${i}`) * 1.5,
    }));
  }, [sparkleCount]);

  const cx = width / 2 + x;
  const cy = height / 2 + y;

  // 텍스트 등장 애니메이션 (스프링)
  const textSpr = spring({
    frame: rel,
    fps,
    config: { damping: 12, stiffness: 120 },
  });

  return (
    <div
      style={{
        position: "absolute",
        left: cx,
        top: cy,
        transform: "translate(-50%, -50%)",
        pointerEvents: "none",
        textAlign: "center",
      }}
    >
      {/* 텍스트 본체 */}
      <div
        style={{
          fontSize,
          fontWeight: "900",
          color,
          transform: `scale(${textSpr})`,
          zIndex: 10,
          fontFamily: "sans-serif",
          textShadow: `0 0 20px ${sparkleColor}88`,
        }}
      >
        {text}
      </div>

      {/* 스파클 파티클 레이어 */}
      {particles.map((p) => {
        const pRel = rel - p.delay;
        if (pRel < 0) return null;

        const opacity = interpolate(pRel, [0, 10, 40], [0, 1, 0], {
          extrapolateRight: "clamp",
        });

        const orbitRadius = p.radius * (1 + pRel * 0.01 * p.speed);
        const tx = Math.cos(p.angle + pRel * 0.05) * orbitRadius;
        const ty = Math.sin(p.angle + pRel * 0.05) * orbitRadius;

        return (
          <div
            key={p.id}
            style={{
              position: "absolute",
              left: "50%",
              top: "50%",
              width: p.size,
              height: p.size,
              backgroundColor: sparkleColor,
              borderRadius: "50%",
              opacity,
              transform: `translate(${tx}px, ${ty}px) scale(${opacity})`,
              boxShadow: `0 0 15px ${sparkleColor}`,
              filter: "blur(1px)",
            }}
          />
        );
      })}
    </div>
  );
};
