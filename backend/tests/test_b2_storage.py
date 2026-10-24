import hashlib
from urllib.parse import parse_qs, urlsplit

import pytest
from botocore.exceptions import ClientError

from app.storage.b2 import B2Settings, B2Storage, StorageError
from app.storage.settings import StorageSettings


class FakeB2Client:
    def __init__(self):
        self.params = None
        self.head_result = {
            "ContentLength": 128,
            "ContentType": "application/pdf",
            "ETag": '"etag"',
        }
        self.deleted = None
        self.contents = b"x" * 128

    def generate_presigned_url(self, operation, *, Params, ExpiresIn, HttpMethod=None):
        self.params = Params
        return "https://b2.example/signed"

    def head_object(self, *, Bucket, Key):
        return self.head_result

    def get_object(self, *, Bucket, Key):
        class Body:
            def iter_chunks(self, chunk_size):
                for offset in range(0, len(self.contents), chunk_size):
                    yield self.contents[offset : offset + chunk_size]

            def close(self):
                pass

        body = Body()
        body.contents = self.contents
        return {"Body": body}

    def delete_object(self, *, Bucket, Key):
        self.deleted = (Bucket, Key)


def make_storage(client=None):
    settings = B2Settings(
        endpoint_url="https://s3.us-west-004.backblazeb2.com",
        bucket_name="private-bucket",
        access_key_id="test-key",
        secret_access_key="test-secret",
    )
    return B2Storage(settings, client=client or FakeB2Client())


def test_b2_configuration_requires_all_credentials():
    with pytest.raises(ValueError, match="required"):
        B2Settings("", "bucket", "key", "secret")
    with pytest.raises(ValueError, match="expiry"):
        B2Settings(
            "https://s3.example", "bucket", "key", "secret", signed_url_expiry_seconds=700000
        )
    with pytest.raises(ValueError, match="HTTPS origin"):
        B2Settings("http://s3.example", "bucket", "key", "secret")
    with pytest.raises(ValueError, match="configured together"):
        StorageSettings(b2_endpoint_url="https://s3.example")
    with pytest.raises(ValueError, match="HTTPS origin"):
        StorageSettings(
            b2_endpoint_url="http://s3.example",
            b2_bucket_name="bucket",
            b2_access_key_id="key",
            b2_application_key="secret",
        )


def test_storage_settings_create_b2_client_config_without_exposing_credentials():
    settings = StorageSettings(
        b2_endpoint_url="https://s3.us-west-004.backblazeb2.com",
        b2_bucket_name="private-bucket",
        b2_access_key_id="test-key",
        b2_application_key="test-secret",
    )
    b2_settings = settings.to_b2_settings()
    assert b2_settings.bucket_name == "private-bucket"
    assert "test-key" not in repr(b2_settings)
    assert "test-secret" not in repr(b2_settings)


def test_upload_authorization_is_scoped_to_generated_object_and_size():
    client = FakeB2Client()
    storage = make_storage(client)

    authorization = storage.authorize_upload("paper.pdf", "application/pdf", 128)

    assert authorization.url == "https://b2.example/signed"
    assert authorization.object_key.startswith("documents/")
    assert authorization.object_key.endswith(".pdf")
    assert authorization.required_headers == {
        "Content-Type": "application/pdf",
        "Content-Length": "128",
    }
    assert client.params == {
        "Bucket": "private-bucket",
        "Key": authorization.object_key,
        "ContentType": "application/pdf",
        "ContentLength": 128,
    }
    assert "test-secret" not in authorization.url
    assert authorization.url not in repr(authorization)


def test_boto_presigned_url_binds_upload_size_and_mime_type():
    settings = B2Settings(
        endpoint_url="https://s3.us-west-004.backblazeb2.com",
        bucket_name="private-bucket",
        access_key_id="test-key",
        secret_access_key="test-secret",
    )
    authorization = B2Storage(settings).authorize_upload("paper.pdf", "application/pdf", 128)
    signed_headers = parse_qs(urlsplit(authorization.url).query)["X-Amz-SignedHeaders"][0]
    assert "content-length" in signed_headers.split(";")
    assert "content-type" in signed_headers.split(";")


@pytest.mark.parametrize(
    "filename, content_type, size",
    [
        ("paper.exe", "application/pdf", 128),
        ("paper.pdf", "text/plain", 128),
        ("paper.pdf", "application/pdf", 0),
        ("paper.pdf", "application/pdf", 50 * 1024 * 1024 + 1),
    ],
)
def test_upload_validation_rejects_disallowed_inputs(filename, content_type, size):
    with pytest.raises(ValueError):
        make_storage().authorize_upload(filename, content_type, size)


def test_confirmation_checks_remote_size_and_mime_and_returns_integrity_metadata():
    storage = make_storage()
    result = storage.confirm_upload(
        "documents/abc/paper.pdf",
        expected_size_bytes=128,
        expected_content_type="application/pdf",
        expected_sha256=hashlib.sha256(b"x" * 128).hexdigest(),
    )
    assert result == {
        "bucket_name": "private-bucket",
        "object_key": "documents/abc/paper.pdf",
        "file_size_bytes": 128,
        "mime_type": "application/pdf",
        "sha256": hashlib.sha256(b"x" * 128).hexdigest(),
        "etag": "etag",
    }

    client = FakeB2Client()
    client.head_result["ContentLength"] = 127
    with pytest.raises(StorageError, match="size"):
        make_storage(client).confirm_upload(
            "documents/abc/paper.pdf",
            expected_size_bytes=128,
            expected_content_type="application/pdf",
        )


def test_confirmation_hashes_content_and_rejects_checksum_mismatch():
    with pytest.raises(StorageError, match="checksum"):
        make_storage().confirm_upload(
            "documents/abc/paper.pdf",
            expected_size_bytes=128,
            expected_content_type="application/pdf",
            expected_sha256="0" * 64,
        )


def test_private_assets_never_get_public_delivery_urls_and_storage_errors_surface():
    storage = make_storage()
    with pytest.raises(ValueError, match="Private"):
        storage.delivery_url("documents/abc/paper.pdf", is_public=False)
    with pytest.raises(ValueError, match="controlled"):
        storage.delivery_url("documents/../private.pdf", is_public=True)

    class MissingObjectClient(FakeB2Client):
        def head_object(self, *, Bucket, Key):
            raise ClientError(
                {"Error": {"Code": "404"}, "ResponseMetadata": {"HTTPStatusCode": 404}},
                "HeadObject",
            )

    with pytest.raises(StorageError, match="missing"):
        make_storage(MissingObjectClient()).confirm_upload(
            "documents/abc/paper.pdf",
            expected_size_bytes=128,
            expected_content_type="application/pdf",
        )
