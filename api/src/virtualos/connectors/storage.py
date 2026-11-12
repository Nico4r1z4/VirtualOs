"""Raw batch persistence: S3 when configured, local .data/raw otherwise."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from virtualos.config.settings import get_settings
from virtualos.connectors.base import RawBatch

logger = logging.getLogger(__name__)


async def save_raw(workspace_id: str, batch: RawBatch) -> str | None:
    """Persist the raw payload for audit/replay. Returns the storage key, or None."""
    settings = get_settings()
    ts = datetime.now(UTC).strftime("%Y%m%d/%H%M%S")
    safe_source = batch.source.replace(":", "_").replace("/", "_")
    key = f"raw/{workspace_id}/{ts}-{safe_source}.json"
    body = json.dumps({"source": batch.source, "meta": batch.meta, "items": batch.items})

    if settings.s3_bucket:
        try:
            import boto3  # lazy: only needed when S3 is configured

            s3 = boto3.client("s3", region_name=settings.aws_region)
            s3.put_object(Bucket=settings.s3_bucket, Key=key, Body=body.encode("utf-8"))
            return f"s3://{settings.s3_bucket}/{key}"
        except Exception:
            logger.exception("S3 save failed; falling back to local")

    path = Path(settings.raw_data_dir) / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return str(path)
