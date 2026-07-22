import { useRef, useState } from "react";
import "./App.css";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

function apiUrl(path) {
  return `${API_BASE_URL}${path}`;
}

function getSessionId() {
  try {
    const existing = localStorage.getItem("campus-agent-session");
    if (existing) return existing;

    const created =
      crypto?.randomUUID?.() ||
      `campus-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    localStorage.setItem("campus-agent-session", created);
    return created;
  } catch {
    return `campus-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }
}

async function requestNormalChat(message, sessionId) {
  const res = await fetch(apiUrl("/api/chat"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      message,
      session_id: sessionId,
    }),
  });

  if (!res.ok) {
    throw new Error("后端普通聊天接口暂时不可用");
  }

  const data = await res.json();
  return data.reply || "后端没有返回可展示的回答。";
}

function App() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);

  const chatRef = useRef(null);

  // =========================
  // 🚀 发送消息（流式）
  // =========================
  const sendMessage = async () => {
    if (!input.trim()) return;

    const userMsg = {
      role: "user",
      content: input,
    };

    const currentInput = input;
    const sessionId = getSessionId();

    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    setMessages((prev) => [
      ...prev,
      { role: "assistant", content: "" },
    ]);

    try {
      const res = await fetch(apiUrl("/api/chat_stream"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          message: currentInput,
          session_id: sessionId,
        }),
      });

      if (!res.ok) {
        throw new Error("后端服务暂时不可用");
      }

      if (!res.body?.getReader) {
        const reply = await requestNormalChat(currentInput, sessionId);
        setMessages((prev) => {
          const newMsgs = [...prev];
          newMsgs[newMsgs.length - 1].content = reply;
          return newMsgs;
        });
        setLoading(false);
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder("utf-8");

      let fullText = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split("\n");

        for (let line of lines) {
          if (line.startsWith("data: ")) {
            const data = line.replace("data: ", "");

            if (data.includes("[DONE]")) {
              setLoading(false);
              return;
            }

            try {
              const json = JSON.parse(data);
              if (json.sources) continue;

              fullText += json.token;

              setMessages((prev) => {
                const newMsgs = [...prev];
                newMsgs[newMsgs.length - 1].content = fullText;
                return newMsgs;
              });

              // 自动滚动
              chatRef.current?.scrollTo({
                top: chatRef.current.scrollHeight,
                behavior: "smooth",
              });
            } catch (err) {
              console.log("JSON parse error:", err);
            }
          }
        }
      }
    } catch (err) {
      console.error("请求失败:", err);
      setMessages((prev) => {
        const newMsgs = [...prev];
        newMsgs[newMsgs.length - 1].content = "连接后端失败，请确认后端服务已经启动。";
        return newMsgs;
      });
    }

    setLoading(false);
  };

  // =========================
  // 🎨 UI
  // =========================
  return (
    <div className="app-container">
      <div className="header">
        <img
          className="school-logo"
          src="/gcas-logo-transparent.png"
          alt="广州应用科技学院"
        />
      </div>

      <div className="chat-box" ref={chatRef}>
        {messages.length === 0 && (
          <div className="empty-state">
            <h1>广应科校园智能服务助手</h1>
            <p>可以闲聊、查天气、找新闻、回答校园资料问题</p>
          </div>
        )}

        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={`message ${
              msg.role === "user" ? "user" : "ai"
            }`}
          >
            <div className="bubble">{msg.content}</div>
          </div>
        ))}

        {loading && <div className="status">AI 正在思考...</div>}
      </div>

      <div className="input-box">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="请输入问题..."
          onKeyDown={(e) => {
            if (e.key === "Enter") sendMessage();
          }}
        />

        <button onClick={sendMessage}>发送</button>
      </div>
    </div>
  );
}

export default App;
