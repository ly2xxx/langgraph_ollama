# 2026 Modernization — langgraph_ollama

Date: 2026-06-22

This project was upgraded from the LangChain **0.2.x** era (pip/`requirements.txt`,
no `pyproject.toml`) to the LangChain/LangGraph **0.3.x** line with **uv**-based
packaging on **Python 3.12**, using the dedicated `langchain-ollama` partner package.

## Packaging: pip/venv → uv

- Added `pyproject.toml` (`requires-python >=3.12`) as the single source of truth
  for dependencies.
- Added `.python-version` (`3.12`); `uv` manages the interpreter.
- Generated `uv.lock` for reproducible installs.
- Regenerated `requirements.txt` from the lock (`uv export`) for tooling compatibility.
- Rewrote `README.md` with uv setup instructions.

Setup is now:

```bash
uv python install 3.12
uv sync
uv run streamlit run app.py
```

## Library versions (resolved on the 0.3.x line)

| Package | Before | After |
|---|---|---|
| langchain | 0.2.10 | 0.3.30 |
| langchain-core | (transitive) | 0.3.86 |
| langchain-community | 0.2.9 | 0.3.31 |
| langchain-text-splitters | (transitive) | 0.3.11 |
| langchain-ollama | — (not used) | 0.3.10 |
| langgraph | 0.1.9 | 0.3.34 |
| langgraph-checkpoint-sqlite | — (bundled) | 2.0.11 |
| ollama (client) | — | 0.6.2 |
| pydantic | 1.x-era | 2.13.4 |

Other deps (streamlit, pandas, faiss-cpu, selenium, beautifulsoup4, pymupdf,
python-docx, openpyxl, python-dotenv) were unpinned/updated to current releases.

## Code migrations (0.3.x + Ollama partner package)

| File(s) | Before | After |
|---|---|---|
| `app.py`, `mm_agent.py`, `rag_research_chatbot.py` | `from langchain_community.chat_models import ChatOllama` | `from langchain_ollama import ChatOllama` |
| `tools/rag.py` | `from langchain_community.embeddings import OllamaEmbeddings` | `from langchain_ollama import OllamaEmbeddings` |
| `tools/rag.py` | `from langchain.text_splitter import CharacterTextSplitter` | `from langchain_text_splitters import CharacterTextSplitter` |
| `tools/rag.py` | `from langchain.schema import Document` | `from langchain_core.documents import Document` |
| `tools/rag.py` | `OllamaEmbeddings(model_selection, base_url=...)` (positional) | `OllamaEmbeddings(model=model_selection, base_url=...)` (keyword) |

Notes:
- `SqliteSaver` (`from langgraph.checkpoint.sqlite import SqliteSaver`) kept the
  same import path but now requires the standalone `langgraph-checkpoint-sqlite`
  package, added as a dependency — no code change.
- `OllamaEmbeddings` had to switch to a keyword `model=` argument because the new
  pydantic-v2 class rejects the old positional form.
- `convert_openai_messages` (`langchain_community.adapters.openai`) and the
  `langchain.agents` agent helpers (`AgentExecutor`, `create_openai_tools_agent`)
  remain valid in 0.3.x — left unchanged.

## Dependency corrections

- Added `pillow` (directly imported via `from PIL import Image`, previously only
  available transitively through streamlit).
- Added `webdriver-manager`.
- Dropped the large block of commented-out/dead pins from `requirements.txt`.

## Verification

- `uv sync` — resolves and installs the full 0.3.x + Ollama stack on Python 3.12. ✅
- `uv run python -m py_compile *.py tools/*.py ui/*.py` — passes (only pre-existing
  `SyntaxWarning`s from hardcoded `D:\code\...` paths). ✅
- Import smoke test — every migrated/partner import path resolves and all project
  modules (`mm_agent`, `rag_research_chatbot`, `tools`, `mytools`) import cleanly. ✅

Not verified (out of scope): end-to-end agent runs, which require a live Ollama
server at `OLLAMA_BASE_URL`.

## Known pre-existing issues (not addressed)

- Hardcoded absolute paths (`D:\code\langgraph_agents\output\...`) in the
  `__main__` test blocks of `tools/rag.py` and `rag_research_chatbot.py`.
