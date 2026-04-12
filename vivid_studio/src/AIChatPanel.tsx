/**
 * AIChatPanel.tsx — Phase 5
 * Gemini AI 채팅 패널
 *
 * 응답 타입별 렌더링:
 *   plan_update → "기획안 적용" 버튼 + 변경 요약
 *   tsx_code    → 코드 블록 + 복사 버튼 + 파일명
 *   text        → 일반 텍스트 버블
 *
 * 상태는 VividStudio가 소유하며, plan_update 시 onPlanUpdate 콜백으로 전달.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { RemotionPlan } from "./types";

// ── API 응답 타입 ──────────────────────────────────────────────────────────
interface PlanUpdateResponse {
  type: "plan_update";
  plan: RemotionPlan;
  summary: string;
}
interface TsxCodeResponse {
  type: "tsx_code";
  filename: string;
  code: string;
  summary: string;
}
interface TextResponse {
  type: "text";
  content: string;
}
type ChatResponse = PlanUpdateResponse | TsxCodeResponse | TextResponse;

// ── 메시지 타입 ────────────────────────────────────────────────────────────
type MessageRole = "user" | "assistant" | "system";
interface ChatMessage {
  id: number;
  role: MessageRole;
  text: string; // 화면 표시용 텍스트
  response?: ChatResponse; // assistant 전용 구조화 응답
}

// ── Props ──────────────────────────────────────────────────────────────────
interface AIChatPanelProps {
  plan: RemotionPlan | null;
  onPlanUpdate: (newPlan: RemotionPlan, summary: string) => void;
}

// ── 코드 블록 ──────────────────────────────────────────────────────────────
function CodeBlock({ filename, code }: { filename: string; code: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div style={s.codeBlock}>
      <div style={s.codeHeader}>
        <span style={s.codeFilename}>{filename}</span>
        <button style={s.copyBtn} onClick={handleCopy}>
          {copied ? "✔ 복사됨" : "📋 복사"}
        </button>
      </div>
      <pre style={s.codePre}>{code}</pre>
    </div>
  );
}

// ── 단일 메시지 버블 ────────────────────────────────────────────────────────
function MessageBubble({
  msg,
  onApplyPlan,
}: {
  msg: ChatMessage;
  onApplyPlan: (plan: RemotionPlan, summary: string) => void;
}) {
  const isUser = msg.role === "user";
  const isSys = msg.role === "system";

  if (isSys) {
    return <div style={s.sysBubble}>{msg.text}</div>;
  }

  return (
    <div style={{ ...s.bubbleRow, justifyContent: isUser ? "flex-end" : "flex-start" }}>
      {!isUser && <div style={s.avatar}>AI</div>}

      <div style={{ maxWidth: "85%", display: "flex", flexDirection: "column", gap: 6 }}>
        {/* 텍스트 버블 */}
        <div style={isUser ? s.userBubble : s.aiBubble}>{msg.text}</div>

        {/* plan_update 응답 */}
        {msg.response?.type === "plan_update" && (
          <div style={s.actionCard}>
            <div style={s.actionSummary}>📋 {msg.response.summary}</div>
            <button
              style={s.applyBtn}
              onClick={() =>
                onApplyPlan(
                  (msg.response as PlanUpdateResponse).plan,
                  (msg.response as PlanUpdateResponse).summary
                )
              }
            >
              기획안 적용
            </button>
          </div>
        )}

        {/* tsx_code 응답 */}
        {msg.response?.type === "tsx_code" && (
          <div>
            <div style={s.actionSummary}>✨ {msg.response.summary}</div>
            <CodeBlock
              filename={(msg.response as TsxCodeResponse).filename}
              code={(msg.response as TsxCodeResponse).code}
            />
            <div style={s.tsxHint}>
              💡 이 파일을 <code style={s.inlineCode}>shared_assets/shared_fx/</code>에 저장 후
              4단계에서 재업로드하면 자동 매칭됩니다.
            </div>
          </div>
        )}
      </div>

      {isUser && <div style={s.userAvatar}>나</div>}
    </div>
  );
}

