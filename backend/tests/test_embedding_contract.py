import sys
import types

import httpx
import pytest

from app.core.errors import ServiceError
from app.data_service.semantic import (
    FastEmbedEmbeddings,
    LocalEmbeddings,
    build_embeddings,
    normalize,
)
from app.data_service.settings import DataServiceSettings


@pytest.mark.parametrize("vector", [[0, 0, 0], [1, 2], [1, float("inf"), 0], [float("nan"), 0, 1]])
def test_invalid_embedding_values_are_rejected(vector):
    with pytest.raises(ServiceError, match="Embedding"):
        normalize(vector, 3)


def test_local_embedding_http_contract_checks_auth_batch_model_and_normalization():
    settings = DataServiceSettings(
        _env_file=None,
        embedding_base_url="http://local-ai.test",
        embedding_service_token="embeddings-key",
        embedding_model="local-v1",
        embedding_dimensions=3,
    )

    def peer(request):
        assert request.headers["X-Internal-Token"] == "embeddings-key"
        assert request.url.path == "/internal/v1/embeddings"
        return httpx.Response(200, json={"model": "local-v1", "vectors": [[3, 4, 0]]})

    with httpx.Client(transport=httpx.MockTransport(peer)) as client:
        assert LocalEmbeddings(settings, client).embed(["Differentiate"]) == [[0.6, 0.8, 0.0]]
    for body in (
        {"model": "other", "vectors": [[1, 0, 0]]},
        {"model": "local-v1", "vectors": [[1, 0, 0], [1, 0, 0]]},
        {"model": "local-v1", "vectors": [[1, 0]]},
    ):
        with httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body))
        ) as client:
            with pytest.raises(ServiceError):
                LocalEmbeddings(settings, client).embed(["Differentiate"])


def test_unconfigured_embeddings_fail_explicitly():
    with pytest.raises(ServiceError) as exc:
        LocalEmbeddings(DataServiceSettings(_env_file=None)).embed(["query"])
    assert exc.value.code == "EMBEDDINGS_NOT_CONFIGURED"


def test_build_embeddings_selects_provider_by_configuration():
    assert type(build_embeddings(DataServiceSettings(_env_file=None))) is LocalEmbeddings
    fastembed_settings = DataServiceSettings(
        _env_file=None,
        embedding_provider="fastembed",
        embedding_model="BAAI/bge-small-en-v1.5",
        embedding_dimensions=384,
    )
    assert type(build_embeddings(fastembed_settings)) is FastEmbedEmbeddings
    with pytest.raises(ServiceError) as exc:
        build_embeddings(DataServiceSettings(_env_file=None, embedding_provider="widget"))
    assert exc.value.code == "EMBEDDING_PROVIDER_UNKNOWN"


def test_fastembed_adapter_validates_model_batch_and_normalization(monkeypatch):
    class FakeTextEmbedding:
        def __init__(self, model_name):
            assert model_name == "BAAI/bge-small-en-v1.5"

        def embed(self, texts):
            return [[3, 4, 0] for _ in texts]

    module = types.ModuleType("fastembed")
    module.TextEmbedding = FakeTextEmbedding
    monkeypatch.setitem(sys.modules, "fastembed", module)
    settings = DataServiceSettings(
        _env_file=None,
        embedding_provider="fastembed",
        embedding_model="BAAI/bge-small-en-v1.5",
        embedding_dimensions=3,
    )
    adapter = FastEmbedEmbeddings(settings)
    assert adapter.embed(["a", "b"]) == [[0.6, 0.8, 0.0], [0.6, 0.8, 0.0]]
    with pytest.raises(ServiceError) as empty:
        adapter.embed([])
    assert empty.value.code == "INVALID_EMBEDDING"

    class MismatchedEmbedding(FakeTextEmbedding):
        def embed(self, texts):
            return [[3, 4, 0]]

    module.TextEmbedding = MismatchedEmbedding
    with pytest.raises(ServiceError) as mismatch:
        FastEmbedEmbeddings(settings).embed(["a", "b"])
    assert mismatch.value.code == "INVALID_EMBEDDING"


def test_fastembed_adapter_wraps_model_load_failures(monkeypatch):
    class BrokenEmbedding:
        def __init__(self, model_name):
            raise RuntimeError("weights unavailable")

    module = types.ModuleType("fastembed")
    module.TextEmbedding = BrokenEmbedding
    monkeypatch.setitem(sys.modules, "fastembed", module)
    settings = DataServiceSettings(
        _env_file=None,
        embedding_provider="fastembed",
        embedding_model="BAAI/bge-small-en-v1.5",
        embedding_dimensions=384,
    )
    with pytest.raises(ServiceError) as exc:
        FastEmbedEmbeddings(settings).embed(["query"])
    assert exc.value.code == "EMBEDDING_PROVIDER_UNAVAILABLE"


def test_missing_fastembed_dependency_fails_explicitly(monkeypatch):
    monkeypatch.setitem(sys.modules, "fastembed", None)
    settings = DataServiceSettings(
        _env_file=None,
        embedding_provider="fastembed",
        embedding_model="BAAI/bge-small-en-v1.5",
        embedding_dimensions=384,
    )
    with pytest.raises(ServiceError) as exc:
        FastEmbedEmbeddings(settings).embed(["query"])
    assert exc.value.code == "EMBEDDING_PROVIDER_UNAVAILABLE"
