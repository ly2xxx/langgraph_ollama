import streamlit as st
from langchain_core.messages import HumanMessage
# from multi_agent import create_travel_agent_graph
# from web_research import create_web_research_graph
# from web_research_rag import create_web_research_rag_graph
# from web_research_consolidated import WebResearchGraph
from rag_research_chatbot import RAGResearchChatbot
from mm_agent import ArticleWriterStateMachine
from web_researcher import WebResearcher
from io import BytesIO
from PIL import Image
import asyncio
import tempfile
import os
from ui.file_picker import render_file_picker
import urllib.parse
from dotenv import load_dotenv
import os
import telemetry

# Initialise OpenTelemetry once per process. This is idempotent, so it is safe
# to call here even though Streamlit re-runs this module on every interaction.
telemetry.init_telemetry()

# TRAVEL_AGENT = "Travel Agency"
# RESEARCH_AGENT = "Research Assistant"
# RAG_RESEARCH_AGENT = "RAG Research Assistant"
RAG_CHATBOT_AGENT = "RAG Chatbot Agent"
ARTICLE_WRITER = "Article Writer"
INTERNET_RESEARCHER = "Internet Researcher"

load_dotenv()

CHAIN_CONFIG = {
    # TRAVEL_AGENT: {
    #     "models": ["gpt-4o-mini"],
    #     "support_types": ["txt", "md"]
    # },
    # RESEARCH_AGENT: {
    #     "models": ["gpt-4o-mini", "glm-5:cloud"],
    #     "support_types": ["pdf", "txt", "md"]
    # },
    # RAG_RESEARCH_AGENT: {
    #     "models": ["gpt-4o-mini", "glm-5:cloud"],
    #     "support_types": ["pdf", "txt", "md", "xlsx"]
    # },
    RAG_CHATBOT_AGENT: {
        "models": [os.getenv('OLLAMA_MODEL')],
        "support_types": ["pdf", "txt", "md", "xlsx", "png", "jpg"]
    },
    ARTICLE_WRITER: {
        "models": [os.getenv('OLLAMA_MODEL')],
        "support_types": ["txt", "md"]
    },
    INTERNET_RESEARCHER: {
        "models": [os.getenv('OLLAMA_MODEL')],
        "support_types": []
    }
}

# Canned queries for interview demos — chosen to route reliably to the right
# tools (md-mcp notes under demo-notes/ for the RAG agent) and produce rich
# traces. Selecting one pre-fills the query box; it stays editable.
DEMO_QUERIES = {
    RAG_CHATBOT_AGENT: [
        "Search my notes: what is the logical execution order of a SQL SELECT query?",
        "From my notes, what are the incident response steps when agent answers are slow?",
        "According to my notes, why does context engineering beat prompt engineering?",
        "List the files in my markdown knowledge base.",
    ],
    INTERNET_RESEARCHER: [
        "What is the weather forecast for Glasgow tomorrow?",
        "What's new in the latest LangGraph release?",
    ],
}

def process_uploaded_files(uploaded_files, support_types):
    temp_file_paths = []
    suffixes = ['.' + file_type for file_type in support_types]
    
    for uploaded_file in uploaded_files:
        file_suffix = os.path.splitext(uploaded_file.name)[1].lower()
        if file_suffix in suffixes:
            with tempfile.NamedTemporaryFile(delete=False, suffix=file_suffix) as temp_file:
                # Reset the file pointer to the beginning
                # uploaded_file.seek(0)
                # Write the content
                content=uploaded_file.read()
                # Write bytes directly to temp file
                temp_file.write(content)
                temp_file.flush()  # Ensure content is written to disk
                # Reset the file pointer again for any subsequent reads
                temp_file.seek(0)
                temp_file_paths.append(temp_file.name)
        else:
            st.warning(f"File type {file_suffix} not supported. Supported types: {','.join(support_types)}")
    
    return temp_file_paths

