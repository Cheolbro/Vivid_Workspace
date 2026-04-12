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

export default function ColorPicker({ label, value, onChange }: ColorPickerProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // 외부 클릭 감지
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // hex가 유효하지 않으면 기본값
  const safeHex = /^#[0-9a-fA-F]{6}$/.test(value) ? value : "#888888";

  return (
    <div ref={ref} style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <label style={s.label}>{label}</label>

      {/* 색상 스와치 버튼 */}
      <button
        style={{ ...s.swatch, background: safeHex }}
        onClick={() => setOpen((v) => !v)}
        title={safeHex}
      />

      {/* hex 텍스트 입력 */}
      <input
        style={s.hexInput}
        type="text"
        value={value}
        maxLength={7}
        onChange={(e) => onChange(e.target.value)}
        onBlur={() => {
          // blur 시 유효하지 않으면 원래 값 복원
          if (!/^#[0-9a-fA-F]{6}$/.test(value)) onChange(safeHex);
        }}
      />

      {/* 팝업 피커 */}
      {open && (
        <div style={s.popover}>
          <HexColorPicker color={safeHex} onChange={onChange} />
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
    zIndex: 9999,
    marginTop: 4,
    top: "100%",
    left: 100,
    boxShadow: "0 8px 24px rgba(0,0,0,0.5)",
    borderRadius: 6,
    overflow: "hidden",
  },
};
