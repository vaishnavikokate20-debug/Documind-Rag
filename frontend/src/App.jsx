
import { useState,useEffect } from "react";
import "./App.css";

const API_URL = "http://127.0.0.1:8000";

function App() {
  const [file, setFile] = useState(null);
  const [documentName, setDocumentName] = useState("");
  const [pdfHistory, setPdfHistory] = useState([]);
  useEffect(() => {
  async function fetchPdfHistory() {
    try {
      const response = await fetch(`${API_URL}/api/history`);
      const data = await response.json();

      if (!response.ok) {
        throw new Error("Could not load PDF history.");
      }

      setPdfHistory(data.history || []);
    } catch (err) {
      console.error("Failed to fetch PDF history:", err);
    }
  }

  fetchPdfHistory();
}, []);
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  
async function activatePdf(pdf) {
  setError("");

  try {
    const response = await fetch(
      `${API_URL}/api/history/${pdf.id}/activate`,
      {
        method: "POST",
      }
    );

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || "Could not activate this PDF.");
    }

    setDocumentName(data.filename || pdf.filename);
    setFile(null);
    setMessages([
      {
        role: "assistant",
        content: `I've activated "${data.filename || pdf.filename}". You can now ask questions about this PDF.`,
      },
    ]);
  } catch (err) {
    setError(err.message || "Could not connect to the backend.");
  }
}
  async function deletePdf(pdf, event) {
    event.stopPropagation();

    const confirmed = window.confirm(
      `Are you sure you want to delete "${pdf.filename}"?`
    );

    if (!confirmed) return;

    setError("");

    try {
      const response = await fetch(
        `${API_URL}/api/history/${pdf.id}`,
        {
          method: "DELETE",
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Could not delete this PDF.");
      }

      // Remove the deleted PDF from the history displayed in the UI.
      setPdfHistory((previous) =>
        previous.filter((item) => item.id !== pdf.id)
      );

      // Clear the displayed conversation if this was the active PDF.
      if (documentName === pdf.filename) {
        setDocumentName("");
        setMessages([]);
        setQuestion("");
      }
    } catch (err) {
      setError(err.message || "Could not connect to the backend.");
    }
  }


  async function uploadPdf() {
    if (!file) {
      setError("Please select a PDF first.");
      return;
    }

    setUploading(true);
    setError("");

    try {
      const formData = new FormData();
      formData.append("file", file);

      const response = await fetch(`${API_URL}/api/upload`, {
        method: "POST",
        body: formData,
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "PDF upload failed.");
      }
      setDocumentName(data.filename || file.name);

setMessages([
  {
    role: "assistant",
    content: `I've processed "${file.name}". You can now ask questions about your PDF.`,
  },
]);

// Refresh PDF history after successful upload.
const historyResponse = await fetch(`${API_URL}/api/history`);
const historyData = await historyResponse.json();

if (!historyResponse.ok) {
  throw new Error("PDF uploaded, but history could not be refreshed.");
}

setPdfHistory(historyData.history || []);

      
    } catch (err) {
      setError(err.message || "Cannot connect to the backend.");
    } finally {
      setUploading(false);
    }
  }

  async function sendQuestion(event) {
    event.preventDefault();

    const text = question.trim();
    if (!text || loading) return;

    setError("");
    setQuestion("");
    setMessages((previous) => [
      ...previous,
      { role: "user", content: text },
    ]);
    setLoading(true);

    try {
      const response = await fetch(`${API_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: text }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Could not get an answer.");
      }

      setMessages((previous) => [
        ...previous,
        {
          role: "assistant",
          content: data.answer,
          sources: data.sources || [],
        },
      ]);
    } catch (err) {
      setError(err.message || "Cannot connect to the backend.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-icon">✦</div>
          <span>DocuMind</span>
        </div>

        <button
  className="new-chat"
  onClick={() => {
    setMessages([]);
    setQuestion("");
    setFile(null);
    setError("");
  }}
>
  + New conversation
</button>

        <div className="sidebar-label">YOUR DOCUMENT</div>
        <div className="document-card">
          <div className="pdf-icon">PDF</div>
          <div className="document-info">
            <strong>{documentName || "No document uploaded"}</strong>
            <span>{documentName ? "Ready to chat" : "Upload a PDF to begin"}</span>
          </div>
        </div>
        <div className="sidebar-label">PDF HISTORY</div>

<div className="pdf-history-list">
  {pdfHistory.length === 0 ? (
    <p className="history-empty">No uploaded PDFs yet</p>
  ) : (
   
pdfHistory.map((pdf) => (
  <div
    className={`history-document ${
      documentName === pdf.filename ? "active" : ""
    }`}
    key={pdf.id}
    onClick={() => activatePdf(pdf)}
    role="button"
    tabIndex={0}
    onKeyDown={(event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        activatePdf(pdf);
      }
    }}
    title={`Open ${pdf.filename}`}
  >
   <div className="pdf-icon">PDF</div>

<div className="document-info">
  <strong title={pdf.filename}>{pdf.filename}</strong>
  <span>
    {pdf.pages} pages · {pdf.chunks} chunks
  </span>
</div>
<button
  type="button"
  className="delete-pdf-button"
  onClick={(event) => deletePdf(pdf, event)}
  title={`Delete ${pdf.filename}`}
  aria-label={`Delete ${pdf.filename}`}
>
  <svg
    width="18"
    height="18"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.7"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    <path d="M3 6h18" />
    <path d="M8 6V4h8v2" />
    <path d="m19 6-1 14H6L5 6" />
    <path d="M10 11v5M14 11v5" />
  </svg>
</button>

  </div>
))

  )}
</div>

        <div className="sidebar-bottom">
          <div className="status-dot" />
          <span>AI document assistant</span>
        </div>
      </aside>

      <main className="main-panel">
        <header className="topbar">
          <div>
            <div className="eyebrow">YOUR PERSONAL RESEARCH ASSISTANT</div>
            <h1>Chat with your documents</h1>
          </div>
          <div className="model-badge">
            <span className="status-dot" /> RAG Assistant
          </div>
        </header>

        <section className="workspace">
    
{messages.length === 0 ? (
  <div className="welcome">
    <div className="welcome-symbol">✦</div>
    <h2>Your documents, understood.</h2>
    <p>
      Upload a PDF and ask questions. I'll find relevant passages
      and generate answers grounded in your document.
    </p>
  </div>
) : (
  <div className="conversation">
    {messages.map((message, index) => (
      <article className={`message ${message.role}`} key={index}>
        <div className="avatar">
          {message.role === "assistant" ? "✦" : "Y"}
        </div>

        <div className="message-body">
          <div className="message-author">
            {message.role === "assistant" ? "DocuMind" : "You"}
          </div>

          <div className="message-text">{message.content}</div>

          {message.sources?.length > 0 && (
            <details className="sources">
              <summary>
                Sources ({message.sources.length} passages)
              </summary>

              {message.sources.map((source, sourceIndex) => (
                <div className="source-card" key={sourceIndex}>
                  <strong>
                    {source.filename || documentName} · Page{" "}
                    {source.page}
                  </strong>
                  <p>{source.text}</p>
                </div>
              ))}
            </details>
          )}
        </div>
      </article>
    ))}

     {loading && (
  <div className="loading-message">
    <span className="status-dot" />
    <span>DocuMind is thinking</span>
    <span className="typing-dots" aria-label="Loading">
      <span>.</span>
      <span>.</span>
      <span>.</span>
    </span>
   </div>
)}
  </div>
)}

<div className="upload-panel upload-panel-compact">
  <h3>{documentName ? "Upload another PDF" : "Start with a PDF"}</h3>
  <p>
    {documentName
      ? "Choose another document to process."
      : "Select a PDF from your computer to begin."}
  </p>

  <label className="file-picker">
    Choose PDF
    <input
      type="file"
      accept=".pdf,application/pdf"
      onChange={(event) => {
        setFile(event.target.files?.[0] || null);
        setError("");
      }}
    />
  </label>

  {file && <div className="selected-file">{file.name}</div>}

  <button
    className="upload-button"
    onClick={uploadPdf}
    disabled={!file || uploading}
  >
    {uploading ? "Processing PDF..." : "Upload and process"}
  </button>
</div>


          {error && <div className="error-message">{error}</div>}
        </section>

        <footer className="composer-area">
          <form className="composer" onSubmit={sendQuestion}>
            <input
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder={
                documentName
                  ? "Ask a question about your PDF..."
                  : "Upload a PDF to start asking questions..."
              }
              disabled={!documentName || loading}
            />
            <button
              type="submit"
              disabled={!documentName || !question.trim() || loading}
              aria-label="Send question"
            >
              ↑
            </button>
          </form>
         
        </footer>
      </main>
    </div>
  );
}

export default App;