def get_llm(model_selection):
    # if model_selection == "gpt-4o-mini":
    #     from langchain_openai import ChatOpenAI
    #     return ChatOpenAI(model=model_selection, temperature=0)
    # else:
        from langchain_ollama import ChatOllama
        return ChatOllama(model=model_selection, base_url=os.getenv('OLLAMA_BASE_URL'), temperature=0)

@st.cache_resource(show_spinner="Building agent graph...")
def build_chain(chain_selection: str, model_selection: str):
    """Build only the selected agent's graph, once per (agent, model) pair.

    Cached across Streamlit reruns — previously all three agents were
    constructed from scratch on every interaction. Note the Article Writer
    graph built here is only used for the topology picture; mm_st.py keeps
    its own checkpointed instance in session state for the HITL flow.
    """
    llm = get_llm(model_selection)
    if chain_selection == RAG_CHATBOT_AGENT:
        return RAGResearchChatbot(llm).create_rag_research_chatbot_graph()
    if chain_selection == ARTICLE_WRITER:
        return ArticleWriterStateMachine().getGraph()
    if chain_selection == INTERNET_RESEARCHER:
        return WebResearcher(llm).create_graph()
    return None

def main():
    st.title("Multi-agent Assistant Demo")

    chain_selection = st.selectbox("Select assistant", [RAG_CHATBOT_AGENT, ARTICLE_WRITER, INTERNET_RESEARCHER])#[TRAVEL_AGENT, RESEARCH_AGENT, RAG_RESEARCH_AGENT, RAG_CHATBOT_AGENT, ARTICLE_WRITER])
    
    # Clear chat history when switching away from RAG Chatbot Agent
    if "previous_agent" not in st.session_state:
        st.session_state.previous_agent = chain_selection
    elif st.session_state.previous_agent != chain_selection:
        if "chat_history" in st.session_state:
            del st.session_state.chat_history
        if "last_output" in st.session_state:
            del st.session_state.last_output
        st.session_state.previous_agent = chain_selection

    # Get available models for the selected chain
    available_models = CHAIN_CONFIG[chain_selection]["models"]
    model_selection = st.selectbox("Select LLM model", available_models)

    langgraph_chain = build_chain(chain_selection, model_selection)

    displayGraph(langgraph_chain, chain_selection)

    if chain_selection == RAG_CHATBOT_AGENT:
        with st.sidebar:
            st.header("MCP Settings")
            md_url = os.getenv("MD_MCP_URL")
            md_folder = os.getenv("MD_MCP_FOLDER")
            if md_url:
                st.success(f"**md-mcp** connected over streamable-http (distributed tracing on):\n\n`{md_url}`")
            elif md_folder:
                st.success(f"**md-mcp** is automatically connected via Docker (stdio) using folder:\n\n`{md_folder}`")
            else:
                st.warning("**md-mcp** is disabled. Set `MD_MCP_URL` or `MD_MCP_FOLDER` in `.env` to enable it.")

    # Canned demo queries: choosing one pre-fills the query box (still editable).
    demo_queries = DEMO_QUERIES.get(chain_selection) or []
    if demo_queries:
        placeholder = "(choose a demo query)"

        def _fill_query():
            sel = st.session_state.get(f"demo_query_{chain_selection}")
            if sel and sel != placeholder:
                st.session_state[f"query_{chain_selection}"] = sel

        st.selectbox(
            "Demo queries (optional)",
            [placeholder] + demo_queries,
            key=f"demo_query_{chain_selection}",
            on_change=_fill_query,
        )

    # Get user input
    user_input = st.text_area("Enter your query:", key=f"query_{chain_selection}")

    # Create a placeholder
    dynamic_content_container = st.empty()
    # File picker (only shown for RAG_RESEARCH_AGENT)
    if chain_selection in [RAG_CHATBOT_AGENT]:#[RAG_RESEARCH_AGENT, RAG_CHATBOT_AGENT]:
        with dynamic_content_container.container():
            uploaded_files = render_file_picker(CHAIN_CONFIG[chain_selection]["support_types"])
    elif chain_selection in [ARTICLE_WRITER]:
        with dynamic_content_container.container():
            import mm_st
            mm_st.main()
    else:
        dynamic_content_container.empty()

    if st.button("Submit"):
        temp_file_paths = []  # Initialize the list here
        query = {"messages": [HumanMessage(content=user_input)]}
        # if chain_selection == TRAVEL_AGENT:
        #     for chunk in langgraph_chain.stream(query):
        #         if "__end__" not in chunk:
        #             st.write(chunk)
        #             st.write("---")
        # elif chain_selection == RESEARCH_AGENT:
        #     asyncio.run(run_research_graph(query, langgraph_chain))
        # elif chain_selection == RAG_RESEARCH_AGENT:
        #     # Convert the list of file paths to a comma-delimited string
        #     temp_file_paths = process_uploaded_files(uploaded_files, CHAIN_CONFIG[chain_selection]["support_types"])#','.join(temp_file_paths)
        #     # Use the temporary file path in the function call
        #     asyncio.run(run_research_graph({"messages": [HumanMessage(content=f"Query: {user_input}\nFile Path: {','.join(temp_file_paths)}")]}, langgraph_chain))
        if chain_selection == RAG_CHATBOT_AGENT:
            config = {"configurable": {"thread_id": "1"}}  # Add a thread_id
            temp_file_paths = process_uploaded_files(uploaded_files, CHAIN_CONFIG[chain_selection]["support_types"])
            input_data = {
                "messages": [HumanMessage(content=f"Query: {user_input}\nFile Path: {','.join(temp_file_paths)}")],
                "query": user_input,
                "file_path": ','.join(temp_file_paths)
            }
            run_chatbot_graph(langgraph_chain, input_data, config)
        elif chain_selection == INTERNET_RESEARCHER:
            # Time the whole streamed run as one request. Per-node/LLM/tool spans
            # are still captured automatically by OpenInference.
            with telemetry.track_request(INTERNET_RESEARCHER, model_selection):
                for s in langgraph_chain.stream({"messages": [HumanMessage(content=user_input)]}, {"recursion_limit": 100}):
                    if "__end__" not in s:
                        for node_name, node_state in s.items():
                            st.markdown(f"**Agent**: `{node_name}`")
                            if isinstance(node_state, dict) and "messages" in node_state:
                                p_tok, c_tok = telemetry.extract_token_usage(node_state)
                                telemetry.record_tokens(INTERNET_RESEARCHER, model_selection, p_tok, c_tok)
                                for msg in node_state["messages"]:
                                    st.markdown(msg.content)
                            elif isinstance(node_state, dict) and "next" in node_state:
                                st.markdown(f"*Routing to → {node_state['next']}*")
                            else:
                                st.write(node_state)
                        st.write("---")
        else:
            st.write("Feature under construction")

        # Clean up the temporary files after use
        for path in temp_file_paths:
            os.unlink(path)

    # Add this section to re-render chat history after page reloads
    if chain_selection == RAG_CHATBOT_AGENT and "chat_history" in st.session_state:
        render_chat_history_and_thoughts(st.session_state.chat_history, st.session_state.get("last_output"))

