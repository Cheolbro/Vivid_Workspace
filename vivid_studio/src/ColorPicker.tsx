/**
 * ColorPicker.tsx
 * react-colorful 기반 인라인 색상 선택기
 * 클릭 시 팝업, 외부 클릭 시 자동 닫힘
 */

import { useEffect, useRef, useState } from "react";
import { HexColorPicker } from "react-colorful";

interface ColorPickerProps {
  label: string;
  value: string; // hex: "#rrggbb"
  onChange: (hex: string) => void;
}

const isValidHex = (v: string) => /^#[0-9a-fA-F]{6}$/.test(v);

export default function ColorPicker({ label, value, onChange }: ColorPickerProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // 로컬 draft — 드래그 중 부모 재렌더링에 의해 피커 위치가 튀는 현상 방지
  const safeValue = isValidHex(value) ? value : "#888888";
  const [draft, setDraft] = useState(safeValue);

  // 선택된 이펙트가 바뀌면(=value가 바뀌면) draft 동기화
  // 단, 팝업이 열려있는 동안(= 사용자가 드래그 중)엔 동기화하지 않음
  const openRef = useRef(open);
  openRef.current = open;
  useEffect(() => {
    if (!openRef.current) setDraft(safeValue);
  }, [safeValue]); // eslint-disable-line react-hooks/exhaustive-deps

  // 외부 클릭 시 팝업 닫기 + 최종 값 부모에 커밋
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
        onChange(draft); // 팝업 닫힐 때 한 번만 부모에 전달
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open, draft, onChange]);

  return (
    <div ref={ref} style={{ position: "relative", display: "flex", alignItems: "center", gap: 6 }}>
      <label style={s.label}>{label}</label>

      {/* 색상 스와치 버튼 */}
      <button
        style={{ ...s.swatch, background: draft }}
        onClick={() => setOpen((v) => !v)}
        title={draft}
      />

      {/* hex 텍스트 입력 — 직접 타이핑 시엔 즉시 부모에 반영 */}
      <input
        style={s.hexInput}
        type="text"
        value={draft}
        maxLength={7}
        onChange={(e) => {
          setDraft(e.target.value);
          if (isValidHex(e.target.value)) onChange(e.target.value);
        }}
        onBlur={() => {
          if (!isValidHex(draft)) {
            setDraft(safeValue);
            onChange(safeValue);
          }
        }}
      />

      {/* 팝업 피커 — draft만 업데이트, 부모는 팝업 닫힐 때 커밋 */}
      {open && (
        <div style={s.popover} onMouseDown={(e) => e.stopPropagation()}>
          <HexColorPicker color={draft} onChange={setDraft} />
        </div>
      )}
    </div>
  );
}

const s: Record<string, React.CSSProperties> = {
  label: {
    fontSize: 10,
    color: "#5a7a9a",
    width: 100,
    flexShrink: 0,
    fontFamily: "monospace",
  },
  swatch: {
    width: 20,
    height: 20,
    borderRadius: 3,
    border: "1px solid #2a4a6a",
    cursor: "pointer",
    flexShrink: 0,
    padding: 0,
  },
  hexInput: {
    flex: 1,
    background: "#0f1a30",
    border: "1px solid #1a3a5a",
    borderRadius: 3,
    color: "#e0e0e0",
    padding: "3px 6px",
    fontSize: 11,
    outline: "none",
    fontFamily: "monospace",
  },
  popover: {
    position: "absolute",
    zIndex: 10000,
    marginTop: 4,
    top: "100%",
    right: 0,
    boxShadow: "0 8px 24px rgba(0,0,0,0.5)",
    borderRadius: 6,
    overflow: "hidden",
    background: "#16213e", // EditPanel 배경과 맞춤
    padding: "8px",
    border: "1px solid #0f3460",
  },
};
