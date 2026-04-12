/**
 * MiniTimeline.tsx — Phase 4
 * 현재 슬라이드의 Effect 타이밍을 가로 타임라인으로 표시.
 *
 * 인터랙션:
 *   • 바 본체 드래그   → startFrame 이동
 *   • 좌측 핸들 드래그 → startFrame 조정 + durationFrames 역방향 조정
 *   • 우측 핸들 드래그 → durationFrames 연장/축소
 *   • 바 클릭          → Effect 선택 (EditPanel / Canvas 연동)
 *   • 슬라이드 배경 클릭 → 선택 해제
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Effect, Slide } from "./types";
import { withDefaults } from "./types";

// ── Effect type별 색상 (Phase 3과 동일 팔레트) ────────────────────────────
const TYPE_COLOR: Record<string, string> = {
  Popup: "#2196f3",
  TextPopup: "#9c27b0",
  Video: "#4caf50",
  Custom: "#ff9800",
  default: "#e2b04a",
};
function barColor(type: string) {
  return TYPE_COLOR[type] ?? TYPE_COLOR.default;
}

// ── 상수 ──────────────────────────────────────────────────────────────────
const ROW_H = 28; // 각 effect 행 높이(px)
const LABEL_W = 80; // 좌측 레이블 너비(px)
const RULER_H = 22; // 눈금자 높이(px)
const HANDLE_W = 6; // 드래그 핸들 너비(px)
const MIN_DUR = 1; // 최소 durationFrames

// ── 드래그 상태 타입 ──────────────────────────────────────────────────────
type DragType = "move" | "left" | "right";
interface DragState {
  effectId: string;
  type: DragType;
  startX: number; // mousedown 시 pageX
  origStart: number; // mousedown 시 startFrame
  origDur: number; // mousedown 시 durationFrames
  framesPerPx: number; // 드래그 계수
}

// ── 눈금자 ────────────────────────────────────────────────────────────────
interface RulerProps {
  totalFrames: number;
  pxPerFrame: number;
  currentFrame: number;
  onSeek: (frame: number) => void;
}

function Ruler({ totalFrames, pxPerFrame, currentFrame, onSeek }: RulerProps) {
  // 눈금 간격: 화면에 약 8~12개 표시되도록 자동 산정
  const step = useMemo(() => {
    const candidates = [5, 10, 15, 20, 30, 45, 60, 90, 120, 180, 240];
    const ideal = totalFrames / 10;
    return candidates.find((c) => c >= ideal) ?? 240;
  }, [totalFrames]);

  const marks: number[] = [];
  for (let f = 0; f <= totalFrames; f += step) marks.push(f);

  return (
    <div
      style={{ position: "relative", height: RULER_H, marginLeft: LABEL_W, cursor: "crosshair" }}
      onClick={(e: React.MouseEvent<HTMLDivElement>) => {
        const rect = e.currentTarget.getBoundingClientRect();
        onSeek(
          Math.max(0, Math.min(Math.round((e.clientX - rect.left) / pxPerFrame), totalFrames))
        );
      }}
    >
      {marks.map((f) => (
        <div
          key={f}
          style={{
            position: "absolute",
            left: f * pxPerFrame,
            top: 0,
            height: "100%",
            display: "flex",
            flexDirection: "column",
            alignItems: "flex-start",
            transform: "translateX(-50%)",
            pointerEvents: "none",
          }}
        >
          <span
            style={{
              fontSize: 8,
              color: "#3a5a7a",
              lineHeight: 1,
              paddingBottom: 2,
              paddingLeft: 1,
            }}
          >
            {f}
          </span>
          <div style={{ width: 1, flex: 1, background: "#1a3050" }} />
        </div>
      ))}
      {/* 종단 마크 */}
      <div
        style={{
          position: "absolute",
          left: totalFrames * pxPerFrame,
          top: 0,
          bottom: 0,
          width: 1,
          background: "#e2b04a",
          opacity: 0.4,
          pointerEvents: "none",
        }}
      />
      {/* 눈금자 플레이헤드 마커 */}
      <div
        style={{
          position: "absolute",
          left: currentFrame * pxPerFrame,
          top: 0,
          width: 2,
          height: "100%",
          background: "#ff5252",
          transform: "translateX(-50%)",
          pointerEvents: "none",
          zIndex: 5,
        }}
      />
    </div>
  );
}

