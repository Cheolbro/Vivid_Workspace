/**
 * SlideCanvas.tsx
 * Phase 3 — 슬라이드 레이아웃 시각화 캔버스
 *
 * 1920×1080 비디오 프레임을 640×360으로 축소 표시.
 * 각 Effect를 EditWrapper로 렌더링 → 드래그/리사이즈 가능.
 * 선택된 Effect는 하이라이트 + EditPanel 연동.
 */

import { useEffect, useMemo, useRef } from "react";
import { Player, type PlayerRef } from "@remotion/player";
import { type Effect, type Slide, VIDEO_W } from "./types";
import EditWrapper from "./EditWrapper";
import { DynamicSlide } from "./DynamicSlide";

// 캔버스 표시 크기 (16:9) - 가시성 확보를 위한 80% 축소 (768x432)
const CANVAS_W = 768;
const CANVAS_H = 432;

// 비디오 실제 크기는 types.ts의 VIDEO_W (1920), VIDEO_H (1080) 사용
const VIDEO_H = 1080;

const SCALE = CANVAS_W / VIDEO_W; // 768 / 1920 = 0.4

interface SlideCanvasProps {
  slide: Slide;
  selectedEffectId: string | null;
  onEffectSelect: (id: string) => void;
  onEffectChange: (effectId: string, updated: Effect) => void;
  currentFrame?: number;
}

export default function SlideCanvas({
  slide,
  selectedEffectId,
  onEffectSelect,
  onEffectChange,
  currentFrame,
}: SlideCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const playerRef = useRef<PlayerRef>(null);

  // pause() 후 seekTo() — Player가 재생 중일 때 충돌 방지
  useEffect(() => {
    if (!playerRef.current) return;
    playerRef.current.pause();
    playerRef.current.seekTo(currentFrame ?? 0);
  }, [currentFrame]);

  // 슬라이드 시작 절대 프레임 — remotion_plan.json의 startFrame은 영상 전체 기준 절대값.
  // Player는 슬라이드 1개를 0부터 재생하므로 로컬 프레임으로 변환 필수.
  const slideStart = useMemo(
    () => (slide.effects.length > 0 ? Math.min(...slide.effects.map((e) => e.startFrame ?? 0)) : 0),
    [slide.effects]
  );

  // inputProps 불변성 + 절대→로컬 startFrame 변환
  // FX 컴포넌트: rel = useCurrentFrame() - startFrame → 절대값 그대로 주면 rel < 0 → null 반환
  const playerInputProps = useMemo(
    () => ({
      effects: slide.effects.map((e) => ({
        ...e,
        startFrame: (e.startFrame ?? 0) - slideStart, // 절대 → 로컬 변환
      })),
    }),
    [slide.effects, slideStart]
  );

  // z-index 순으로 정렬 (낮은 것 먼저 렌더 → 높은 것이 위에 표시)
  const sortedEffects = [...slide.effects].sort((a, b) => (a.zIndex ?? 0) - (b.zIndex ?? 0));

  return (
    <div style={s.wrapper}>
      {/* 슬라이드 정보 바 */}
      <div style={s.infoBar}>
        <span style={s.infoLabel}>
          슬라이드 레이아웃 · {slide.effects.length}개 FX · {CANVAS_W}×{CANVAS_H}px (1/3 축소)
        </span>
        <span style={s.infoLabel}>
          video: {VIDEO_W}×{VIDEO_H}
        </span>
      </div>

      {/* 캔버스 프레임 */}
      <div
        ref={containerRef}
        style={{
          ...s.canvas,
          width: CANVAS_W,
          height: CANVAS_H,
        }}
        onClick={(e) => {
          // 캔버스 배경 클릭 시 선택 해제
          if (e.target === containerRef.current) {
            onEffectSelect("");
          }
        }}
      >
        {/* 배경 격자 */}
        <div style={s.grid} />

        {/* 비디오 중앙 가이드라인 */}
        <div
          style={{ ...s.guideline, left: CANVAS_W / 2 - 0.5, top: 0, width: 1, height: "100%" }}
        />
        <div
          style={{ ...s.guideline, top: CANVAS_H / 2 - 0.5, left: 0, height: 1, width: "100%" }}
        />

        {/* 안전 영역 (Safe Zone: 90%) */}
        <div
          style={{
            ...s.safeZone,
            left: CANVAS_W * 0.05,
            top: CANVAS_H * 0.05,
            width: CANVAS_W * 0.9,
            height: CANVAS_H * 0.9,
          }}
        />

        {/* ── 레이어 1 (Base): Player — 실제 FX 렌더링 ────────────────────────
            컨테이너(640×360)가 표시 크기를 결정하고,
            Player는 width/height:"100%"로 채우며 1920×1080→640×360 내부 스케일링 처리.
            CSS transform을 Player에 직접 적용하지 않음.                          */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            zIndex: 3,
            pointerEvents: "none",
          }}
        >
          <Player
            ref={playerRef}
            component={DynamicSlide}
            inputProps={playerInputProps}
            compositionWidth={VIDEO_W}
            compositionHeight={VIDEO_H}
            fps={30}
            durationInFrames={Math.max(1, slide.durationFrames)}
            controls={false}
            autoPlay={false}
            style={{ width: "100%", height: "100%" }}
          />
        </div>

        {/* ── 레이어 2 (Overlay): 투명 react-rnd 인터랙션 레이어 ────────────────
            Player 위를 position:absolute로 덮음. react-rnd는 이 레이어에서만 렌더링.
            Player 내부로 rnd 컴포넌트가 절대 혼입되지 않도록 완전히 분리.          */}
        <div style={{ position: "absolute", inset: 0, zIndex: 10 }}>
          {sortedEffects.map((eff) => {
            // 절대 startFrame → 로컬 변환 후 currentFrame(로컬)과 비교
            const localStart = (eff.startFrame ?? 0) - slideStart;
            const isActive =
              currentFrame === undefined ||
              (currentFrame >= localStart &&
                currentFrame < localStart + (eff.durationFrames ?? 30));

            return (
              <EditWrapper
                key={eff.id}
                effect={eff}
                scale={SCALE}
                selected={selectedEffectId === eff.id}
                active={isActive}
                onSelect={() => onEffectSelect(eff.id)}
                onChange={(updated) => onEffectChange(eff.id, updated)}
              />
            );
          })}
        </div>

        {/* 빈 슬라이드 안내 */}
        {slide.effects.length === 0 && <div style={s.emptyHint}>이 슬라이드에 FX가 없습니다</div>}

        {/* 스케일 워터마크 */}
        <div style={s.watermark}>1920×1080</div>
      </div>

      {/* 선택 effect 좌표 정보 */}
      {selectedEffectId &&
        (() => {
          const eff = slide.effects.find((e) => e.id === selectedEffectId);
          if (!eff) return null;
          return (
            <div style={s.coordBar}>
              <span style={s.coordChip}>x: {eff.x ?? 0}</span>
              <span style={s.coordChip}>y: {eff.y ?? 0}</span>
              <span style={s.coordChip}>w: {eff.width ?? 400}</span>
              <span style={s.coordChip}>h: {eff.height ?? 240}</span>
              <span style={s.coordChip}>z: {eff.zIndex ?? 0}</span>
              <span style={{ ...s.coordChip, color: "#e2b04a" }}>{eff.type}</span>
            </div>
          );
        })()}
    </div>
  );
}

