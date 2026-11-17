import json
from typing import Any, Callable, Dict, Optional, Type, TypeVar
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from app.config import EngineSettings

T = TypeVar("T", bound=BaseModel)


def invoke_structured_agent(
    schema_cls: Type[T],
    system_prompt: str,
    user_payload: Dict[str, Any],
    mock_builder: Callable[[Dict[str, Any]], T],
    settings: Optional[EngineSettings] = None,
) -> T:
    """Invoke an agent with structured output enforcement or deterministic mock generation.

    Zero import-time side effects: EngineSettings is only instantiated inside the function
    when not explicitly provided.
    """
    if settings is None:
        settings = EngineSettings()

    if settings.USE_MOCK_LLM:
        raw_mock = mock_builder(user_payload)
        dumped = raw_mock.model_dump() if isinstance(raw_mock, BaseModel) else raw_mock
        return schema_cls.model_validate(dumped)

    # Live LLM execution with ChatGoogleGenerativeAI
    llm = ChatGoogleGenerativeAI(
        model=settings.GEMINI_MODEL,
        google_api_key=settings.GEMINI_API_KEY,
        temperature=0.1,
    )
    structured_llm = llm.with_structured_output(schema_cls)
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=json.dumps(user_payload, indent=2, default=str)),
    ]
    result = structured_llm.invoke(messages)
    if result is None:
        # Retry once before failing
        result = structured_llm.invoke(messages)
        if result is None:
            raise ValueError(f"Structured output model returned None for {schema_cls.__name__}")

    dumped_result = result.model_dump() if isinstance(result, BaseModel) else result
    return schema_cls.model_validate(dumped_result)

