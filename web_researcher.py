import os
import functools
import operator
from typing import Annotated, List, Dict, Optional
from pydantic import BaseModel, Field

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_community.document_loaders import WebBaseLoader
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_ollama import ChatOllama

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

tavily_tool = TavilySearchResults(max_results=5)

@tool
def scrape_webpages(urls: List[str]) -> str:
    """Use requests and bs4 to scrape the provided web pages for detailed information."""
    loader = WebBaseLoader(urls)
    docs = loader.load()
    return "\n\n".join(
        [
            f'<Document name="{doc.metadata.get("title", "")}">\n{doc.page_content}\n</Document>'
            for doc in docs
        ]
    )

def create_agent(
    llm: ChatOllama,
    tools: list,
    system_prompt: str,
) -> AgentExecutor:
    """Create a tool-calling agent and add it to the graph."""
    system_prompt += "\nWork autonomously according to your specialty, using the tools available to you."
    system_prompt += " Do not ask for clarification."
    system_prompt += " Your other team members (and other teams) will collaborate with you with their own specialties."
    system_prompt += " You are chosen for a reason! You are one of the following team members: {team_members}."
    
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="messages"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ]
    )
    agent = create_tool_calling_agent(llm, tools, prompt)
    executor = AgentExecutor(agent=agent, tools=tools)
    return executor

def agent_node(state, agent, name):
    result = agent.invoke(state)
    return {"messages": [HumanMessage(content=result["output"], name=name)]}

def create_team_supervisor(llm: ChatOllama, system_prompt: str, members: List[str]):
    """An LLM-based router."""
    options = ["FINISH"] + members
    
    class RouteSchema(BaseModel):
        next: str = Field(description=f"The next role to act. Must be one of: {options}")

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="messages"),
            (
                "system",
                "Given the conversation above, who should act next?"
                " Or should we FINISH? Select one of: {options}",
            ),
        ]
    ).partial(options=str(options), team_members=", ".join(members))
    
    # Use with_structured_output which expects tool-calling capable local models.
    chain = prompt | llm.with_structured_output(RouteSchema)
    
    # The supervisor node needs to return {"next": route.next} to update the state
    return chain | (lambda x: {"next": x.next})

# Research team graph state
class ResearchTeamState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    team_members: List[str]
    next: str

def create_researcher_graph_workflow(llm: ChatOllama):
    search_agent = create_agent(
        llm,
        [tavily_tool],
        "You are a research assistant who can search for up-to-date info using the tavily search engine.",
    )
    search_node = functools.partial(agent_node, agent=search_agent, name="Search")

    research_agent = create_agent(
        llm,
        [scrape_webpages],
        "You are a research assistant who can scrape specified urls for more detailed information using the scrape_webpages function.",
    )
    research_node = functools.partial(agent_node, agent=research_agent, name="Web_Scraper")

    supervisor_agent = create_team_supervisor(
        llm,
        "You are a supervisor tasked with managing a conversation between the"
        " following workers: Search, Web_Scraper. Given the following user request,"
        " respond with the worker to act next. Each worker will perform a"
        " task and respond with their results and status. When finished,"
        " respond with FINISH.",
        ["Search", "Web_Scraper"],
    )

    research_graph = StateGraph(ResearchTeamState)
    research_graph.add_node("Search", search_node)
    research_graph.add_node("Web_Scraper", research_node)
    research_graph.add_node("supervisor", supervisor_agent)

    research_graph.add_edge("Search", "supervisor")
    research_graph.add_edge("Web_Scraper", "supervisor")
    research_graph.add_conditional_edges(
        "supervisor",
        lambda x: x["next"],
        {"Search": "Search", "Web_Scraper": "Web_Scraper", "FINISH": END},
    )

    research_graph.set_entry_point("supervisor")
    return research_graph.compile()

class WebResearcher:
    def __init__(self, llm):
        self.llm = llm

    def create_graph(self):
        return create_researcher_graph_workflow(self.llm)