// ── AIChatPanel 메인 ───────────────────────────────────────────────────────
export default function AIChatPanel({ plan, onPlanUpdate }: AIChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 0,
      role: "system",
      text: "Gemini AI 어시스턴트입니다. 기획안 수정, FX 코드 생성, 편집 방향 상담을 도와드립니다.",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const msgEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const idRef = useRef(1);

  // 자동 스크롤
  useEffect(() => {
    msgEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ── 전송 ────────────────────────────────────────────────────────────────
  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || loading) return;

    const userMsg: ChatMessage = { id: idRef.current++, role: "user", text };
    setMessages((p) => [...p, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, plan: plan ?? undefined }),
      });

      const data: ChatResponse = await res.json();

      if (!res.ok) {
        // FastAPI HTTPException → { detail: string }
        const errMsg = (data as unknown as { detail?: string }).detail ?? `HTTP ${res.status}`;
        setMessages((p) => [
          ...p,
          {
            id: idRef.current++,
            role: "system",
            text: `❌ 오류: ${errMsg}`,
          },
        ]);
        return;
      }

      // 표시용 텍스트 결정
      let displayText = "";
      if (data.type === "plan_update") {
        displayText = `기획안 수정안을 생성했습니다: ${data.summary}`;
      } else if (data.type === "tsx_code") {
        displayText = `TSX 코드를 생성했습니다: ${data.summary}`;
      } else {
        displayText = data.content;
      }

      setMessages((p) => [
        ...p,
        {
          id: idRef.current++,
          role: "assistant",
          text: displayText,
          response: data,
        },
      ]);
    } catch (e) {
      setMessages((p) => [
        ...p,
        {
          id: idRef.current++,
          role: "system",
          text: `❌ 네트워크 오류: ${(e as Error).message}`,
        },
      ]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  }, [input, loading, plan]);

  // Enter(단독) 전송, Shift+Enter 줄바꿈
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // plan_update 적용 → VividStudio로 위임
  const handleApplyPlan = (newPlan: RemotionPlan, summary: string) => {
    onPlanUpdate(newPlan, summary);
    setMessages((p) => [
      ...p,
      {
        id: idRef.current++,
        role: "system",
        text: `✔ 기획안 적용 완료: ${summary}. 좌측 캔버스를 확인하고 "반영" 버튼으로 저장하세요.`,
      },
    ]);
  };

  // 대화 초기화
  const handleClear = () => {
    setMessages([
      {
        id: idRef.current++,
        role: "system",
        text: "대화가 초기화되었습니다.",
      },
    ]);
  };

  // ── 렌더 ──────────────────────────────────────────────────────────────
  return (
    <div style={s.panel}>
      {/* 헤더 */}
      <div style={s.panelHeader}>
        <span>AI 채팅</span>
        <div style={{ display: "flex", gap: 6 }}>
          {!plan && <span style={{ fontSize: 9, color: "#ff5252" }}>기획안 없음</span>}
          <button style={s.iconBtn} onClick={handleClear} title="대화 초기화">
            ✕
          </button>
        </div>
      </div>

      {/* 메시지 목록 */}
      <div style={s.messageList}>
        {messages.map((msg) => (
          <MessageBubble key={msg.id} msg={msg} onApplyPlan={handleApplyPlan} />
        ))}

        {/* 로딩 인디케이터 */}
        {loading && (
          <div style={s.bubbleRow}>
            <div style={s.avatar}>AI</div>
            <div style={{ ...s.aiBubble, color: "#4a6a8a" }}>
              생각 중<span style={s.dots}>…</span>
            </div>
          </div>
        )}

        <div ref={msgEndRef} />
      </div>

      {/* 입력 영역 */}
      <div style={s.inputArea}>
        <textarea
          ref={inputRef}
          style={s.textarea}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={
            plan
              ? "편집 요청을 입력하세요… (Enter 전송, Shift+Enter 줄바꿈)"
              : "기획안을 먼저 업로드하세요."
          }
          disabled={loading}
          rows={3}
        />
        <button
          style={{
            ...s.sendBtn,
            opacity: !input.trim() || loading ? 0.5 : 1,
            cursor: !input.trim() || loading ? "not-allowed" : "pointer",
          }}
          onClick={handleSend}
          disabled={!input.trim() || loading}
        >
          ▶
        </button>
      </div>

      {/* 힌트 */}
      <div style={s.hint}>
        예: "슬라이드 2의 duration을 90f로 바꿔줘" · "새 flicker FX 코드 만들어줘"
      </div>
    </div>
  );
}

