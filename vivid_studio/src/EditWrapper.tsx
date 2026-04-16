/**
 * EditWrapper.tsx
 * Phase 3 — react-rnd 기반 드래그/리사이즈 HOC
 *
 * 역할:
 *   SlideCanvas 위에서 각 Effect를 감싸는 드래그·리사이즈 가능한 컨테이너.
 *   좌표계: display px (캔버스 스케일) ↔ video px (1920×1080) 변환 내장.
 *
 * 사용:
 *   <EditWrapper
 *     effect={eff}
 *     scale={0.333}
 *     selected={selectedId === eff.id}
 *     onSelect={() => onSelect(eff.id)}
 *     onChange={(updated) => onEffectChange(eff.id, updated)}
 *   />
 */

import { useCallback } from "react";
import { Rnd } from "react-rnd";
import { type Effect, VIDEO_W, VIDEO_H, withDefaults } from "./types";

// ── Effect type별 시각 스타일 ──────────────────────────────────────────────
const TYPE_COLOR: Record<string, string> = {
  Popup: "rgba(33,150,243,0.35)",
  TextPopup: "rgba(156,39,176,0.35)",
  Video: "rgba(76,175,80,0.20)",
  Custom: "rgba(255,152,0,0.35)",
  default: "rgba(226,176,74,0.30)",
};
const TYPE_BORDER: Record<string, string> = {
  Popup: "#2196f3",
  TextPopup: "#9c27b0",
  Video: "#4caf50",
  Custom: "#ff9800",
  default: "#e2b04a",
};

function typeColor(type: string) {
  return TYPE_COLOR[type] ?? TYPE_COLOR.default;
}
function typeBorder(type: string) {
  return TYPE_BORDER[type] ?? TYPE_BORDER.default;
}

// ── Props ─────────────────────────────────────────────────────────────────
interface EditWrapperProps {
  effect: Effect;
  /** display px / video px (예: 640/1920 ≈ 0.333) */
  scale: number;
  selected: boolean;
  /** 현재 프레임에서 활성 여부 — false이면 반투명 표시 */
  active?: boolean;
  onSelect: () => void;
  onChange: (updated: Effect) => void;
}

// ── 컴포넌트 ─────────────────────────────────────────────────────────────
export default function EditWrapper({
  effect,
  scale,
  selected,
  active = true,
  onSelect,
  onChange,
}: EditWrapperProps) {
  const eff = withDefaults(effect);

  // 1. 렌더링 공식: 박스의 '중심'이 효과의 실제 위치(eff.x, eff.y - 이미 절대좌표)에 오도록 배치
  const dispW = Math.max(eff.width * scale, 20);
  const dispH = Math.max(eff.height * scale, 16);
  // withDefaults를 거친 eff.x, eff.y는 이미 절대좌표(VIDEO_W/2 + relX)임.
  const dispX = eff.x * scale - dispW / 2;
  const dispY = eff.y * scale - dispH / 2;

  const border = typeBorder(eff.type);

  // 2. 역산 공식: (new_rnd_x + width * SCALE / 2) / SCALE - (VIDEO_W / 2)
  const handleDragStop = useCallback(
    (_e: unknown, d: { x: number; y: number }) => {
      const w = eff.width;
      const h = eff.height;
      // 중심점 구하기: (rnd_x + rnd_w / 2)
      const absX = Math.round((d.x + (w * scale) / 2) / scale);
      const absY = Math.round((d.y + (h * scale) / 2) / scale);
      // 중앙점(960, 540)을 빼서 relX, relY 도출
      const relX = absX - VIDEO_W / 2;
      const relY = absY - VIDEO_H / 2;

      onChange({
        ...effect,
        x: absX,
        y: absY,
        ...(effect.commonProps !== undefined && {
          commonProps: { ...effect.commonProps, x: relX, y: relY },
        }),
      });
    },
    [eff.width, eff.height, effect, onChange, scale]
  );

  const handleResizeStop = useCallback(
    (
      _e: unknown,
      _dir: unknown,
      ref: HTMLElement,
      _delta: unknown,
      pos: { x: number; y: number }
    ) => {
      const w = Math.round(ref.offsetWidth / scale);
      const h = Math.round(ref.offsetHeight / scale);
      // 중심점 구하기: (rnd_x + rnd_w / 2)
      const absX = Math.round((pos.x + (w * scale) / 2) / scale);
      const absY = Math.round((pos.y + (h * scale) / 2) / scale);
      const relX = absX - VIDEO_W / 2;
      const relY = absY - VIDEO_H / 2;

      onChange({
        ...effect,
        x: absX,
        y: absY,
        width: w,
        height: h,
        ...(effect.commonProps !== undefined && {
          commonProps: { ...effect.commonProps, x: relX, y: relY, width: w, height: h },
        }),
      });
    },
    [effect, onChange, scale]
  );

  return (
    <Rnd
      position={{ x: dispX, y: dispY }}
      size={{ width: dispW, height: dispH }}
      bounds="parent"
      onDragStop={handleDragStop}
      onResizeStop={handleResizeStop}
      onMouseDown={onSelect}
      style={{ zIndex: eff.zIndex ?? 0, opacity: active ? 1 : 0.25 }}
      enableResizing={selected}
    >
      <div
        style={{
          position: "relative",
          width: "100%",
          height: "100%",
          background: "transparent",
          border: selected ? `2px solid ${border}` : "1px solid rgba(255,255,255,0.18)",
          borderRadius: 3,
          boxSizing: "border-box",
          cursor: "move",
          userSelect: "none",
          outline: selected ? `1px solid ${border}` : "none",
          outlineOffset: 2,
        }}
      >
        {/* 타입 배지 — 선택 시에만 표시 */}
        {selected && (
          <div
            style={{
              position: "absolute",
              top: -18,
              left: 0,
              fontSize: 9,
              fontWeight: 700,
              color: "#fff",
              background: border,
              borderRadius: "2px 2px 0 0",
              padding: "1px 5px",
              lineHeight: 1.6,
              pointerEvents: "none",
              whiteSpace: "nowrap",
            }}
          >
            {eff.type}
          </div>
        )}

        {/* 선택 시 리사이즈 핸들 힌트 */}
        {selected && (
          <div
            style={{
              position: "absolute",
              bottom: 2,
              right: 2,
              width: 8,
              height: 8,
              background: border,
              borderRadius: 1,
              opacity: 0.9,
            }}
          />
        )}
      </div>
    </Rnd>
  );
}
