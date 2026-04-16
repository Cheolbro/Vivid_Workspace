/**
 * VividStudio.tsx  — Phase 3
 * 상태 소유자(State Owner): plan, selectedSlideIdx, selectedEffectId
 *
 * 레이아웃:
 *   ┌─── Header ────────────────────────────────────────────┐
 *   │ Preview Area (SlideCanvas)       │ EditPanel (우측)   │
 *   └─── Footer ────────────────────────────────────────────┘
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { Effect, RemotionPlan, ServerStatus, Slide } from "./types";
import AIChatPanel from "./AIChatPanel";
import EditPanel from "./EditPanel";
import MiniTimeline from "./MiniTimeline";
import SlideCanvas from "./SlideCanvas";

type RightTab = "edit" | "chat";

// ── 토스트 ─────────────────────────────────────────────────────────────────
interface ToastItem {
  id: number;
  msg: string;
  type: "success" | "error" | "info";
}

function Toast({ items }: { items: ToastItem[] }) {
  return (
    <div
      style={{
        position: "fixed",
        bottom: 32,
        left: "50%",
        transform: "translateX(-50%)",
        zIndex: 9999,
        display: "flex",
        flexDirection: "column",
        gap: 8,
        alignItems: "center",
      }}
    >
      {items.map((t) => (
        <div
          key={t.id}
          style={{
            padding: "9px 18px",
            borderRadius: 6,
            fontSize: 12,
            fontWeight: 600,
            color: "#fff",
            background:
              t.type === "success" ? "#2e7d32" : t.type === "error" ? "#b71c1c" : "#1565c0",
            boxShadow: "0 4px 12px rgba(0,0,0,0.5)",
            whiteSpace: "nowrap",
          }}
        >
          {t.msg}
        </div>
      ))}
    </div>
  );
}

function useToast() {
  const [items, setItems] = useState<ToastItem[]>([]);
  const cnt = useRef(0);
  const push = useCallback((msg: string, type: ToastItem["type"] = "info", ms = 3000) => {
    const id = ++cnt.current;
    setItems((p) => [...p, { id, msg, type }]);
    setTimeout(() => setItems((p) => p.filter((t) => t.id !== id)), ms);
  }, []);
  return { items, push };
}

// ── 메인 컴포넌트 ──────────────────────────────────────────────────────────
export default function VividStudio() {
  // ── 상태 ────────────────────────────────────────────────────────────────
  const [plan, setPlan] = useState<RemotionPlan | null>(null);
  const [selectedSlideIdx, setSelectedSlideIdx] = useState(0);
  const [selectedEffectId, setSelectedEffectId] = useState<string | null>(null);
  const [currentFrame, setCurrentFrame] = useState(0);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [serverStatus, setServerStatus] = useState<ServerStatus | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [now, setNow] = useState(() => new Date().toLocaleTimeString());
  const [rightTab, setRightTab] = useState<RightTab>("edit");
  const { items: toasts, push: pushToast } = useToast();

  // 시계
  useEffect(() => {
    const t = setInterval(() => setNow(new Date().toLocaleTimeString()), 1000);
    return () => clearInterval(t);
  }, []);

  // 서버 헬스체크
  const checkServer = useCallback(async () => {
    try {
      const r = await fetch("/api/status");
      setServerStatus(await r.json());
    } catch {
      setServerStatus({ ok: false, project_dir: null });
    }
  }, []);

  useEffect(() => {
    checkServer();
    const t = setInterval(checkServer, 5000);
    return () => clearInterval(t);
  }, [checkServer]);

  // ── 기획안 로드 ────────────────────────────────────────────────────────
  const fetchPlan = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch("/api/plan");
      if (!r.ok) {
        const e = await r.json();
        pushToast(`로드 실패: ${e.detail ?? r.status}`, "error");
        return;
      }
      const data: RemotionPlan = await r.json();
      setPlan(data);
      setSelectedSlideIdx(0);
      setSelectedEffectId(null);
      pushToast("기획안 로드 완료", "success", 2000);
    } catch (e) {
      pushToast(`네트워크 오류: ${(e as Error).message}`, "error");
    } finally {
      setLoading(false);
    }
  }, [pushToast]);

  useEffect(() => {
    fetchPlan();
  }, [fetchPlan]);

  // ── 슬라이드 변경 (EditPanel에서 호출) ────────────────────────────────
  // 슬라이드 전환 시 currentFrame 리셋
  const handleSlideSelect = useCallback((idx: number) => {
    setSelectedSlideIdx(idx);
    setCurrentFrame(0);
  }, []);

  const handleSlideChange = useCallback((idx: number, updated: Slide) => {
    setPlan((prev) => {
      if (!prev) return prev;
      const slides = [...prev.slides];
      slides[idx] = updated;
      return { ...prev, slides };
    });
  }, []);

  // ── Effect 위치 변경 (SlideCanvas 드래그에서 호출) ─────────────────────
  const handleEffectChange = useCallback(
    (effectId: string, updated: Effect) => {
      setPlan((prev) => {
        if (!prev) return prev;
        const slides = prev.slides.map((sl, i) => {
          if (i !== selectedSlideIdx) return sl;
          return {
            ...sl,
            effects: sl.effects.map((e) => (e.id === effectId ? updated : e)),
          };
        });
        return { ...prev, slides };
      });
    },
    [selectedSlideIdx]
  );

  // ── Effect 선택 ────────────────────────────────────────────────────────
  // 객체 선택 시 프레임 이동 방지 (Auto-jump 제거)
  const handleEffectSelect = useCallback((id: string) => {
    setSelectedEffectId(id || null);
  }, []);

  // ── 반영 (POST /api/plan) ──────────────────────────────────────────────
  const handleSave = useCallback(async () => {
    if (!plan) return;
    setSaving(true);
    try {
      const r = await fetch("/api/plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(plan),
      });
      const data = await r.json();
      if (!r.ok) {
        pushToast(`저장 실패: ${data.detail ?? r.status}`, "error");
        return;
      }
      setSavedAt(new Date().toLocaleTimeString());
      pushToast(`설계도 업데이트 완료! (백업: ${data.backup})`, "success");
    } catch (e) {
      pushToast(`저장 오류: ${(e as Error).message}`, "error");
    } finally {
      setSaving(false);
    }
  }, [plan, pushToast]);

  // ── AI 채팅: plan_update 수신 ────────────────────────────────────────
  const handlePlanUpdate = useCallback(
    (newPlan: RemotionPlan, summary: string) => {
      setPlan(newPlan);
      pushToast(`AI 수정 적용: ${summary}`, "info");
    },
    [pushToast]
  );

  // ── 현재 슬라이드 ────────────────────────────────────────────────────
  const currentSlide = plan?.slides[selectedSlideIdx];
  const projectName = serverStatus?.project_dir?.split(/[\\/]/).pop();

  return (
    <div style={s.root}>
      {/* ── 헤더 ── */}
      <header style={s.header}>
        <div style={s.headerLeft}>
          <div style={{ ...s.dot, background: serverStatus?.ok ? "#4caf50" : "#ff5252" }} />
          <span style={s.title}>VIVID Studio</span>
          <span style={s.badge}>Phase 4 — Timeline</span>
        </div>
        <div style={s.headerRight}>
          {projectName && <span style={s.projectLabel}>📂 {projectName}</span>}
          {savedAt && <span style={s.savedLabel}>✔ 저장됨 {savedAt}</span>}
          {!serverStatus?.ok && <span style={s.warnLabel}>⚠ 서버 없음</span>}
        </div>
      </header>

      {/* ── 메인 ── */}
      <main style={s.main}>
        {/* 상단: 캔버스 + 속성 패널 */}
        <div style={s.upperArea}>
          {/* 미리보기 / 캔버스 */}
          <div style={s.previewArea}>
            {loading ? (
              <div style={s.centerHint}>기획안 로드 중…</div>
            ) : !plan ? (
              <div style={s.centerHint}>
                기획안이 없습니다.
                <br />
                <button style={s.retryBtn} onClick={fetchPlan}>
                  다시 시도
                </button>
              </div>
            ) : !currentSlide ? (
              <div style={s.centerHint}>슬라이드가 없습니다.</div>
            ) : (
              <SlideCanvas
                slide={currentSlide}
                currentFrame={currentFrame}
                selectedEffectId={selectedEffectId}
                onEffectSelect={handleEffectSelect}
                onEffectChange={handleEffectChange}
              />
            )}

            {/* Remotion Studio 링크 */}
            <div style={s.studioLink}>
              Remotion Studio →{" "}
              <a
                href="http://localhost:3000"
                target="_blank"
                rel="noreferrer"
                style={{ color: "#e2b04a" }}
              >
                http://localhost:3000
              </a>
            </div>
          </div>

          {/* ── 우측 패널 (탭 전환) ── */}
          <div style={s.rightPanel}>
            {/* 탭 헤더 */}
            <div style={s.tabBar}>
              <button
                style={{ ...s.tab, ...(rightTab === "edit" ? s.tabActive : {}) }}
                onClick={() => setRightTab("edit")}
              >
                속성
              </button>
              <button
                style={{ ...s.tab, ...(rightTab === "chat" ? s.tabActive : {}) }}
                onClick={() => setRightTab("chat")}
              >
                ✨ AI 채팅
              </button>
            </div>

            {/* 탭 콘텐츠 — display:none으로 숨김(unmount 방지 → 채팅 이력 유지) */}
            <div style={{ ...s.tabContent, display: rightTab === "edit" ? "flex" : "none" }}>
              <EditPanel
                plan={plan}
                loading={loading}
                saving={saving}
                selectedSlideIdx={selectedSlideIdx}
                selectedEffectId={selectedEffectId}
                onSlideSelect={handleSlideSelect}
                onEffectSelect={handleEffectSelect}
                onSlideChange={handleSlideChange}
                onSave={handleSave}
                onReset={fetchPlan}
              />
            </div>
            <div style={{ ...s.tabContent, display: rightTab === "chat" ? "flex" : "none" }}>
              <AIChatPanel plan={plan} onPlanUpdate={handlePlanUpdate} />
            </div>
          </div>
        </div>

        {/* 하단: MiniTimeline */}
        {currentSlide && (
          <MiniTimeline
            slide={currentSlide}
            selectedEffectId={selectedEffectId}
            onEffectSelect={handleEffectSelect}
            onEffectChange={handleEffectChange}
            currentFrame={currentFrame}
            onFrameChange={setCurrentFrame}
          />
        )}
      </main>

      {/* ── 푸터 ── */}
      <footer style={s.footer}>
        <span>VIVID Studio v0.5 · Phase 5</span>
        <span style={{ color: "#3a5a7a" }}>API: 127.0.0.1:8000 · {now}</span>
      </footer>

      <Toast items={toasts} />
    </div>
  );
}

