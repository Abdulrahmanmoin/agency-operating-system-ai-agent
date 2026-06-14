"""Groq chat-model factory. Returns a LangChain chat model bound to the right Groq model per role."""

from typing import Literal

from langchain_groq import ChatGroq

from config import settings

Role = Literal["manager", "specialist", "validator"]


def get_chat_model(role: Role = "specialist", temperature: float = 0.2) -> ChatGroq:
    model_map = {
        "manager": settings.groq_model_manager,
        "specialist": settings.groq_model_specialist,
        "validator": settings.groq_model_validator,
    }
    return ChatGroq(
        model=model_map[role],
        api_key=settings.groq_api_key,
        temperature=temperature,
    )
