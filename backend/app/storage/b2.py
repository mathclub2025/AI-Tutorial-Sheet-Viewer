import hashlib
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, urlsplit
from uuid import uuid4

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

ALLOWED_CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class StorageError(RuntimeError):
    """A B2 request failed or did not match the expected upload metadata."""


@dataclass(frozen=True)
class B2Settings:
    endpoint_url: str
    bucket_name: str
    access_key_id: str = field(repr=False)
    secret_access_key: str = field(repr=False)
    region: str = "us-west-004"
    delivery_base_url: str | None = None
    signed_url_expiry_seconds: int = 900
    max_upload_bytes: int = 50 * 1024 * 1024
    connect_timeout_seconds: int = 5
    read_timeout_seconds: int = 30

    def __post_init__(self):
        required = (
            self.endpoint_url,
            self.bucket_name,
            self.access_key_id,
            self.secret_access_key,
        )
        if any(not value.strip() for value in required):
            raise ValueError("B2 endpoint, bucket, access key, and application key are required")
        endpoint = urlsplit(self.endpoint_url)
        if (
            endpoint.scheme != "https"
            or not endpoint.hostname
            or endpoint.username
            or endpoint.password
            or endpoint.path
            or endpoint.query
            or endpoint.fragment
        ):
            raise ValueError("B2 endpoint must be an HTTPS origin without credentials")
        if self.signed_url_expiry_seconds < 1 or self.signed_url_expiry_seconds > 604800:
            raise ValueError("Signed URL expiry must be between 1 and 604800 seconds")
        if self.max_upload_bytes < 1:
            raise ValueError("Maximum upload size must be positive")
        if self.connect_timeout_seconds < 1 or self.read_timeout_seconds < 1:
            raise ValueError("Storage timeouts must be positive")
        if self.delivery_base_url:
            delivery = urlsplit(self.delivery_base_url)
            if (
                delivery.scheme not in {"https", "http"}
                or not delivery.hostname
                or delivery.username
                or delivery.password
                or delivery.query
                or delivery.fragment
            ):
                raise ValueError("Delivery URL must be HTTP(S) without credentials or query")


@dataclass(frozen=True)
class UploadAuthorization:
    object_key: str
    url: str = field(repr=False)
    required_headers: dict[str, str]
    expires_in_seconds: int
    max_size_bytes: int