// ── 단일 Effect 행 ─────────────────────────────────────────────────────────
interface EffectRowProps {
  effect: Effect;
  totalFrames: number;
  pxPerFrame: number;
  selected: boolean;
  onSelect: () => void;
  onDragStart: (type: DragType, pageX: number) => void;
}

function EffectRow({
  effect,
  totalFrames,
  pxPerFrame,
  selected,
  onSelect,
  onDragStart,
}: EffectRowProps) {
  const eff = withDefaults(effect);
  const color = barColor(eff.type);

  const barLeft = Math.max(0, eff.startFrame) * pxPerFrame;
  const barWidth = Math.max(MIN_DUR, eff.durationFrames) * pxPerFrame;
  const maxLeft = totalFrames * pxPerFrame;

  // 바가 슬라이드 범위를 넘지 않도록 클리핑
  const clippedLeft = Math.min(barLeft, maxLeft);
  const clippedWidth = Math.min(barWidth, maxLeft - clippedLeft);

  return (
    <div style={{ display: "flex", height: ROW_H, alignItems: "center" }}>
      {/* 레이블 */}
      <div
        style={{
          width: LABEL_W,
          paddingRight: 6,
          flexShrink: 0,
          fontSize: 9,
          color: selected ? color : "#4a6a8a",
          textAlign: "right",
          fontWeight: selected ? 700 : 400,
          fontFamily: "monospace",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
          cursor: "pointer",
        }}
        onClick={onSelect}
        title={`${eff.type} · ${eff.id}`}
      >
        {eff.type}
      </div>

      {/* 트랙 */}
      <div style={{ flex: 1, position: "relative", height: "100%" }}>
        {/* 트랙 배경 */}
        <div
          style={{
            position: "absolute",
            inset: "4px 0",
            background: "#0a1020",
            borderRadius: 2,
          }}
          onClick={onSelect}
        />

        {/* 이펙트 바 */}
        {clippedWidth > 0 && (
          <div
            style={{
              position: "absolute",
              left: clippedLeft,
              width: clippedWidth,
              top: 4,
              bottom: 4,
              borderRadius: 3,
              background: `${color}${selected ? "cc" : "80"}`,
              border: `1px solid ${color}${selected ? "ff" : "88"}`,
              boxSizing: "border-box",
              cursor: "grab",
              display: "flex",
              alignItems: "center",
              overflow: "hidden",
              userSelect: "none",
            }}
          >
            {/* 좌측 핸들 */}
            <div
              style={{
                width: HANDLE_W,
                height: "100%",
                flexShrink: 0,
                cursor: "w-resize",
                background: selected ? `${color}dd` : "transparent",
                borderRight: `1px solid ${color}88`,
              }}
              onMouseDown={(e) => {
                e.stopPropagation();
                onDragStart("left", e.pageX);
              }}
            />

            {/* 본체 (이동) */}
            <div
              style={{ flex: 1, height: "100%", cursor: "grab", minWidth: 0 }}
              onMouseDown={(e) => {
                e.stopPropagation();
                onDragStart("move", e.pageX);
              }}
              onClick={onSelect}
            >
              {clippedWidth > 30 && (
                <span
                  style={{
                    fontSize: 8,
                    color,
                    paddingLeft: 4,
                    fontFamily: "monospace",
                    whiteSpace: "nowrap",
                    lineHeight: `${ROW_H - 8}px`,
                  }}
                >
                  {eff.startFrame}→{eff.startFrame + eff.durationFrames}
                </span>
              )}
            </div>

            {/* 우측 핸들 */}
            <div
              style={{
                width: HANDLE_W,
                height: "100%",
                flexShrink: 0,
                cursor: "e-resize",
                background: selected ? `${color}dd` : "transparent",
                borderLeft: `1px solid ${color}88`,
              }}
              onMouseDown={(e) => {
                e.stopPropagation();
                onDragStart("right", e.pageX);
              }}
            />
          </div>
        )}
      </div>
    </div>
  );
}

