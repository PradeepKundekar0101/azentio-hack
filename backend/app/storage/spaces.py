"""DigitalOcean Spaces (S3-compatible), private objects, scoped to one key prefix in one bucket."""

from typing import Annotated

import boto3
from botocore.config import Config
from fastapi import Depends, Request

from app.core.config import Settings

PRESIGN_SECONDS = 5 * 60


class Storage:
    def __init__(self, client, bucket: str, prefix: str) -> None:
        self._client = client
        self._bucket = bucket
        self._prefix = prefix

    @classmethod
    def from_settings(cls, settings: Settings) -> "Storage":
        client = boto3.client(
            "s3",
            region_name=settings.spaces_region,
            endpoint_url=settings.spaces_endpoint_url,
            aws_access_key_id=settings.spaces_access_key_id.get_secret_value(),
            aws_secret_access_key=settings.spaces_secret_access_key.get_secret_value(),
            config=Config(
                signature_version="s3v4",
                connect_timeout=5,
                read_timeout=30,
                retries={"max_attempts": 2},
            ),
        )
        return cls(client, settings.spaces_bucket, settings.spaces_prefix)

    def key(self, name: str) -> str:
        return f"{self._prefix}{name}"

    def upload(self, name: str, body: bytes, content_type: str) -> str:
        key = self.key(name)
        self._client.put_object(Bucket=self._bucket, Key=key, Body=body, ContentType=content_type, ACL="private")
        return key

    def download(self, name: str) -> bytes:
        return self._client.get_object(Bucket=self._bucket, Key=self.key(name))["Body"].read()

    def delete(self, name: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=self.key(name))

    def presigned_download_url(self, name: str, expires_in: int = PRESIGN_SECONDS) -> str:
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": self.key(name)},
            ExpiresIn=expires_in,
        )

    def ping(self) -> None:
        self._client.list_objects_v2(Bucket=self._bucket, Prefix=self._prefix, MaxKeys=1)


def get_storage(request: Request) -> Storage:
    return request.app.state.storage


StorageDep = Annotated[Storage, Depends(get_storage)]