class B2Storage:
    def __init__(self, settings: B2Settings, client: Any | None = None):
        self.settings = settings
        self.client = client or boto3.client(
            "s3",
            endpoint_url=settings.endpoint_url,
            aws_access_key_id=settings.access_key_id,
            aws_secret_access_key=settings.secret_access_key,
            region_name=settings.region,
            config=Config(
                signature_version="s3v4",
                connect_timeout=settings.connect_timeout_seconds,
                read_timeout=settings.read_timeout_seconds,
                retries={"max_attempts": 2, "mode": "standard"},
            ),
        )

    @staticmethod
    def _validated_file(filename: str, content_type: str, size_bytes: int, max_size: int) -> str:
        suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        expected_type = ALLOWED_CONTENT_TYPES.get(suffix)
        if expected_type is None or expected_type != content_type.lower():
            raise ValueError(
                "Only PDF and DOCX uploads with matching declared MIME types are allowed"
            )
        if size_bytes < 1 or size_bytes > max_size:
            raise ValueError(f"Upload size must be between 1 and {max_size} bytes")
        return suffix

    @classmethod
    def new_object_key(
        cls, filename: str, content_type: str, size_bytes: int, max_size: int
    ) -> str:
        suffix = cls._validated_file(filename, content_type, size_bytes, max_size)
        return f"documents/{uuid4()}/{uuid4()}{suffix}"

    def authorize_upload(
        self, filename: str, content_type: str, size_bytes: int
    ) -> UploadAuthorization:
        self._validated_file(filename, content_type, size_bytes, self.settings.max_upload_bytes)
        key = self.new_object_key(
            filename, content_type, size_bytes, self.settings.max_upload_bytes
        )
        params = {
            "Bucket": self.settings.bucket_name,
            "Key": key,
            "ContentType": content_type,
            "ContentLength": size_bytes,
        }
        try:
            url = self.client.generate_presigned_url(
                "put_object",
                Params=params,
                ExpiresIn=self.settings.signed_url_expiry_seconds,
                HttpMethod="PUT",
            )
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("Could not authorize object upload") from exc
        return UploadAuthorization(
            object_key=key,
            url=url,
            required_headers={"Content-Type": content_type, "Content-Length": str(size_bytes)},
            expires_in_seconds=self.settings.signed_url_expiry_seconds,
            max_size_bytes=size_bytes,
        )

    @staticmethod
    def _validate_object_key(object_key: str) -> None:
        parts = object_key.split("/")
        if (
            len(parts) != 3
            or parts[0] != "documents"
            or any(part in {"", ".", ".."} for part in parts)
            or "\\" in object_key
            or "\x00" in object_key
        ):
            raise ValueError("Object key must be a controlled documents/ path")

    def confirm_upload(
        self,
        object_key: str,
        *,
        expected_size_bytes: int,
        expected_content_type: str,
        expected_sha256: str | None = None,
    ) -> dict[str, Any]:
        self._validate_object_key(object_key)
        self._validated_file(
            object_key.rsplit("/", 1)[-1],
            expected_content_type,
            expected_size_bytes,
            self.settings.max_upload_bytes,
        )
        try:
            metadata = self.client.head_object(Bucket=self.settings.bucket_name, Key=object_key)
        except (BotoCoreError, ClientError) as exc:
            raise StorageError(
                "Uploaded object is missing or its metadata could not be read"
            ) from exc
        if metadata.get("ContentLength") != expected_size_bytes:
            raise StorageError("Uploaded object size does not match the authorized size")
        if metadata.get("ContentType", "").lower() != expected_content_type.lower():
            raise StorageError("Uploaded object content type does not match the authorized type")
        body = None
        digest = hashlib.sha256()
        streamed_size = 0
        try:
            body = self.client.get_object(Bucket=self.settings.bucket_name, Key=object_key)["Body"]
            for chunk in body.iter_chunks(chunk_size=1024 * 1024):
                streamed_size += len(chunk)
                if streamed_size > expected_size_bytes:
                    raise StorageError("Uploaded object exceeds the authorized size")
                digest.update(chunk)
        except StorageError:
            raise
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("Could not verify uploaded object contents") from exc
        finally:
            if body is not None:
                body.close()
        if streamed_size != expected_size_bytes:
            raise StorageError("Uploaded object content length does not match")
        verified_sha256 = digest.hexdigest()
        if expected_sha256 and verified_sha256.lower() != expected_sha256.lower():
            raise StorageError("Uploaded object checksum does not match")
        return {
            "bucket_name": self.settings.bucket_name,
            "object_key": object_key,
            "file_size_bytes": metadata["ContentLength"],
            "mime_type": metadata["ContentType"],
            "sha256": verified_sha256,
            "etag": metadata.get("ETag", "").strip('"'),
        }

    def object_exists(self, object_key: str) -> bool:
        self._validate_object_key(object_key)
        try:
            self.client.head_object(Bucket=self.settings.bucket_name, Key=object_key)
        except ClientError as exc:
            if exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 404:
                return False
            raise StorageError("Could not check object existence") from exc
        except BotoCoreError as exc:
            raise StorageError("Could not check object existence") from exc
        return True

    def download_url(self, object_key: str) -> str:
        self._validate_object_key(object_key)
        try:
            return self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.settings.bucket_name, "Key": object_key},
                ExpiresIn=self.settings.signed_url_expiry_seconds,
            )
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("Could not authorize object download") from exc

    def delivery_url(self, object_key: str, *, is_public: bool) -> str:
        self._validate_object_key(object_key)
        if not is_public:
            raise ValueError("Private documents must use an authorized download URL")
        if not self.settings.delivery_base_url:
            raise ValueError("Public delivery is not configured")
        encoded_key = quote(object_key, safe="/")
        return f"{self.settings.delivery_base_url.rstrip('/')}/{encoded_key}"

    def delete_object(self, object_key: str) -> None:
        self._validate_object_key(object_key)
        try:
            self.client.delete_object(Bucket=self.settings.bucket_name, Key=object_key)
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("Could not delete object") from exc