// ── 스타일 ────────────────────────────────────────────────────────────────
const s: Record<string, React.CSSProperties> = {
  root: {
    height: "100vh",
    display: "flex",
    flexDirection: "column",
    fontFamily: "'Segoe UI', system-ui, sans-serif",
    background: "#1a1a2e",
    color: "#e0e0e0",
  },
  header: {
    background: "#16213e",
    borderBottom: "1px solid #0f3460",
    padding: "10px 20px",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    flexShrink: 0,
  },
  headerLeft: { display: "flex", alignItems: "center", gap: 12 },
  headerRight: { display: "flex", alignItems: "center", gap: 12 },
  dot: { width: 8, height: 8, borderRadius: "50%", flexShrink: 0 },
  title: { fontSize: 15, fontWeight: 700, color: "#e2b04a", letterSpacing: "0.5px" },
  badge: {
    fontSize: 10,
    background: "#0f3460",
    color: "#7ec8e3",
    padding: "2px 8px",
    borderRadius: 10,
    border: "1px solid #1a4a7a",
  },
  projectLabel: { fontSize: 11, color: "#7ec8e3" },
  savedLabel: { fontSize: 11, color: "#4caf50" },
  warnLabel: { fontSize: 11, color: "#ff5252" },
  main: { flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" },
  upperArea: { flex: 1, display: "flex", overflow: "hidden" },
  previewArea: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    background: "#0d0d1a",
    gap: 12,
    overflow: "auto",
    padding: 16,
  },
  centerHint: {
    fontSize: 13,
    color: "#3a4a6a",
    textAlign: "center",
    lineHeight: 1.8,
  },
  retryBtn: {
    marginTop: 8,
    padding: "6px 16px",
    background: "#0f3460",
    border: "1px solid #1a4a7a",
    borderRadius: 4,
    color: "#7ec8e3",
    cursor: "pointer",
    fontSize: 12,
  },
  studioLink: { fontSize: 11, color: "#2a3a5a", marginTop: 4 },
  // ── 우측 패널 (탭) ──
  rightPanel: {
    width: 300,
    flexShrink: 0,
    display: "flex",
    flexDirection: "column",
    borderLeft: "1px solid #0f3460",
    background: "#16213e",
    overflow: "hidden",
  },
  tabBar: {
    display: "flex",
    borderBottom: "1px solid #0f3460",
    flexShrink: 0,
  },
  tab: {
    flex: 1,
    padding: "8px 0",
    background: "none",
    border: "none",
    borderBottom: "2px solid transparent",
    color: "#4a6a8a",
    fontSize: 11,
    fontWeight: 600,
    cursor: "pointer",
    letterSpacing: "0.3px",
  },
  tabActive: {
    color: "#e2b04a",
    borderBottom: "2px solid #e2b04a",
    background: "rgba(226,176,74,0.05)",
  },
  tabContent: {
    flex: 1,
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
  },
  footer: {
    background: "#0f1a30",
    borderTop: "1px solid #0f3460",
    padding: "5px 20px",
    fontSize: 10,
    color: "#3a4a6a",
    display: "flex",
    justifyContent: "space-between",
    flexShrink: 0,
  },
};
