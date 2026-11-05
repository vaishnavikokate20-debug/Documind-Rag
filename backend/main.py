
import os
import tempfile

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from rag_pipeline import RAGPipeline
import uuid
from datetime import datetime, timezone
from pathlib import Path

import history_db
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "data" / "uploaded_pdfs"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

history_db.initialize_database()

app = FastAPI(title="DocuMind RAG Chat API")

# Allow the React frontend to connect to the backend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Create the RAG pipeline only when a PDF is uploaded.
rag_pipeline = None


class ChatRequest(BaseModel):
    question: str


@app.get("/")
def home():
    return {"message": "DocuMind API is running!"}


@app.get("/api/health")
def health_check():
    return {"status": "healthy"}
@app.delete("/api/history/{pdf_id}")
def delete_pdf_from_history(pdf_id: str):
    global rag_pipeline

    record = history_db.get_pdf(pdf_id)

    if not record:
        raise HTTPException(
            status_code=404,
            detail="PDF not found in history.",
        )

    stored_path = Path(record["stored_path"])

    try:
        # Check whether the PDF being deleted is currently active.
        is_active_pdf = (
            rag_pipeline is not None
            and rag_pipeline.document_loaded
            and any(
                source.get("filename") == record["filename"]
                for source in rag_pipeline.sources
            )
        )

        # Delete the history record first.
        deleted = history_db.delete_pdf(pdf_id)

        if not deleted:
            raise HTTPException(
                status_code=404,
                detail="PDF history record could not be deleted.",
            )

        # Remove the saved PDF file.
        if stored_path.exists():
            stored_path.unlink()

        # Clear the active RAG document if this PDF was active.
        
        # Delete only this PDF's chunks from ChromaDB.
        if rag_pipeline is not None:
            unique_pdf_id = Path(record["stored_path"]).stem
            rag_pipeline.delete_pdf_chunks(unique_pdf_id)

        return {
            "message": "PDF deleted successfully.",
            "id": pdf_id,
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not delete PDF: {str(exc)}",
        )

@app.get("/api/history")
def get_pdf_history():
    
    
    try:
        return {
            "history": history_db.list_pdfs()
        }
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not retrieve PDF history: {str(exc)}",
        )

@app.post("/api/history/{pdf_id}/activate")
def activate_pdf(pdf_id: str):
    global rag_pipeline

    record = history_db.get_pdf(pdf_id)

    if not record:
        raise HTTPException(
            status_code=404,
            detail="PDF not found in history.",
        )

    stored_path = record["stored_path"]

    if not os.path.exists(stored_path):
        raise HTTPException(
            status_code=404,
            detail="The saved PDF file could not be found.",
        )

    try:
        if rag_pipeline is None:
            rag_pipeline = RAGPipeline()

        result = rag_pipeline.load_pdf(
            stored_path,
            record["filename"],
        )

        return {
            "message": "PDF activated successfully.",
            "id": pdf_id,
            "filename": record["filename"],
            "pages": result["pages"],
            "chunks": result["chunks"],
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not activate PDF: {str(exc)}",
        )

@app.post("/api/upload")
async def upload_pdf(file: UploadFile = File(...)):
    global rag_pipeline

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Please upload a valid PDF file.",
        )

    pdf_id = str(uuid.uuid4())
    stored_path = UPLOAD_DIR / f"{pdf_id}.pdf"

    try:
        contents = await file.read()

        if not contents:
            raise HTTPException(
                status_code=400,
                detail="The uploaded file is empty.",
            )

        # Save the PDF permanently.
        stored_path.write_bytes(contents)

        # Initialize the RAG pipeline if needed.
        if rag_pipeline is None:
            rag_pipeline = RAGPipeline()

        # Extract text and create document chunks.
        result = rag_pipeline.load_pdf(
            str(stored_path),
            file.filename,
        )

        # Save the PDF details in SQLite.
        record = {
            "id": pdf_id,
            "filename": file.filename,
            "stored_path": str(stored_path),
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "pages": result["pages"],
            "chunks": result["chunks"],
        }

        history_db.add_pdf(record)

        return {
            "message": "PDF processed successfully.",
            "id": pdf_id,
            "filename": file.filename,
            "uploaded_at": record["uploaded_at"],
            "pages": result["pages"],
            "chunks": result["chunks"],
        }

    except HTTPException:
        raise
    except Exception as exc:
        # Remove the new file if processing or saving history fails.
        if stored_path.exists():
            stored_path.unlink()

        raise HTTPException(
            status_code=500,
            detail=f"Could not process PDF: {str(exc)}",
        )
    finally:
        await file.close()



@app.post("/api/chat")
def chat(request: ChatRequest):
    if rag_pipeline is None:
        raise HTTPException(
            status_code=400,
            detail="Please upload a PDF before asking a question.",
        )

    question = request.question.strip()

    if not question:
        raise HTTPException(
            status_code=400,
            detail="Please enter a question.",
        )

    try:
        result = rag_pipeline.answer(question)

        return {
            "answer": result["answer"],
            "sources": result["sources"],
        }
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not generate an answer: {str(exc)}",
        )
