import { useState } from "react";
import axios from "axios";

const API_BASE = "http://127.0.0.1:8000";

function App() {
  const [files, setFiles] = useState([]);
  const [uploadStatus, setUploadStatus] = useState("");
  const [question, setQuestion] = useState("");
  const [loadingIngest, setLoadingIngest] = useState(false);
  const [loadingAsk, setLoadingAsk] = useState(false);
  const [sources, setSources] = useState([]);
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content:
        "Hi! Upload one or more PDFs on the left, click Ingest, then ask me anything about them.",
    },
  ]);

  const handleFileChange = (e) => {
    setFiles(Array.from(e.target.files || []));
  };

  const handleUpload = async () => {
    if (!files.length) {
      setUploadStatus("Please select at least one file.");
      return;
    }

    const formData = new FormData();
    files.forEach((file) => formData.append("files", file));

    try {
      setLoadingIngest(true);
      setUploadStatus("Ingesting documents...");
      const res = await axios.post(`${API_BASE}/ingest`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setUploadStatus(`✅ Ingested ${res.data.chunks} chunks.`);
    } catch (err) {
      console.error(err);
      setUploadStatus("❌ Error during ingestion. Check backend logs.");
    } finally {
      setLoadingIngest(false);
    }
  };

 const handleAsk = async () => {
  if (!question.trim()) return;

  // Keep a copy of the current question
  const currentQuestion = question.trim();

  // Clear the input immediately in the UI
  setQuestion("");

  const userMessage = { role: "user", content: currentQuestion };

  // Show user message right away
  setMessages((prev) => [...prev, userMessage]);

  try {
    setLoadingAsk(true);
    setSources([]); // clear previous sources

    const res = await axios.post(`${API_BASE}/ask`, {
      question: currentQuestion,   // use the saved value, not state
    });

    const answer = res.data.answer || "No answer returned.";
    const rawSources = res.data.sources || [];

    // ==== CLEAN + DEDUPE SOURCES HERE ====
    const seen = new Set();
    const cleanedSources = [];

    for (const src of rawSources) {
      const meta = src.metadata || {};

      // Normalize fields (backend might send in metadata or top-level)
      const sourceName = src.source || meta.source;
      const chunkIndex =
        src.chunk_index ??
        meta.chunk_index ??
        meta.chunkIndex ??
        null;
      const snippet = src.snippet || meta.snippet || "";

      // Skip entries with no file name
      if (!sourceName) continue;

      // Build dedupe key
      const key = `${sourceName}::${chunkIndex ?? ""}::${snippet}`;

      if (seen.has(key)) continue;
      seen.add(key);

      cleanedSources.push({
        ...src,
        source: sourceName,
        chunk_index: chunkIndex,
        snippet,
      });
    }
    // =====================================

    const assistantMessage = { role: "assistant", content: answer };

    setMessages((prev) => [...prev, assistantMessage]);
    setSources(cleanedSources);
  } catch (err) {
    console.error(err);
    const errMessage = {
      role: "assistant",
      content:
        "❌ Error getting an answer. Please check that the backend and Ollama are running.",
    };
    setMessages((prev) => [...prev, errMessage]);

    // (Optional) also ensure input is empty on error
    setQuestion("");
  } finally {
    setLoadingAsk(false);
  }
};

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleAsk();
    }
  };

  const handleNewChat = () => {
    setMessages([
      {
        role: "assistant",
        content:
          "New chat started. Ask me anything about the documents you've ingested.",
      },
    ]);
    setSources([]);
    setQuestion("");
  };

  return (
    
    <div className="h-full w-full bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 flex items-center justify-center">
      
      <div className="w-[95vw] h-[90vh] bg-slate-900/70 border border-slate-800/60 rounded-3xl shadow-2xl backdrop-blur-xl flex flex-col lg:flex-row overflow-hidden">
        {/* Left Panel */}
        <div className="w-full lg:w-1/3 border-b lg:border-b-0 lg:border-r border-slate-800/70 p-6 lg:p-8 flex flex-col gap-4">
          {/* Header */}
          <div className="flex items-center justify-between gap-3">
            <div>
              <h1 className="text-xl lg:text-2xl font-semibold text-slate-50 flex items-center gap-2">
                <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-emerald-500/20 text-emerald-400 font-bold">
                  R
                </span>
                Local RAG Chatbot
              </h1>
              {/* <p className="mt-1.5 text-xs text-slate-400">
                FastAPI · Chroma · sentence-transformers · Ollama (Llama 3) —
                running locally on your Mac.
              </p> */}
            </div>
            <button
              onClick={handleNewChat}
              className="hidden lg:inline-flex items-center rounded-xl border border-slate-700/80 bg-slate-900/80 px-3 py-1.5 text-xs font-medium text-slate-200 hover:border-emerald-500/70 hover:text-emerald-300 transition-colors"
            >
              New chat
            </button>
          </div>

          {/* Upload section */}
          <div className="mt-2 space-y-3">
            <h2 className="text-xs font-medium text-slate-200 uppercase tracking-wide">
              1. Upload documents
            </h2>

            <label className="flex flex-col items-center justify-center w-full h-32 border-2 border-dashed rounded-2xl cursor-pointer border-slate-700 hover:border-emerald-500/60 transition-colors bg-slate-900/60">
              <div className="flex flex-col items-center justify-center pt-4 pb-3 text-center">
                <p className="text-sm text-slate-300">
                  <span className="font-medium text-emerald-400">
                    Click to upload
                  </span>{" "}
                  or drag &amp; drop
                </p>
                <p className="text-xs text-slate-500 mt-1">
                  PDF or text files
                </p>
              </div>
              <input
                id="file-input"
                type="file"
                className="hidden"
                multiple
                onChange={handleFileChange}
              />
            </label>

            {files.length > 0 && (
              <div className="rounded-xl bg-slate-900/80 border border-slate-800 p-2 max-h-32 overflow-y-auto">
                <p className="text-xs font-medium text-slate-400 mb-1">
                  Selected files:
                </p>
                <ul className="space-y-0.5">
                  {files.map((file, idx) => (
                    <li key={idx} className="text-xs text-slate-300 truncate">
                      • {file.name}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <button
              onClick={handleUpload}
              disabled={loadingIngest || files.length === 0}
              className="mt-1 inline-flex w-full items-center justify-center rounded-xl bg-emerald-500 px-3 py-2.5 text-sm font-semibold text-slate-950 shadow-md shadow-emerald-500/30 hover:bg-emerald-400 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
            >
              {loadingIngest ? "Ingesting..." : "Ingest documents"}
            </button>

            {uploadStatus && (
              <p className="text-xs text-slate-300 mt-1">{uploadStatus}</p>
            )}
          </div>

          {/* Tips */}
          {/* <div className="mt-4 pt-3 border-t border-slate-800/70">
            <h2 className="text-xs font-medium text-slate-400 uppercase tracking-wide mb-1.5">
              Tips
            </h2>
            <ul className="text-xs text-slate-400 space-y-1.5 list-disc list-inside">
              <li>Ingest one or more PDFs before asking questions.</li>
              <li>Ask specific questions, e.g. “What are the key findings?”</li>
              <li>Answers are grounded in your uploaded documents.</li>
            </ul>
          </div> */}

          {/* Mobile new chat button */}
          <button
            onClick={handleNewChat}
            className="lg:hidden mt-3 inline-flex items-center justify-center rounded-xl border border-slate-700/80 bg-slate-900/90 px-3 py-2 text-xs font-medium text-slate-200 hover:border-emerald-500/70 hover:text-emerald-300 transition-colors"
          >
            New chat
          </button>
        </div>

        {/* Right Panel: Chat */}
        <div className="w-full lg:w-2/3 p-6 lg:p-8 flex flex-col">
          <h2 className="text-xs font-medium text-slate-200 uppercase tracking-wide mb-3">
            2. Chat with your documents
          </h2>

          {/* Messages */}
          <div className="flex-1 rounded-2xl bg-slate-950/40 border border-slate-800/70 p-4 overflow-y-auto space-y-3">
            {messages.map((msg, idx) => (
              <div
                key={idx}
                className={`flex ${
                  msg.role === "user" ? "justify-end" : "justify-start"
                }`}
              >
                <div
                  className={`max-w-[80%] rounded-2xl px-3 py-2 text-sm shadow-sm ${
                    msg.role === "user"
                      ? "bg-emerald-500 text-slate-950 rounded-br-sm"
                      : "bg-slate-800/90 text-slate-50 rounded-bl-sm"
                  }`}
                >
                  <p className="whitespace-pre-wrap">{msg.content}</p>
                </div>
              </div>
            ))}
            {loadingAsk && (
              <div className="flex justify-start">
                <div className="inline-flex items-center gap-2 rounded-2xl bg-slate-800/80 px-3 py-1.5 text-xs text-slate-300">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping" />
                  Thinking…
                </div>
              </div>
            )}
          </div>

          {/* Sources */}
          <div className="mt-3">
            <h3 className="text-xs font-medium text-slate-300 uppercase tracking-wide mb-1">
              Sources
            </h3>
            {sources.length === 0 ? (
              <p className="text-xs text-slate-500">
                No sources yet. Ask a question to see which document chunks were
                used.
              </p>
            ) : (
              <div className="grid gap-2 max-h-40 overflow-y-auto">
           {sources.map((src, idx) => (
  <div
    key={src.id ?? idx}
    className="rounded-xl border border-slate-800 bg-slate-900/70 px-3 py-2"
  >
    <div className="flex items-center justify-between gap-2 mb-1">
      <span className="text-xs font-semibold text-slate-200">
        Source {idx + 1}
      </span>
      <span className="text-[10px] text-slate-500">
        {src.source}
        {typeof src.chunk_index === "number" &&
          ` · chunk ${src.chunk_index}`}
      </span>
    </div>
    <p className="text-xs text-slate-300 line-clamp-3">
      {src.snippet}...
    </p>
  </div>
))}

              </div>
            )}
          </div>

          {/* Input */}
          <div className="mt-4 flex items-end gap-2">
            <div className="flex-1">
              <textarea
                rows={2}
                className="w-full rounded-2xl border border-slate-700 bg-slate-900/80 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/70 focus:border-emerald-500/60 resize-none"
                placeholder="Ask something about your documents… (Enter to send, Shift+Enter for new line)"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={handleKeyDown}
              />
            </div>
            <button
              onClick={handleAsk}
              disabled={loadingAsk || !question.trim()}
              className="inline-flex items-center justify-center rounded-2xl bg-emerald-500 px-4 py-2 text-sm font-semibold text-slate-950 shadow-md shadow-emerald-500/40 hover:bg-emerald-400 disabled:opacity-60 disabled:cursor-not-allowed transition-colors h-10"
            >
              {loadingAsk ? "Sending..." : "Send"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