def displayGraph(chain, chain_selection):
    """Render the agent's graph topology.

    draw_mermaid_png() calls the remote mermaid.ink service, so the PNG is
    cached on disk keyed by the graph's mermaid source — reruns (and offline
    demos) never repeat the network call. Falls back to showing the mermaid
    source text if the image can't be produced at all.
    """
    import hashlib
    from pathlib import Path

    graph = chain.get_graph(xray=True)
    mermaid_src = graph.draw_mermaid()
    cache_dir = Path(".cache/graph-png")
    cache_dir.mkdir(parents=True, exist_ok=True)
    png_path = cache_dir / (hashlib.sha256(mermaid_src.encode()).hexdigest()[:16] + ".png")

    if not png_path.exists():
        try:
            png_path.write_bytes(graph.draw_mermaid_png())
        except Exception:
            with st.expander(f"{chain_selection} — graph diagram (image service unreachable)"):
                st.code(mermaid_src)
            return

    image = Image.open(BytesIO(png_path.read_bytes()))
    new_height = 460  # Desired height in pixels
    new_width = int(new_height * image.width / image.height)  # Maintain aspect ratio
    new_image = image.resize((new_width, new_height))
    st.image(new_image, caption=chain_selection)

# def displayGraph(chain, chain_selection):
#     # Get the graph
#     graph = chain.get_graph(xray=True)
    