// ── 스타일 ──────────────────────────────────────────────────────────────────
const s: Record<string, React.CSSProperties> = {
  wrapper: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: 6,
  },
  infoBar: {
    width: CANVAS_W,
    display: "flex",
    justifyContent: "space-between",
  },
  infoLabel: {
    fontSize: 10,
    color: "#3a5a7a",
    fontFamily: "monospace",
  },
  canvas: {
    position: "relative",
    background: "#0a0e1a",
    border: "1px solid #1a3060",
    borderRadius: 4,
    overflow: "hidden",
    flexShrink: 0,
  },
  bgImage: {
    position: "absolute",
    inset: 0,
    width: "100%",
    height: "100%",
    objectFit: "cover",
    pointerEvents: "none",
    userSelect: "none",
    opacity: 0.9,
    zIndex: 0,
  },
  grid: {
    position: "absolute",
    inset: 0,
    zIndex: 1,
    backgroundImage:
      "linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px)," +
      "linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px)",
    backgroundSize: `${CANVAS_W / 16}px ${CANVAS_H / 9}px`,
    pointerEvents: "none",
  },
  guideline: {
    position: "absolute",
    background: "rgba(255,255,255,0.06)",
    pointerEvents: "none",
    zIndex: 2,
  },
  safeZone: {
    position: "absolute",
    border: "1px dashed rgba(255,255,255,0.07)",
    pointerEvents: "none",
    borderRadius: 2,
    zIndex: 2,
  },
  emptyHint: {
    position: "absolute",
    inset: 0,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 12,
    color: "#2a3a5a",
    pointerEvents: "none",
  },
  watermark: {
    position: "absolute",
    bottom: 4,
    right: 6,
    fontSize: 9,
    color: "#1a2a3a",
    fontFamily: "monospace",
    pointerEvents: "none",
  },
  coordBar: {
    width: CANVAS_W,
    display: "flex",
    gap: 6,
  },
  coordChip: {
    fontSize: 10,
    color: "#5a8aaa",
    background: "#0f1a2a",
    border: "1px solid #1a3040",
    borderRadius: 3,
    padding: "1px 6px",
    fontFamily: "monospace",
  },
};
