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
import type { Effect } from "./types";
import { withDefaults } from "./types";

// ── props에서 텍스트 / 이미지 URL 추출 ───────────────────────────────────
function extractText(effect: Effect): string {
  const p = effect.props ?? {};
  return String(p.text ?? p.content ?? p.subtitle ?? p.label ?? p.message ?? p.caption ?? "");
}
function extractImgSrc(effect: Effect): string {
  const p = effect.props ?? {};
  const raw = String(p.src ?? p.image ?? p.imageSrc ?? p.url ?? "");
  if (!raw) return "";
  const name = raw.split(/[\\/]/).pop() ?? raw;
  return `/api/asset/${name}`;
}
function extractColor(effect: Effect): string {
  const p = effect.props ?? {};
  return String(p.color ?? p.textColor ?? p.fillColor ?? "");
}

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

  // video px → display px
  const dispX = eff.x * scale;
  const dispY = eff.y * scale;
  const dispW = Math.max(eff.width * scale, 20);
  const dispH = Math.max(eff.height * scale, 16);

  const border = typeBorder(eff.type);

  const handleDragStop = useCallback(
    (_e: unknown, d: { x: number; y: number }) => {
      onChange({
        ...effect,
        x: Math.round(d.x / scale),
        y: Math.round(d.y / scale),
      });
    },
    [effect, onChange, scale]
  );

  const handleResizeStop = useCallback(
    (
      _e: unknown,
      _dir: unknown,
      ref: HTMLElement,
      _delta: unknown,
      pos: { x: number; y: number }
    ) => {
      onChange({
        ...effect,
        x: Math.round(pos.x / scale),
        y: Math.round(pos.y / scale),
        width: Math.round(ref.offsetWidth / scale),
        height: Math.round(ref.offsetHeight / scale),
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
          background: typeColor(eff.type),
          border: `${selected ? 2 : 1}px solid ${border}`,
          borderRadius: 3,
          boxSizing: "border-box",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          alignItems: "center",
          overflow: "hidden",
          cursor: "move",
          userSelect: "none",
          outline: selected ? `2px solid ${border}` : "none",
          outlineOffset: 1,
        }}
      >
        {/* Popup 이미지 썸네일 */}
        {eff.type === "Popup" && extractImgSrc(effect) && (
          <img
            src={extractImgSrc(effect)}
            draggable={false}
            style={{
              position: "absolute",
              inset: 0,
              width: "100%",
              height: "100%",
              objectFit: "cover",
              opacity: 0.55,
              pointerEvents: "none",
            }}
            alt=""
          />
        )}

        {/* 타입 배지 (좌상단 고정) */}
        <div
          style={{
            position: "absolute",
            top: 2,
            left: 3,
            fontSize: Math.max(7, dispH * 0.13),
            fontWeight: 700,
            color: border,
            background: "rgba(0,0,0,0.55)",
            borderRadius: 2,
            padding: "0 3px",
            lineHeight: 1.5,
            pointerEvents: "none",
            maxWidth: "90%",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {eff.type}
        </div>

        {/* 텍스트 컨텐츠 (text/content/subtitle 등 props) */}
        {extractText(effect) ? (
          <div
            style={{
              position: "relative",
              zIndex: 1,
              fontSize: Math.max(9, Math.min(dispH * 0.22, 18)),
              fontWeight: 600,
              color: extractColor(effect) || "#ffffff",
              textAlign: "center",
              lineHeight: 1.35,
              padding: "0 6px",
              maxWidth: "100%",
              maxHeight: "70%",
              overflow: "hidden",
              display: "-webkit-box",
              WebkitLineClamp: 3,
              WebkitBoxOrient: "vertical",
              textShadow: "0 1px 3px rgba(0,0,0,0.8)",
              wordBreak: "break-word",
            }}
          >
            {extractText(effect)}
          </div>
        ) : (
          /* 텍스트 없는 경우 — 타입명만 크게 */
          <div
            style={{
              fontSize: Math.max(9, dispH * 0.2),
              fontWeight: 700,
              color: border,
              opacity: 0.7,
              pointerEvents: "none",
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
              opacity: 0.8,
            }}
          />
        )}
      </div>
    </Rnd>
  );
}
