from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List

import os
import tempfile
from pypdf import PdfReader

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import SentenceTransformerEmbeddings
from langchain_community.chat_models import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

app = FastAPI()

# CORS so your React frontend can talk to this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # in production, restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_DIR = "chroma_db"
os.makedirs(DB_DIR, exist_ok=True)

# 1) Embeddings model (CPU-based, very stable)
embedding_function = SentenceTransformerEmbeddings(
    model_name="all-MiniLM-L6-v2"
)

# 2) Chroma vector store
vectorstore = Chroma(
    collection_name="docs",
    embedding_function=embedding_function,
    persist_directory=DB_DIR,
)

# 3) Local LLM via Ollama (chat model)
llm = ChatOllama(model="llama3")

# 4) Retriever
retriever = vectorstore.as_retriever(search_kwargs={"k": 4})

# 5) Prompt + RAG chain using new LangChain style
prompt = ChatPromptTemplate.from_template(
    """
You are a helpful assistant. Use ONLY the following context to answer the question.

If the answer is not in the context, say:
"I don't know based on the provided documents."

Context:
{context}

Question:
{question}
"""
)

# Runnable pipeline:
# input: user's question (string)
# - "context": uses retriever
# - "question": passes original question through
rag_chain = (
    {"context": retriever, "question": RunnablePassthrough()}
    | prompt
    | llm
    | StrOutputParser()
)


class Question(BaseModel):
    question: str


@app.get("/health")
def health():
    return {"status": "ok"}


def pdf_to_text(file_path: str) -> str:
    reader = PdfReader(file_path)
    texts = []
    for page in reader.pages:
        texts.append(page.extract_text() or "")
    return "\n".join(texts)


@app.post("/ingest")
async def ingest_files(files: List[UploadFile] = File(...)):
    """Upload and index one or more PDFs/text files into Chroma."""
    all_chunks = []
    all_metadatas = []

    for uploaded in files:
        suffix = os.path.splitext(uploaded.filename)[-1]

        # Save to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await uploaded.read()
            tmp.write(content)
            tmp_path = tmp.name

        # Extract text
        if suffix.lower() == ".pdf":
            text = pdf_to_text(tmp_path)
        else:
            text = content.decode("utf-8", errors="ignore")

        # Clean up temp file
        os.remove(tmp_path)

        # Split text into chunks
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
        )
        chunks = splitter.split_text(text)

        # Create metadata for each chunk
        metadatas = [
            {
                "source": uploaded.filename,
                "chunk_index": i
            }
            for i in range(len(chunks))
        ]

        # Save them to global lists
        all_chunks.extend(chunks)
        all_metadatas.extend(metadatas)

    # Add EVERYTHING to Chroma
    vectorstore.add_texts(texts=all_chunks, metadatas=all_metadatas)
    vectorstore.persist()

    return {
        "status": "ingested",
        "chunks": len(all_chunks)
    }



@app.post("/ask")
async def ask_question(payload: Question):
    """Ask a question about the ingested documents."""
    query = payload.question

    # 1) Get answer from RAG chain
    answer = rag_chain.invoke(query)

    # 2) Also fetch the top documents yourself to show as sources
    docs = retriever.invoke(query)

    sources = []
    for i, doc in enumerate(docs):
        sources.append(
            {
                "id": i,
                "metadata": doc.metadata,
                "snippet": doc.page_content[:200],
            }
        )

    return {
        "answer": answer,
        "sources": sources,
    }
