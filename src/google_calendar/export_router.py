"""
Export router for downloading generated report files.

Provides endpoint for downloading Excel files by UUID.
Files expire after 1 hour (TTL enforced by database).
"""

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from google_calendar.db.connection import get_db

export_router = APIRouter(prefix="/export", tags=["export"])


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
