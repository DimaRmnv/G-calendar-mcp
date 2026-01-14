"""
Export router for downloading generated report files.

Provides endpoint for downloading Excel files by UUID.
Files expire after 1 hour (TTL enforced by database).
Includes background cleanup task for expired files.
"""

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from google_calendar.db.connection import get_db

logger = logging.getLogger(__name__)

export_router = APIRouter(prefix="/export", tags=["export"])

# Cleanup interval in seconds (15 minutes)
CLEANUP_INTERVAL = 15 * 60


async def cleanup_expired_reports():
    """
    Delete expired report files from disk and mark as deleted in DB.

    Only processes files from /data/reports directory.
    Runs every 15 minutes as background task.
    """
    while True:
        try:
            await asyncio.sleep(CLEANUP_INTERVAL)

            async with get_db() as conn:
                # Find expired files that haven't been deleted yet
                rows = await conn.fetch(
                    """
                    SELECT id, uuid, file_path
                    FROM export_files
                    WHERE expires_at < NOW()
                      AND NOT is_deleted
                      AND file_path LIKE '/data/reports/%'
                    """
                )

            if not rows:
                continue

            deleted_count = 0
            for row in rows:
                file_path = Path(row["file_path"])

                # Delete physical file if exists
                if file_path.exists():
                    try:
                        file_path.unlink()
                        deleted_count += 1
                    except OSError as e:
                        logger.warning(f"Failed to delete {file_path}: {e}")
                        continue

                # Mark as deleted in DB
                async with get_db() as conn:
                    await conn.execute(
                        "UPDATE export_files SET is_deleted = TRUE WHERE id = $1",
                        row["id"]
                    )

            if deleted_count > 0:
                logger.info(f"Cleanup: deleted {deleted_count} expired report files")

        except Exception as e:
            logger.error(f"Cleanup task error: {e}")


@export_router.get("/{file_uuid}")
async def download_export(file_uuid: str):
    """
    Download exported file by UUID.

    Returns the Excel file if:
    - UUID exists in database
    - File has not expired (TTL = 1 hour)
    - File exists on disk

    Raises:
        404: File not found
        410: File expired
    """
    async with get_db() as conn:
        row = await conn.fetchrow(
            """
            SELECT file_path, filename, expires_at
            FROM export_files
            WHERE uuid = $1 AND NOT is_deleted
            """,
            file_uuid
        )

    if not row:
        raise HTTPException(status_code=404, detail="File not found")

    if row["expires_at"] < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="File expired")

    file_path = Path(row["file_path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    # Mark as downloaded
    async with get_db() as conn:
        await conn.execute(
            "UPDATE export_files SET downloaded_at = NOW() WHERE uuid = $1",
            file_uuid
        )

    return FileResponse(
        path=file_path,
        filename=row["filename"],
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{row["filename"]}"'
        }
    )
