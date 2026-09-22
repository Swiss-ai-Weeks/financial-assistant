from langchain_ollama import ChatOllama
from tools import analyze_ticker
from langchain_openai import ChatOpenAI

# ============================================================
# LLM
# ============================================================

llm_1 = ChatOllama(
    model="nemotron-3-nano:30b",
    base_url="http://localhost:11434",
    temperature=0,
    reasoning=False,
    num_predict=2048,
)

llm_2 = ChatOllama(
    model="qwen3:4b",
    base_url="http://localhost:11434",
    temperature=0,
    reasoning=False,
    num_predict=2048,
)

llm = ChatOpenAI(
    model="nvidia/nemotron-3.5-lightning",
    base_url="http://localhost:8003/v1",
    api_key="EMPTY",
    temperature=0,
    max_tokens=2048,
    extra_body={
        "chat_template_kwargs": {
            "enable_thinking": False
        }
    },
)

tools = [analyze_ticker]

llm_with_tools = llm.bind_tools(tools)

tool_registry = {
    tool.name: tool
    for tool in tools
}


