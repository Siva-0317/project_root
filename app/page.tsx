// app/page.tsx
"use client";
import { useEffect, useRef, useState } from "react";
declare const process: { env: { NEXT_PUBLIC_WS_URL?: string } };

type Msg = { role: "user"|"assistant"; text: string };

export default function Home() {
  const [reg, setReg] = useState("");
  const [name, setName] = useState<string|undefined>();
  const [input, setInput] = useState("");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [streaming, setStreaming] = useState(false);
  const wsRef = useRef<WebSocket|null>(null);
  const mediaRef = useRef<MediaRecorder|null>(null);
  const chunksRef = useRef<BlobPart[]>([]);

  async function doLogin() {
    const r = await fetch("/api/login", {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ reg_no: reg })
    });
    const j = await r.json();
    if (j.ok) setName(j.name);
    else alert(j.msg || "Login failed");
  }

  useEffect(() => {
    if (!name) return;
    const wsUrl = process.env.NEXT_PUBLIC_WS_URL || "wss://YOUR_BACKEND/ws/chat";
    wsRef.current = new WebSocket(wsUrl);
    wsRef.current.onmessage = (ev) => {
      const m = JSON.parse(ev.data);
      if (m.event === "token") {
        setStreaming(true);
        setMsgs(prev => {
          const last = prev[prev.length-1];
          if (last && last.role === "assistant") {
            const merged = prev.slice(0,-1);
            const s = last.text + m.text;
            speakChunk(m.text);
            return [...merged, { role:"assistant", text: s }];
          }
          speakChunk(m.text);
          return [...prev, { role:"assistant", text: m.text }];
        });
      }
      if (m.event === "done") setStreaming(false);
    };
    return () => wsRef.current?.close();
  }, [name]);

  function sendPrompt(text: string) {
    if (!wsRef.current) return;
    setMsgs(prev => [...prev, { role:"user", text }, { role:"assistant", text: "" }]);
    wsRef.current.send(JSON.stringify({
      reg_no: reg,
      content: text,
      model: "llama-3.2-3b-instruct",
      system: "You are JUNE, the library assistant for Easwari Engineering College. Reply clearly and concisely; provide links if asked."
    }));
  }

  async function startMic() {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const rec = new MediaRecorder(stream, { mimeType: "audio/webm" });
    chunksRef.current = [];
    rec.ondataavailable = (e) => chunksRef.current.push(e.data);
    rec.onstop = async () => {
      const blob = new Blob(chunksRef.current, { type: "audio/webm" });
      const fd = new FormData(); fd.append("file", blob, "audio.webm");
      const r = await fetch("/api/transcribe", { method: "POST", body: fd });
      const j = await r.json();
      if (j.text) {
        setInput(j.text);
        sendPrompt(j.text);
      }
    };
    rec.start(300);
    mediaRef.current = rec;
  }

  function stopMic() {
    mediaRef.current?.stop();
    mediaRef.current = null;
  }

  function speakChunk(text: string) {
    const utt = new SpeechSynthesisUtterance(text);
    speechSynthesis.speak(utt);
  }

  return (
    <main className="min-h-screen grid grid-rows-[auto,1fr,auto] bg-amber-50">
      <header className="px-6 py-4 bg-white shadow">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <div>
            <h2 className="text-xl font-semibold text-amber-700">JUNE — Library Assistant</h2>
            <p className="text-xs text-gray-600">{name ? `Logged in as ${name} (${reg})` : "Sign in"}</p>
          </div>
          {!name ? (
            <div className="flex gap-2">
              <input className="border rounded p-2" placeholder="Register number" value={reg} onChange={e=>setReg(e.target.value)} />
              <button onClick={doLogin} className="px-3 py-2 bg-amber-600 text-white rounded">Login</button>
            </div>
          ) : (
            <form action="/api/logout" method="post">
              <button className="px-3 py-2 border rounded">Logout</button>
            </form>
          )}
        </div>
      </header>

      <section className="max-w-4xl mx-auto w-full p-4">
        <div className="h-[70vh] overflow-y-auto bg-white shadow rounded p-4">
          {msgs.map((m, i) => (
            <div key={i} className={`my-2 ${m.role==="user"?"text-right":""}`}>
              <span className={`inline-block px-3 py-2 rounded ${m.role==="user"?"bg-amber-200":"bg-amber-100"}`}>
                {m.text}
              </span>
            </div>
          ))}
        </div>
      </section>

      <footer className="max-w-4xl mx-auto w-full p-4 grid grid-cols-[1fr_auto_auto] gap-2">
        <input className="border rounded p-2" placeholder="Ask about library services…" value={input}
               onChange={e=>setInput(e.target.value)} onKeyDown={(e)=> e.key==="Enter" && (sendPrompt(input), setInput(""))} />
        <button onClick={()=> (sendPrompt(input), setInput(""))} disabled={!input || streaming}
                className="px-4 py-2 bg-amber-600 text-white rounded">Send</button>
        <div className="flex gap-1">
          <button onMouseDown={startMic} onMouseUp={stopMic}
                  className="px-3 py-2 border rounded">Hold to Speak</button>
        </div>
      </footer>
    </main>
  );
}
