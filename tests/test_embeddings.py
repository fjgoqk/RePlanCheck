from unittest.mock import patch

from src.ace.llm.embeddings import EMBEDDING_PROVIDERS, EmbeddingsEnum, create_embedding


def test_local_bge_embedding_is_registered():
    assert EMBEDDING_PROVIDERS[EmbeddingsEnum.BGE_SMALL_EN_V1_5] == "fastembed"


@patch("src.ace.llm.embeddings.FastEmbedEmbeddings")
def test_create_local_bge_embedding(fastembed):
    create_embedding(EmbeddingsEnum.BGE_SMALL_EN_V1_5, cache_dir="/tmp/ace-fastembed")

    fastembed.assert_called_once_with(
        model_name="BAAI/bge-small-en-v1.5",
        cache_dir="/tmp/ace-fastembed",
    )