#     # Create Mermaid syntax with proper indentation
#     mermaid_lines = [
#         "            graph TD"
#     ]
    
#     # Add nodes with indentation
#     for node_id, node in graph.nodes.items():
#         mermaid_lines.append(f'            {node_id}["{node.name}"]')
    
#     # Add edges with indentation
#     for edge in graph.edges:
#         if edge.conditional and edge.data:
#             mermaid_lines.append(f'            {edge.source} -->|{edge.data}| {edge.target}')
#         else:
#             mermaid_lines.append(f'            {edge.source} --> {edge.target}')
    
#     mermaid_definition = "\n".join(mermaid_lines)

#     mock_mermaid_definition = """<pre class="mermaid">
#             graph TD
#             A[Client] -->|tcp_123| B
#             B(Load Balancer)
#             B -->|tcp_456| C[Server1]
#             B -->|tcp_456| D[Server2]
#     </pre>"""
#     # graph TD __start__["__start__"] travel_agent["travel_agent"] language_assistant["language_assistant"] visualizer["visualizer"] designer["designer"] bb6936485e364c8880a6132667c0f271["ChatPromptTemplate"] 153ea937f2b54bb88465d0751ab06cb3["ChatOpenAI"] bd70292b68f548dbab6ab5e330f0f140["JsonOutputFunctionsParser"] __end__["__end__"] bb6936485e364c8880a6132667c0f271 --> 153ea937f2b54bb88465d0751ab06cb3 153ea937f2b54bb88465d0751ab06cb3 --> bd70292b68f548dbab6ab5e330f0f140 __start__ --> bb6936485e364c8880a6132667c0f271 designer --> __end__ language_assistant --> bb6936485e364c8880a6132667c0f271 travel_agent --> bb6936485e364c8880a6132667c0f271 visualizer --> bb6936485e364c8880a6132667c0f271 bd70292b68f548dbab6ab5e330f0f140 --> travel_agent bd70292b68f548dbab6ab5e330f0f140 --> language_assistant bd70292b68f548dbab6ab5e330f0f140 --> visualizer bd70292b68f548dbab6ab5e330f0f140 -->|FINISH| designer

#     # Render the diagram with proper HTML structure
#     st.markdown(f"""
#         <pre class="mermaid">
#             {mock_mermaid_definition}
#         </pre>
#         <script type="module">
#             import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
#             mermaid.initialize({{ startOnLoad: true }});
#         </script>
#     """, unsafe_allow_html=True)
    
#     st.caption(chain_selection)

# def displayGraph(chain, chain_selection):
#     # Get the graph
#     graph = chain.get_graph(xray=True)
    
#     # Create Mermaid syntax with proper indentation
#     mermaid_lines = [
#         "            graph TD"
#     ]
    
#     # Add nodes with indentation and replace spaces with underscores
#     for node_id, node in graph.nodes.items():
#         node_id_processed = node.name.replace(" ", "_")
#         mermaid_lines.append(f'            {node_id_processed}["{node.name}"]')
    
#     # Add edges with indentation and replace spaces with underscores in node references
#     for edge in graph.edges:
#         source = edge.source.replace(" ", "_")
#         target = edge.target.replace(" ", "_")
#         if edge.conditional and edge.data:
#             mermaid_lines.append(f'            {source} -->|{edge.data}| {target}')
#         else:
#             mermaid_lines.append(f'            {source} --> {target}')
    