// ── 스타일 ────────────────────────────────────────────────────────────────
const s: Record<string, React.CSSProperties> = {
  panel: {
    width: 300,
    background: "#16213e",
    borderLeft: "1px solid #0f3460",
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
    flexShrink: 0,
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
    flexShrink: 0,
  },
  iconBtn: {
    background: "none",
    border: "none",
    color: "#4a6a8a",
    cursor: "pointer",
    fontSize: 13,
    padding: "0 3px",
  },
  messageList: {
    flex: 1,
    overflowY: "auto",
    padding: "10px 10px",
    display: "flex",
    flexDirection: "column",
    gap: 10,
  },
  bubbleRow: {
    display: "flex",
    gap: 6,
    alignItems: "flex-start",
  },
  avatar: {
    width: 24,
    height: 24,
    borderRadius: "50%",
    background: "#0f3460",
    color: "#7ec8e3",
    fontSize: 9,
    fontWeight: 700,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
  },
  userAvatar: {
    width: 24,
    height: 24,
    borderRadius: "50%",
    background: "#2a1a0a",
    color: "#e2b04a",
    fontSize: 9,
    fontWeight: 700,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
  },
  userBubble: {
    background: "#1a2a0a",
    border: "1px solid #2a4a1a",
    borderRadius: "12px 4px 12px 12px",
    padding: "8px 10px",
    fontSize: 11,
    color: "#c8e0a8",
    lineHeight: 1.5,
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
  },
  aiBubble: {
    background: "#0f1a2a",
    border: "1px solid #1a3040",
    borderRadius: "4px 12px 12px 12px",
    padding: "8px 10px",
    fontSize: 11,
    color: "#c0d4e8",
    lineHeight: 1.5,
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
  },
  sysBubble: {
    background: "#0a1020",
    border: "1px solid #1a2030",
    borderRadius: 4,
    padding: "6px 10px",
    fontSize: 10,
    color: "#4a6a8a",
    textAlign: "center",
    fontStyle: "italic",
    lineHeight: 1.5,
  },
  actionCard: {
    background: "#0d1a28",
    border: "1px solid #1a3040",
    borderRadius: 6,
    padding: "8px 10px",
    display: "flex",
    flexDirection: "column",
    gap: 6,
  },
  actionSummary: {
    fontSize: 10,
    color: "#7ec8e3",
    lineHeight: 1.4,
  },
  applyBtn: {
    padding: "5px 12px",
    background: "#e2b04a",
    border: "none",
    borderRadius: 4,
    color: "#1a1a2e",
    fontSize: 11,
    fontWeight: 700,
    cursor: "pointer",
    alignSelf: "flex-start",
  },
  codeBlock: {
    background: "#060c14",
    border: "1px solid #1a2a3a",
    borderRadius: 5,
    overflow: "hidden",
  },
  codeHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "4px 8px",
    background: "#0a1828",
    borderBottom: "1px solid #1a2a3a",
  },
  codeFilename: {
    fontSize: 10,
    color: "#7ec8e3",
    fontFamily: "monospace",
  },
  copyBtn: {
    background: "none",
    border: "1px solid #1a3040",
    borderRadius: 3,
    color: "#4a6a8a",
    fontSize: 9,
    cursor: "pointer",
    padding: "2px 6px",
  },
  codePre: {
    margin: 0,
    padding: "8px",
    fontSize: 9,
    color: "#8ab8d8",
    fontFamily: "monospace",
    overflowX: "auto",
    lineHeight: 1.5,
    maxHeight: 200,
    whiteSpace: "pre",
  },
  tsxHint: {
    fontSize: 9,
    color: "#3a5a7a",
    marginTop: 4,
    lineHeight: 1.5,
  },
  inlineCode: {
    background: "#0a1020",
    border: "1px solid #1a2a3a",
    borderRadius: 2,
    padding: "0 3px",
    fontSize: 9,
    color: "#7ec8e3",
    fontFamily: "monospace",
  },
  inputArea: {
    borderTop: "1px solid #0f3460",
    padding: "8px 10px",
    display: "flex",
    gap: 6,
    alignItems: "flex-end",
    flexShrink: 0,
  },
  textarea: {
    flex: 1,
    background: "#0f1a30",
    border: "1px solid #1a3a5a",
    borderRadius: 4,
    color: "#e0e0e0",
    padding: "6px 8px",
    fontSize: 11,
    resize: "none",
    outline: "none",
    fontFamily: "'Segoe UI', system-ui, sans-serif",
    lineHeight: 1.5,
  },
  sendBtn: {
    width: 32,
    height: 32,
    background: "#e2b04a",
    border: "none",
    borderRadius: 4,
    color: "#1a1a2e",
    fontSize: 13,
    fontWeight: 700,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
    transition: "opacity 0.15s",
  },
  hint: {
    fontSize: 9,
    color: "#2a3a5a",
    padding: "3px 10px 6px",
    lineHeight: 1.4,
    flexShrink: 0,
  },
  dots: { display: "inline-block", animation: "none" },
};
