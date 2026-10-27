import os
from langchain_chroma import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from app.config import get_llm

CHROMA_PATH = "./chroma_db"

def get_vectorstore():
    embeddings = GoogleGenerativeAIEmbeddings(model="gemini-embedding-001")
    # Si no existe la carpeta, Chroma la crea sola
    return Chroma(persist_directory=CHROMA_PATH, embedding_function=embeddings)

def ingest_documents(texts: list[str]):
    """Función para cargar datos a la base vectorial"""
    vectorstore = get_vectorstore()
    vectorstore.add_texts(texts)
    print(f"[RAG] {len(texts)} documentos indexados.")