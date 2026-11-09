import httpx
import pytest

from app.core.errors import ServiceError
from app.data_service.semantic import LocalEmbeddings, normalize
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
