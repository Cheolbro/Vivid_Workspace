/**
 * EditPanel.tsx — Phase 3 (controlled)
 *
 * 완전 제어형(Controlled) 컴포넌트.
 * 모든 상태는 VividStudio가 소유하며, EditPanel은 props로 받고 콜백으로 알립니다.
 *
 * 동적 UI:
 *   - color prop (key에 color/fill/stroke 포함) → ColorPicker
 *   - 그 외 → 텍스트/숫자 입력
 *   - z-index 슬라이더 → Effect 쌓임 순서 제어
 */

import { useState } from "react";
import type { Effect, RemotionPlan, Slide } from "./types";
import { isColorProp, isFileProp, withDefaults } from "./types";
import ColorPicker from "./ColorPicker";

// ── Props ──────────────────────────────────────────────────────────────────
interface EditPanelProps {
  plan: RemotionPlan | null;
  loading: boolean;
  saving: boolean;
  selectedSlideIdx: number;
  selectedEffectId: string | null;
  onSlideSelect: (idx: number) => void;
  onEffectSelect: (id: string) => void;
  onSlideChange: (idx: number, slide: Slide) => void;
  onSave: () => void;
  onReset: () => void;
}

// ── Effect 타입별 아이콘 ────────────────────────────────────────────────────
const TYPE_ICON: Record<string, string> = {
  Popup: "🔲",
  TextPopup: "🔤",
  Video: "🎬",
  Custom: "✨",
  default: "⚡",
};
function typeIcon(t: string) {
  return TYPE_ICON[t] ?? TYPE_ICON.default;
}

