from langchain_openai import ChatOpenAI

from agent.llm_config import (
    open_api_base,
    open_api_key,
    openai_model,
    openai_temperature,
)


llm = ChatOpenAI(
    model=openai_model,
    temperature=openai_temperature,
    openai_api_key=open_api_key,
    openai_api_base=open_api_base
)
