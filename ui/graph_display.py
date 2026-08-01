"""Shared LangGraph topology renderer for Streamlit.

Extracted from app.py's displayGraph so the Coding Engineer panel
(ui/coding_engineer_panel.py) can show its pipeline the same way the other
agents do, without a circular import back into app.py. Behaviour is
unchanged from the original: draw_mermaid_png() calls the remote
mermaid.ink service, so the PNG is cached on disk keyed by the graph's
mermaid source -- reruns (and offline demos) never repeat the network
call. Falls back to showing the mermaid source text if the image can't be
produced at all.
"""

import hashlib
from io import BytesIO
from pathlib import Path

import streamlit as st
from PIL import Image


def render_graph_diagram(chain, caption: str, height: int = 460) -> None:
    graph = chain.get_graph(xray=True)
    mermaid_src = graph.draw_mermaid()
    cache_dir = Path(".cache/graph-png")
    cache_dir.mkdir(parents=True, exist_ok=True)
    png_path = cache_dir / (hashlib.sha256(mermaid_src.encode()).hexdigest()[:16] + ".png")

    if not png_path.exists():
        try:
            png_path.write_bytes(graph.draw_mermaid_png())
        except Exception:  # noqa: BLE001 -- mermaid.ink is a remote nicety; any failure falls back to source text (same as the original app.py code)
            with st.expander(f"{caption} — graph diagram (image service unreachable)"):
                st.code(mermaid_src)
            return

    image = Image.open(BytesIO(png_path.read_bytes()))
    new_width = int(height * image.width / image.height)  # maintain aspect ratio
    st.image(image.resize((new_width, height)), caption=caption)
