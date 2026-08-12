import os
from unittest.mock import MagicMock, patch

import pytest
from langchain_openai import ChatOpenAI

from src.ace.llm.base import DEEPSEEK_BASE_URL, DeepSeekChatOpenAI, create_llm
from src.ace.llm.models import MODEL_PROVIDERS, ModelsEnum


def test_deepseek_v4_flash_is_registered():
    assert MODEL_PROVIDERS[ModelsEnum.DEEPSEEK_V4_FLASH] == "deepseek"


@patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-deepseek-key"})
def test_create_deepseek_v4_flash_disables_thinking():
    llm = create_llm(ModelsEnum.DEEPSEEK_V4_FLASH, temperature=0)

    assert isinstance(llm, DeepSeekChatOpenAI)
    assert llm.model_name == "deepseek-v4-flash"
    assert llm.openai_api_base == DEEPSEEK_BASE_URL
    assert llm.extra_body == {"thinking": {"type": "disabled"}}


def test_create_deepseek_requires_api_key():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
            create_llm(ModelsEnum.DEEPSEEK_V4_FLASH)


@patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-deepseek-key"})
def test_deepseek_structured_output_uses_function_calling():
    llm = create_llm(ModelsEnum.DEEPSEEK_V4_FLASH)
    schema = {"type": "object", "properties": {"answer": {"type": "string"}}}
    runnable = MagicMock()

    with patch.object(ChatOpenAI, "with_structured_output", return_value=runnable) as structured_output:
        assert llm.with_structured_output(schema) is runnable

    structured_output.assert_called_once_with(schema, method="function_calling")
