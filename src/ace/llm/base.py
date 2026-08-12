import os
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from .models import MODEL_PROVIDERS, ModelsEnum

DEEPSEEK_BASE_URL = "https://api.deepseek.com"


class DeepSeekChatOpenAI(ChatOpenAI):
    """OpenAI-compatible DeepSeek client with ACE-compatible structured output."""

    def with_structured_output(self, schema=None, **kwargs: Any):
        # DeepSeek supports function calling, but not OpenAI's json_schema mode.
        kwargs.setdefault("method", "function_calling")
        return super().with_structured_output(schema, **kwargs)


def create_llm(model: ModelsEnum, **kwargs: Any) -> BaseChatModel:
    """
    Factory: Instantiate and return a LangChain chat model for the given model enum, with backend-specific config.

    Args:
        model: ModelProviders enum value (e.g. ModelProviders.GPT_40_2024_07_18)
        **kwargs: Passed to the backend constructor (e.g. temperature, api_key, model_path, etc)

    Returns:
        LangChain BaseChatModel instance (e.g. ChatOpenAI, ChatAnthropic, etc)

    Raises:
        ValueError if the provider is unknown or required kwargs are missing.
    """
    provider = MODEL_PROVIDERS[model]
    if provider == "openai" or provider == "vllm":
        return ChatOpenAI(model=model.value, **kwargs)
    elif provider == "deepseek":
        api_key = kwargs.pop("api_key", None) or os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY is required for DeepSeek models")

        extra_body = dict(kwargs.pop("extra_body", {}))
        extra_body.setdefault("thinking", {"type": "disabled"})
        return DeepSeekChatOpenAI(
            model=model.value,
            api_key=api_key,
            base_url=kwargs.pop("base_url", DEEPSEEK_BASE_URL),
            extra_body=extra_body,
            **kwargs,
        )
    elif provider == "anthropic":
        return ChatAnthropic(model_name=model.value, **kwargs)
    elif provider == "meta":
        raise NotImplementedError("Meta/Llama provider support not yet implemented. Please add your backend.")
    else:
        raise ValueError(f"Unknown or unsupported provider: {provider}")
