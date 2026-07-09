from langchain.tools import tool
from pydantic import BaseModel, Field
# from langchain.embeddings import OpenAIEmbeddings
# from langchain.embeddings.openai import OpenAIEmbeddings
# from langchain_openai import OpenAIEmbeddings
from langchain_ollama import OllamaEmbeddings
# from langchain.vectorstores import Chroma
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import CharacterTextSplitter
# from langchain.document_loaders import PyPDFLoader, TextLoader
from langchain_community.document_loaders import PyPDFLoader,TextLoader
import logging
import pandas as pd
from openpyxl import load_workbook
from langchain_core.documents import Document
import base64
import hashlib
import os
import streamlit as st
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# In-process FAISS index cache keyed by (file path, file content hash, embed
# model). Embedding a document with local Ollama takes seconds; without this
# every rag_query call rebuilt the index from scratch even for an unchanged
# file. Keyed on content hash so edits invalidate naturally.
_INDEX_CACHE: dict = {}
_INDEX_CACHE_MAX = 8  # small LRU-ish bound; a chat session touches few files


def _file_digest(file_path: str) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _get_or_build_index(file_path: str, texts, embeddings, embed_model: str):
    key = (file_path, _file_digest(file_path), embed_model)
    db = _INDEX_CACHE.get(key)
    if db is None:
        db = FAISS.from_documents(texts, embeddings)
        if len(_INDEX_CACHE) >= _INDEX_CACHE_MAX:
            _INDEX_CACHE.pop(next(iter(_INDEX_CACHE)))
        _INDEX_CACHE[key] = db
        logging.info(f"FAISS index built and cached for {file_path}")
    else:
        logging.info(f"FAISS index cache hit for {file_path}")
    return db


class RAGInput(BaseModel):
    query: str = Field(description="The question to be answered using the RAG system.")
    file_path: str = Field(description="Path to the file to be used as the knowledge base.")

@tool("rag_query", args_schema=RAGInput)
def rag_query(query: str, file_path: str) -> str:
    """Query a local PDF or Markdown document using RAG. Do not use for 'md://' paths (use the MCP tools for those instead)."""
    
    # Initialize session state for image data
    if "image_data" not in st.session_state:
        st.session_state.image_data = ""

    pages = query
    # Determine file type and load accordingly
    if file_path.lower().endswith('.pdf'):
        try:
            loader = PyPDFLoader(file_path)
            pages = loader.load_and_split()
        except Exception as e:
            return f"Error loading PDF {file_path}: {e}"
    elif file_path.lower().endswith('.md') or file_path.lower().endswith('.txt'):
        if file_path.startswith("md://"):
            return "Error: rag_query is for local disk files only. For 'md://' files, please use the specific MCP server read tool."
        try:
            loader = TextLoader(file_path, encoding="utf-8")
            pages = loader.load()
        except Exception as e:
            return f"Error loading text file {file_path}: {e}"
    elif file_path.lower().endswith('.xlsx'):
        # Get all sheet names
        excel_file = pd.ExcelFile(file_path)
        # all_sheets_data = []
        documents = []
        # Read each sheet
        for sheet_name in excel_file.sheet_names:
            df = pd.read_excel(excel_file, sheet_name=sheet_name)
            df = df.astype(str)
            sheet_text = f"Sheet: {sheet_name}\n{df.to_string()}"
            # Create Document object directly
            doc = Document(page_content=sheet_text, metadata={"source": sheet_name})
            documents.append(doc)
        pages = documents
    elif file_path.lower().endswith('.png'):
        with open(file_path, "rb") as f:
            st.session_state.image_data = base64.b64encode(f.read()).decode("utf-8")
            # pages = image_data
    else:
        raise ValueError("Unsupported file type. Please provide a PDF or Markdown txt file.")

    # Rest of the function remains the same
    if(query != pages):
        text_splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=0)
        texts = text_splitter.split_documents(pages)
        
        # Add validation
        if not texts:
            warning_response = "No content found to process in the document."
            logging.info(warning_response)
            return warning_response
            
        embed_model = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
        embeddings = OllamaEmbeddings(
            model=embed_model,
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        )
        db = _get_or_build_index(file_path, texts, embeddings, embed_model)

        docs = db.similarity_search(query)

        response = f"Based on the document content, here's the relevant information:\n\n"
        for doc in docs:
            response += f"{doc.page_content}\n\n"
    else: # No file or only image file is provided
        response = query

    return response

if __name__ == "__main__":
    #Enable logging
    logging.basicConfig(level=logging.INFO)
    
    # Point RAG_TEST_FILE at any local PDF or Markdown file to try a query.
    test_path = os.getenv("RAG_TEST_FILE")
    if not test_path:
        raise SystemExit("Set RAG_TEST_FILE to a PDF or Markdown file path.")
    test_query = os.getenv("RAG_TEST_QUERY", "What is the main topic of this document?")
    print(rag_query.run({"query": test_query, "file_path": test_path}))
