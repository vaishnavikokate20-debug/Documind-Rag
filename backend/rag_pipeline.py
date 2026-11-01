
import os
from pathlib import Path

import chromadb
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
VECTOR_STORE_PATH = BASE_DIR / "data" / "vector_store"
COLLECTION_NAME = "pdf_documents"


class RAGPipeline:
    def __init__(self):
        self.embedding_model = SentenceTransformer(
            "all-MiniLM-L6-v2"
        )

        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError(
                "GROQ_API_KEY is missing. Add it to backend/.env"
            )

        self.llm = ChatGroq(
            model=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"),
            groq_api_key=api_key,
            temperature=0,
        )

        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50,
        )

        VECTOR_STORE_PATH.mkdir(parents=True, exist_ok=True)

        self.chroma_client = chromadb.PersistentClient(
            path=str(VECTOR_STORE_PATH)
        )

        self.collection = self._create_collection()
        self.chunks = []
        self.sources = []
        self.document_loaded = False
        self.active_pdf_id = None

    def _create_collection(self):
        return self.chroma_client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    def load_pdf(self, file_path, filename):
        loader = PyPDFLoader(file_path)
        pages = loader.load()

        if not pages:
            raise ValueError("No readable pages found in this PDF.")

        documents = self.text_splitter.split_documents(pages)
        documents = [
            doc for doc in documents
            if doc.page_content.strip()
        ]

        if not documents:
            raise ValueError("No readable text found in this PDF.")

        chunks = [doc.page_content for doc in documents]
        pdf_id = Path(file_path).stem
        sources = []

        for index, doc in enumerate(documents):
            page_number = int(doc.metadata.get("page", 0)) + 1
            sources.append({
             "filename": filename,
             "pdf_id": pdf_id,
             "page": page_number,
              "doc_index": index,
             "content_length": len(doc.page_content),
                    })

        vectors = self.embedding_model.encode(
            chunks,
            show_progress_bar=False,
        )

            

        chunk_ids = [
            f"{pdf_id}_chunk_{i}"
            for i in range(len(chunks))
        ]

        # Add the new PDF chunks to the existing collection.
                # Remove existing chunks for this saved PDF before reloading it.
        existing_ids = [
            f"{pdf_id}_chunk_{i}"
            for i in range(len(chunks))
        ]

        existing = self.collection.get(
            ids=existing_ids,
            include=["metadatas"],
        )

        if existing["ids"]:
            self.collection.delete(ids=existing["ids"])

        # Add the PDF chunks to the existing collection.
        self.collection.add(
            ids=chunk_ids,
            documents=chunks,
            embeddings=vectors.tolist(),
            metadatas=sources,
        )

        # Track all chunks currently stored in the collection.
        self.chunks = self.collection.get(
            include=["documents"]
        )["documents"] or []

        self.sources = self.collection.get(
            include=["metadatas"]
        )["metadatas"] or []

        self.document_loaded = len(self.chunks) > 0
        self.active_pdf_id = pdf_id

        return {
            "filename": filename,
            "pages": len(pages),
            "chunks": len(chunks),
        }

    def clear_document(self):
        """Reset the active document state without deleting stored PDFs."""
        self.chunks = self.collection.get(
            include=["documents"]
        )["documents"] or []

        self.sources = self.collection.get(
            include=["metadatas"]
        )["metadatas"] or []

        self.document_loaded = len(self.chunks) > 0

    def delete_pdf_chunks(self, pdf_id):
        """Delete chunks belonging to one specific PDF."""

        all_data = self.collection.get(
            include=["metadatas"]
        )

        chunk_ids = [
            chunk_id
            for chunk_id in all_data["ids"]
            if chunk_id.startswith(f"{pdf_id}_chunk_")
        ]

        if chunk_ids:
            self.collection.delete(ids=chunk_ids)

        self.clear_document()

        return len(chunk_ids)

    def answer(self, question, top_k=5):
        if not self.document_loaded:
            raise ValueError("Upload a PDF before asking a question.")

        question = question.strip()
        if not question:
            raise ValueError("Please enter a question.")

        query_vector = self.embedding_model.encode(
            [question],
            show_progress_bar=False,
        )[0]

        if not self.active_pdf_id:
            raise ValueError("Please select or activate a PDF first.")

        active_pdf_data = self.collection.get(
            where={"pdf_id": self.active_pdf_id},
            include=["metadatas"],
        )

        active_pdf_count = len(active_pdf_data["ids"])

        if active_pdf_count == 0:
            raise ValueError(
                "No indexed chunks found for the selected PDF. "
                "Please activate the PDF again."
            )

        result = self.collection.query(
            query_embeddings=[query_vector.tolist()],
            n_results=min(top_k, active_pdf_count),
            where={"pdf_id": self.active_pdf_id},
            include=["documents", "metadatas", "distances"],
        )
        print("\n========== RETRIEVED PDF PASSAGES ==========")

        for index, (chunk, metadata, distance) in enumerate(
            zip(
                result["documents"][0],
                result["metadatas"][0],
                result["distances"][0],
            ),
            start=1,
        ):
            print(f"\nPassage {index}")
            print(f"PDF: {metadata.get('filename')}")
            print(f"Page: {metadata.get('page')}")
            print(f"Similarity score: {1 - distance:.4f}")
            print(f"Text: {chunk[:1000]}")

        print("\n============================================\n")
        retrieved_chunks = result["documents"][0]
        retrieved_metadata = result["metadatas"][0]
        distances = result["distances"][0]

        context_parts = []
        retrieved_sources = []

        for chunk, metadata, distance in zip(
            retrieved_chunks,
            retrieved_metadata,
            distances,
        ):
            page = metadata["page"]
            context_parts.append(f"[Page {page}] {chunk}")

            retrieved_sources.append({
                "filename": metadata["filename"],
                "page": page,
                "text": chunk,
                "score": float(1 - distance),
            })

        context = "\n\n".join(context_parts)

        messages = [
            
           
            SystemMessage(
                content=(
                    "You are a PDF question-answering assistant. "
                    "Answer the user's question completely using only the supplied PDF context.\n\n"

                    "Follow these rules carefully:\n"
                    "1. Include all important points from the context that directly answer "
                    "the question. Do not omit relevant information.\n"
                    "2. Do not stop after mentioning only the first point when the context "
                    "contains several relevant points.\n"
                    "3. For questions asking 'explain', provide a clear explanation with "
                    "the relevant details from the PDF.\n"
                    "4. For questions asking 'list', include all relevant items available "
                    "in the supplied context.\n"
                    "5. For questions asking 'compare', cover the relevant differences "
                    "available in the context.\n"
                    "6. Use simple, clear language while preserving the meaning of the PDF.\n"
                    "7. Do not add unrelated information, outside knowledge, or invented facts.\n"
                    "8. If the supplied context contains only part of the answer, explain "
                    "that the answer is incomplete based on the available context.\n"
                    "9. If the answer is not supported by the context, say that you could "
                    "not find the information in the provided PDFs.\n"
                    "10. Keep the answer as detailed as the question requires. Do not "
                    "force every answer to be short."
                )
            ),

        
            
            

            HumanMessage(
                content=(
                    f"PDF context:\n{context}\n\n"
                    f"Question: {question}"
                )
            ),
        ]
        print("\n========== QUESTION ==========")
        print(question)
        print("\n========== CONTEXT SENT TO AI ==========")
        print(context)
        print("\n========== END CONTEXT ==========\n")

        response = self.llm.invoke(messages)

        return {
            "answer": response.content,
            "sources": retrieved_sources,
        }