// ── 단일 필드 ──────────────────────────────────────────────────────────────
function Field({
  label,
  value,
  type = "text",
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  value: string | number;
  type?: "text" | "number";
  min?: number;
  max?: number;
  step?: number;
  onChange: (v: string) => void;
}) {
  return (
    <div style={s.field}>
      <label style={s.fieldLabel}>{label}</label>
      <input
        style={s.input}
        type={type}
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}

// ── Effect 편집 섹션 ────────────────────────────────────────────────────────
function EffectEditor({
  effect,
  onChange,
}: {
  effect: Effect;
  onChange: (updated: Effect) => void;
}) {
  const eff = withDefaults(effect);
  const [propsOpen, setPropsOpen] = useState(true);

  const set = (key: keyof Effect, val: unknown) => onChange({ ...effect, [key]: val });

  const setProp = (key: string, val: unknown) =>
    onChange({ ...effect, props: { ...(effect.props ?? {}), [key]: val } });

  const propKeys = Object.keys(effect.props ?? {});

  return (
    <div style={s.effectEditor}>
      {/* 타입 헤더 */}
      <div style={s.effectHeader}>
        <span style={s.effectIcon}>{typeIcon(eff.type)}</span>
        <span style={s.effectType}>{eff.type}</span>
        <span style={s.effectId}>{eff.id}</span>
      </div>

      {/* 타이밍 */}
      <div style={s.group}>
        <div style={s.groupTitle}>타이밍</div>
        <Field
          label="startFrame"
          type="number"
          min={0}
          value={eff.startFrame}
          onChange={(v) => set("startFrame", Math.max(0, +v))}
        />
        <Field
          label="durationFrames"
          type="number"
          min={1}
          value={eff.durationFrames}
          onChange={(v) => set("durationFrames", Math.max(1, +v))}
        />
      </div>

      {/* 레이아웃 */}
      <div style={s.group}>
        <div style={s.groupTitle}>레이아웃 (video px)</div>
        <Field label="x" type="number" value={eff.x} onChange={(v) => set("x", +v)} />
        <Field label="y" type="number" value={eff.y} onChange={(v) => set("y", +v)} />
        <Field
          label="width"
          type="number"
          min={1}
          value={eff.width}
          onChange={(v) => set("width", Math.max(1, +v))}
        />
        <Field
          label="height"
          type="number"
          min={1}
          value={eff.height}
          onChange={(v) => set("height", Math.max(1, +v))}
        />
      </div>

      {/* Z-Index */}
      <div style={s.group}>
        <div style={s.groupTitle}>Z-Index (쌓임 순서)</div>
        <div style={s.field}>
          <label style={s.fieldLabel}>zIndex</label>
          <input
            type="range"
            min={-10}
            max={100}
            step={1}
            value={eff.zIndex ?? 0}
            onChange={(e) => set("zIndex", +e.target.value)}
            style={{ flex: 1, accentColor: "#e2b04a" }}
          />
          <span style={{ fontSize: 11, color: "#e2b04a", width: 28, textAlign: "right" }}>
            {eff.zIndex ?? 0}
          </span>
        </div>
      </div>

      {/* 사용자 Props (동적 UI) */}
      {propKeys.length > 0 && (
        <div style={s.group}>
          <div
            style={{ ...s.groupTitle, cursor: "pointer", userSelect: "none" }}
            onClick={() => setPropsOpen((v) => !v)}
          >
            {propsOpen ? "▾" : "▸"} Props ({propKeys.length})
          </div>

          {propsOpen &&
            propKeys.map((k) => {
              const val = effect.props![k];

              if (isColorProp(k)) {
                return (
                  <div key={k} style={{ position: "relative" }}>
                    <ColorPicker
                      label={k}
                      value={typeof val === "string" ? val : "#888888"}
                      onChange={(hex) => setProp(k, hex)}
                    />
                  </div>
                );
              }

              if (isFileProp(k)) {
                return (
                  <div key={k} style={s.field}>
                    <label style={s.fieldLabel}>{k}</label>
                    <input
                      style={{ ...s.input, fontFamily: "monospace", fontSize: 10 }}
                      type="text"
                      value={String(val ?? "")}
                      placeholder="경로 또는 파일명"
                      onChange={(e) => setProp(k, e.target.value)}
                    />
                  </div>
                );
              }

              // 숫자 또는 텍스트
              const isNum = typeof val === "number";
              return (
                <Field
                  key={k}
                  label={k}
                  type={isNum ? "number" : "text"}
                  value={String(val ?? "")}
                  onChange={(v) => setProp(k, isNum ? +v : v)}
                />
              );
            })}
        </div>
      )}
    </div>
  );
}

// ── EditPanel 메인 ────────────────────────────────────────────────────────
export default function EditPanel({
  plan,
  loading,
  saving,
  selectedSlideIdx,
  selectedEffectId,
  onSlideSelect,
  onEffectSelect,
  onSlideChange,
  onSave,
  onReset,
}: EditPanelProps) {
  const currentSlide = plan?.slides[selectedSlideIdx];
  const selectedEffect = currentSlide?.effects.find((e) => e.id === selectedEffectId) ?? null;

  const handleSlideField = (key: keyof Slide, val: unknown) => {
    if (!currentSlide) return;
    onSlideChange(selectedSlideIdx, { ...currentSlide, [key]: val });
  };

  const handleEffectUpdate = (updated: Effect) => {
    if (!currentSlide) return;
    onSlideChange(selectedSlideIdx, {
      ...currentSlide,
      effects: currentSlide.effects.map((e) => (e.id === updated.id ? updated : e)),
    });
  };

  // Z-index 조작: 한 칸 올리기/내리기
  const moveZ = (effectId: string, dir: 1 | -1) => {
    if (!currentSlide) return;
    const effects = currentSlide.effects.map((e) =>
      e.id === effectId ? { ...e, zIndex: (e.zIndex ?? 0) + dir } : e
    );
    onSlideChange(selectedSlideIdx, { ...currentSlide, effects });
  };

  return (
    <div style={s.panel}>
      {/* 헤더 */}
      <div style={s.panelHeader}>
        <span>속성 패널</span>
        <button style={s.iconBtn} onClick={onReset} title="새로고침 (되돌리기)">
          ↺
        </button>
      </div>

      {loading ? (
        <div style={s.centerHint}>기획안 로드 중…</div>
      ) : !plan ? (
        <div style={s.centerHint}>
          기획안이 없습니다.
          <br />
          서버 연결 확인
        </div>
      ) : (
        <div style={s.body}>
          {/* ── 슬라이드 목록 ── */}
          <div style={s.section}>
            <div style={s.sectionTitle}>슬라이드 ({plan.slides.length})</div>
            <div style={s.slideList}>
              {plan.slides.map((sl, i) => (
                <button
                  key={sl.id ?? i}
                  style={{ ...s.slideBtn, ...(i === selectedSlideIdx ? s.slideBtnActive : {}) }}
                  onClick={() => {
                    onSlideSelect(i);
                    onEffectSelect("");
                  }}
                >
                  <span style={{ fontWeight: 600 }}>S{i + 1}</span>
                  <span style={{ fontSize: 10, opacity: 0.65 }}>{sl.durationFrames}f</span>
                  {sl.effects.length > 0 && <span style={s.fxBadge}>{sl.effects.length} FX</span>}
                </button>
              ))}
            </div>
          </div>

          {/* ── 슬라이드 기본 속성 ── */}
          {currentSlide && (
            <div style={s.section}>
              <div style={s.sectionTitle}>슬라이드 {selectedSlideIdx + 1}</div>
              <Field
                label="durationFrames"
                type="number"
                min={1}
                value={currentSlide.durationFrames}
                onChange={(v) => handleSlideField("durationFrames", Math.max(1, +v))}
              />
            </div>
          )}

          {/* ── Effect 목록 ── */}
          {currentSlide && currentSlide.effects.length > 0 && (
            <div style={s.section}>
              <div style={s.sectionTitle}>FX 목록</div>
              <div style={s.effectList}>
                {[...currentSlide.effects]
                  .sort((a, b) => (b.zIndex ?? 0) - (a.zIndex ?? 0))
                  .map((eff) => (
                    <div
                      key={eff.id}
                      style={{
                        ...s.effectItem,
                        ...(eff.id === selectedEffectId ? s.effectItemActive : {}),
                      }}
                      onClick={() => onEffectSelect(eff.id)}
                    >
                      <span style={s.effectItemIcon}>{typeIcon(eff.type)}</span>
                      <span style={s.effectItemType}>{eff.type}</span>
                      <span style={s.effectItemId}>{eff.id}</span>
                      {/* Z 조작 버튼 */}
                      <div style={{ marginLeft: "auto", display: "flex", gap: 2 }}>
                        <button
                          style={s.zBtn}
                          onClick={(e) => {
                            e.stopPropagation();
                            moveZ(eff.id, 1);
                          }}
                          title="Z 올리기"
                        >
                          ↑
                        </button>
                        <button
                          style={s.zBtn}
                          onClick={(e) => {
                            e.stopPropagation();
                            moveZ(eff.id, -1);
                          }}
                          title="Z 내리기"
                        >
                          ↓
                        </button>
                      </div>
                    </div>
                  ))}
              </div>
            </div>
          )}

          {/* ── 선택된 Effect 편집 ── */}
          {selectedEffect && (
            <div style={s.section}>
              <div style={s.sectionTitle}>Effect 편집</div>
              <EffectEditor effect={selectedEffect} onChange={handleEffectUpdate} />
            </div>
          )}

          {/* 선택 안내 */}
          {currentSlide && currentSlide.effects.length > 0 && !selectedEffect && (
            <div style={{ ...s.centerHint, flex: "none", padding: "12px 16px" }}>
              캔버스에서 FX를 클릭하거나
              <br />위 목록에서 선택하세요
            </div>
          )}
        </div>
      )}

      {/* ── 액션 바 ── */}
      {plan && (
        <div style={s.actionBar}>
          <button style={{ ...s.btn, ...s.btnSecondary }} onClick={onReset} disabled={loading}>
            되돌리기
          </button>
          <button
            style={{ ...s.btn, ...s.btnPrimary, opacity: saving ? 0.6 : 1 }}
            onClick={onSave}
            disabled={saving}
          >
            {saving ? "저장 중…" : "✔ 반영"}
          </button>
        </div>
      )}
    </div>
  );
}

// ── 스타일 ────────────────────────────────────────────────────────────────
const s: Record<string, React.CSSProperties> = {
  panel: {
    width: 300,
    flex: 1,
    minHeight: 0,
    background: "#16213e",
    borderLeft: "1px solid #0f3460",
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
  },
  panelHeader: {
    padding: "12px 14px",
    borderBottom: "1px solid #0f3460",
    fontSize: 11,
    fontWeight: 700,
    color: "#7ec8e3",
    textTransform: "uppercase",
    letterSpacing: "0.5px",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
  },
  iconBtn: {
    background: "none",
    border: "none",
    color: "#4a6a8a",
    cursor: "pointer",
    fontSize: 16,
    padding: "0 4px",
    lineHeight: 1,
  },
  body: {
    flex: 1,
    minHeight: 0,
    overflowY: "auto",
    display: "flex",
    flexDirection: "column",
  },
  centerHint: {
    flex: 1,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 12,
    color: "#3a4a6a",
    textAlign: "center",
    padding: 24,
    lineHeight: 1.6,
  },
  section: { borderBottom: "1px solid #0a1828", padding: "10px 12px" },
  sectionTitle: {
    fontSize: 10,
    fontWeight: 700,
    color: "#e2b04a",
    textTransform: "uppercase",
    letterSpacing: "0.5px",
    marginBottom: 7,
  },
  slideList: { display: "flex", flexDirection: "column", gap: 3 },
  slideBtn: {
    display: "flex",
    alignItems: "center",
    gap: 7,
    padding: "5px 8px",
    background: "#1e2a4a",
    border: "1px solid #1a3a5a",
    borderRadius: 3,
    color: "#c0d0e0",
    fontSize: 11,
    cursor: "pointer",
    textAlign: "left",
  },
  slideBtnActive: { background: "#0f3460", borderColor: "#e2b04a", color: "#e2b04a" },
  fxBadge: {
    marginLeft: "auto",
    fontSize: 9,
    background: "#1a4a2a",
    color: "#4caf50",
    padding: "1px 5px",
    borderRadius: 8,
    border: "1px solid #2a6a3a",
  },
  effectList: { display: "flex", flexDirection: "column", gap: 2 },
  effectItem: {
    display: "flex",
    alignItems: "center",
    gap: 5,
    padding: "4px 7px",
    background: "#1a2030",
    border: "1px solid #1a2840",
    borderRadius: 3,
    cursor: "pointer",
    fontSize: 11,
  },
  effectItemActive: { background: "#0f2840", borderColor: "#e2b04a" },
  effectItemIcon: { fontSize: 12 },
  effectItemType: { fontSize: 11, fontWeight: 600, color: "#7ec8e3" },
  effectItemId: { fontSize: 9, color: "#3a5a7a", fontFamily: "monospace" },
  zBtn: {
    background: "#0f1a28",
    border: "1px solid #1a3040",
    borderRadius: 2,
    color: "#5a8aaa",
    cursor: "pointer",
    fontSize: 10,
    padding: "0 3px",
    lineHeight: "16px",
  },
  effectEditor: { display: "flex", flexDirection: "column", gap: 0 },
  effectHeader: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    marginBottom: 8,
  },
  effectIcon: { fontSize: 14 },
  effectType: {
    fontSize: 11,
    fontWeight: 700,
    color: "#7ec8e3",
    background: "#0f2030",
    padding: "1px 6px",
    borderRadius: 3,
  },
  effectId: { fontSize: 9, color: "#3a5a7a", fontFamily: "monospace" },
  group: { marginBottom: 8 },
  groupTitle: {
    fontSize: 9,
    fontWeight: 700,
    color: "#4a6a8a",
    textTransform: "uppercase",
    letterSpacing: "0.4px",
    marginBottom: 5,
  },
  field: { display: "flex", alignItems: "center", gap: 6, marginBottom: 4 },
  fieldLabel: {
    fontSize: 10,
    color: "#5a7a9a",
    width: 100,
    flexShrink: 0,
    fontFamily: "monospace",
  },
  input: {
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
  actionBar: {
    padding: "10px 12px",
    borderTop: "1px solid #0f3460",
    display: "flex",
    gap: 8,
    flexShrink: 0,
  },
  btn: {
    flex: 1,
    padding: "8px 0",
    border: "none",
    borderRadius: 4,
    fontSize: 12,
    fontWeight: 600,
    cursor: "pointer",
  },
  btnPrimary: { background: "#e2b04a", color: "#1a1a2e" },
  btnSecondary: { background: "#0f3460", color: "#7ec8e3" },
};