// ── MiniTimeline 메인 ──────────────────────────────────────────────────────
interface MiniTimelineProps {
  slide: Slide;
  selectedEffectId: string | null;
  onEffectSelect: (id: string) => void;
  onEffectChange: (effectId: string, updated: Effect) => void;
  currentFrame: number;
  onFrameChange: (frame: number) => void;
}

export default function MiniTimeline({
  slide,
  selectedEffectId,
  onEffectSelect,
  onEffectChange,
  currentFrame,
  onFrameChange,
}: MiniTimelineProps) {
  const trackRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<DragState | null>(null);
  const playheadDragging = useRef(false);
  const [trackW, setTrackW] = useState(500);

  const pageXToFrame = (pageX: number): number => {
    if (!trackRef.current) return 0;
    const rect = trackRef.current.getBoundingClientRect();
    const total = Math.max(1, slide.durationFrames);
    const ppf = trackW / total;
    return Math.max(0, Math.min(Math.round((pageX - rect.left - LABEL_W) / ppf), total));
  };

  // 트랙 너비 측정
  useEffect(() => {
    if (!trackRef.current) return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width;
      if (w) setTrackW(w - LABEL_W);
    });
    ro.observe(trackRef.current);
    return () => ro.disconnect();
  }, []);

  const totalFrames = Math.max(1, slide.durationFrames);
  const pxPerFrame = trackW / totalFrames;

  // ── 드래그 시작 ─────────────────────────────────────────────────────────
  const handleDragStart = useCallback(
    (effectId: string, type: DragType, pageX: number) => {
      const eff = slide.effects.find((e) => e.id === effectId);
      if (!eff) return;
      dragRef.current = {
        effectId,
        type,
        startX: pageX,
        origStart: eff.startFrame,
        origDur: eff.durationFrames,
        framesPerPx: 1 / pxPerFrame,
      };
      onEffectSelect(effectId);
    },
    [slide.effects, pxPerFrame, onEffectSelect]
  );

  // ── 드래그 중 (document 레벨) ───────────────────────────────────────────
  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (playheadDragging.current) {
        onFrameChange(pageXToFrame(e.pageX));
        return;
      }
      const drag = dragRef.current;
      if (!drag) return;

      const deltaX = e.pageX - drag.startX;
      const deltaFrames = Math.round(deltaX * drag.framesPerPx);

      const eff = slide.effects.find((f) => f.id === drag.effectId);
      if (!eff) return;

      let newStart = drag.origStart;
      let newDur = drag.origDur;

      if (drag.type === "move") {
        newStart = Math.max(0, Math.min(drag.origStart + deltaFrames, totalFrames - MIN_DUR));
      } else if (drag.type === "right") {
        newDur = Math.max(
          MIN_DUR,
          Math.min(drag.origDur + deltaFrames, totalFrames - drag.origStart)
        );
      } else if (drag.type === "left") {
        const shift = Math.min(deltaFrames, drag.origStart); // 왼쪽으로 못 이동
        const clamp = Math.max(-drag.origDur + MIN_DUR, shift);
        newStart = drag.origStart + clamp;
        newDur = drag.origDur - clamp;
      }

      onEffectChange(drag.effectId, { ...eff, startFrame: newStart, durationFrames: newDur });
    };

    const onUp = () => {
      playheadDragging.current = false;
      dragRef.current = null;
    };

    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
    return () => {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    };
  }, [slide.effects, totalFrames, onEffectChange, onFrameChange]);

  // 눈금자용 마커 간격
  const fps = 30; // 기본 fps (필요시 plan.fps 주입)

  // ── 렌더 ─────────────────────────────────────────────────────────────────
  return (
    <div style={s.root}>
      {/* 헤더 */}
      <div style={s.header}>
        <span style={s.headerTitle}>Timeline</span>
        <span style={s.headerInfo}>
          {slide.effects.length}개 FX · {totalFrames}f ({(totalFrames / fps).toFixed(1)}s @ {fps}
          fps)
        </span>
        <span style={s.frameLabel}>▶ {currentFrame}f</span>
        {selectedEffectId &&
          (() => {
            const eff = slide.effects.find((e) => e.id === selectedEffectId);
            return eff ? (
              <span style={s.selectedInfo}>
                [{eff.type}] {eff.startFrame}f→{eff.startFrame + eff.durationFrames}f &nbsp;(
                {eff.durationFrames}f)
              </span>
            ) : null;
          })()}
      </div>

      {/* 타임라인 본체 */}
      <div style={s.body} ref={trackRef}>
        {/* 눈금자 */}
        <Ruler
          totalFrames={totalFrames}
          pxPerFrame={pxPerFrame}
          currentFrame={currentFrame}
          onSeek={(f) => onFrameChange(Math.max(0, Math.min(f, totalFrames)))}
        />

        {/* Effect 행들 */}
        <div
          style={{ overflowY: "auto", maxHeight: 160 }}
          onMouseDown={(e) => {
            // 배경 클릭 시 선택 해제
            if (e.target === e.currentTarget) onEffectSelect("");
          }}
        >
          {slide.effects.length === 0 ? (
            <div style={s.emptyHint}>이 슬라이드에 FX가 없습니다.</div>
          ) : (
            slide.effects.map((eff) => (
              <EffectRow
                key={eff.id}
                effect={eff}
                totalFrames={totalFrames}
                pxPerFrame={pxPerFrame}
                selected={selectedEffectId === eff.id}
                onSelect={() => onEffectSelect(eff.id)}
                onDragStart={(type, pageX) => handleDragStart(eff.id, type, pageX)}
              />
            ))
          )}
        </div>

        {/* 배경 눈금 세로선 (뷰 전체) */}
        <div style={s.gridOverlay} aria-hidden>
          {Array.from({ length: Math.floor(totalFrames / 10) + 1 }, (_, i) => i * 10).map((f) => (
            <div
              key={f}
              style={{
                position: "absolute",
                left: LABEL_W + f * pxPerFrame,
                top: RULER_H,
                bottom: 0,
                width: 1,
                background: f % 30 === 0 ? "rgba(255,255,255,0.06)" : "rgba(255,255,255,0.025)",
                pointerEvents: "none",
              }}
            />
          ))}
        </div>

        {/* 플레이헤드 세로선 */}
        <div
          style={{
            position: "absolute",
            left: LABEL_W + currentFrame * pxPerFrame,
            top: 0,
            bottom: 0,
            width: 2,
            background: "#ff5252",
            transform: "translateX(-50%)",
            pointerEvents: "none",
            zIndex: 10,
          }}
        />
        {/* 플레이헤드 드래그 핸들 */}
        <div
          style={{
            position: "absolute",
            left: LABEL_W + currentFrame * pxPerFrame,
            top: RULER_H - 6,
            fontSize: 10,
            color: "#ff5252",
            transform: "translateX(-50%)",
            cursor: "ew-resize",
            zIndex: 11,
            lineHeight: 1,
            userSelect: "none",
          }}
          onMouseDown={(e) => {
            e.stopPropagation();
            playheadDragging.current = true;
          }}
        >
          ▼
        </div>
      </div>
    </div>
  );
}

// ── 스타일 ──────────────────────────────────────────────────────────────────
const s: Record<string, React.CSSProperties> = {
  root: {
    background: "#10182a",
    borderTop: "1px solid #0f2840",
    flexShrink: 0,
    userSelect: "none",
  },
  header: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: "5px 12px",
    borderBottom: "1px solid #0f2040",
  },
  headerTitle: {
    fontSize: 10,
    fontWeight: 700,
    color: "#e2b04a",
    textTransform: "uppercase",
    letterSpacing: "0.5px",
  },
  headerInfo: {
    fontSize: 10,
    color: "#3a5a7a",
    fontFamily: "monospace",
  },
  frameLabel: {
    fontSize: 10,
    color: "#ff5252",
    fontFamily: "monospace",
    marginLeft: "auto",
  },
  selectedInfo: {
    fontSize: 10,
    color: "#7ec8e3",
    fontFamily: "monospace",
  },
  body: {
    position: "relative",
    padding: "0 8px 6px 0",
    overflow: "hidden",
  },
  emptyHint: {
    fontSize: 11,
    color: "#2a3a5a",
    textAlign: "center",
    padding: "12px 0",
  },
  gridOverlay: {
    position: "absolute",
    inset: 0,
    pointerEvents: "none",
  },
};