#     mermaid_definition = "\n".join(mermaid_lines)
    
#     # Create complete HTML with mermaid
#     # check visually on https://mermaid.live/
#     # comparison - https://swimm.io/learn/mermaid-js/mermaid-js-a-complete-guide
#     # repo - https://github.com/mermaid-js/mermaid
#     # plugin - https://marketplace.visualstudio.com/items?itemName=bierner.markdown-mermaid

#     html_content = f"""
#     <html>
#       <body>
#         <pre class="mermaid">
#             {mermaid_definition}
#         </pre>
        
#         <script type="module">
#           import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
#           mermaid.initialize({{ startOnLoad: true }});
#         </script>
        
#         <!--
#         <script type="module">
#             import mermaid from './mermaid.esm.mjs';
#             mermaid.initialize({{ startOnLoad: false, logLevel: 0 }});
#             await mermaid.run();
#         </script>
#         -->
#         <!--
#         <script src="mermaid.min.js"></script>
# 	    <script>mermaid.initialize({{startOnLoad:true}});</script>
#         -->
#       </body>
#     </html>
#     """
    
#     # Use components.v1.html to render
#     st.components.v1.html(html_content, height=600)
#     st.caption(chain_selection)



# async def run_research_graph(input, chain):
#     async for output in chain.astream(input):
#         for node_name, output_value in output.items():
#             st.write("---")
#             st.write(f"Output from node '{node_name}':")
#             if isinstance(output_value, dict) and 'messages' in output_value:
#                 for message in output_value['messages']:
#                     st.markdown(message.content, unsafe_allow_html=True)
#             else:
#                 st.write(output_value)
#         st.write("\n---\n")

def render_chat_history_and_thoughts(chat_history, output=None):
    with st.container():
        # Render chat history
        for message in chat_history:
            with st.chat_message(message["role"]):
                st.write(message["content"])
        
        # Render download link
        if chat_history:
            chat_history_str = "\n\n".join([f"{msg['role']}: {msg['content']}" for msg in chat_history])
            href = f'data:text/plain;charset=utf-8,{urllib.parse.quote(chat_history_str)}'
            st.markdown(f'<a href="{href}" download="chat_history.txt">Download Chat History</a>', unsafe_allow_html=True)
        
        # Render agent thoughts
        if output:
            with st.expander("Display Agent's Thoughts"):
                st.write(output)

def run_chatbot_graph(graph, input, config):
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    
    response_container = st.container()
    prompt_container = st.container()

    user_input = input["messages"][0].content
    st.session_state.chat_history.append({"role": "user", "content": user_input})

    # Custom metrics: count the request, time it, and tally tokens. The detailed
    # per-node / per-LLM spans are captured automatically by OpenInference.
    model = os.getenv("OLLAMA_MODEL", "unknown")
    with telemetry.track_request(RAG_CHATBOT_AGENT, model):
        output = graph.invoke(input, config=config)

    prompt_tokens, completion_tokens = telemetry.extract_token_usage(output)
    telemetry.record_tokens(RAG_CHATBOT_AGENT, model, prompt_tokens, completion_tokens)

    # Extract AIMessage content from the string output
    if isinstance(output, dict):
        # response_value = str(next(iter(output.values())))
        # Last message with actual content: after summarization prunes the
        # history, messages[-1] can be an empty/removed placeholder.
        response = next(
            (m.content for m in reversed(output["messages"]) if getattr(m, "content", "")),
            "",
        )
    else:
        # Find AIMessage content in the string
        ai_message_start = output.find("AIMessage(content='") + len("AIMessage(content='")
        ai_message_end = output.find("', response_metadata")
        response = output[ai_message_start:ai_message_end]
    
    st.session_state.chat_history.append({"role": "assistant", "content": response})
    st.session_state.last_output = output


if __name__ == "__main__":
    main()
