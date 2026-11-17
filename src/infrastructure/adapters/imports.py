"""CSV spooling + PostgreSQL import job repository, behind ImportPort."""
import hashlib
from pathlib import Path
from uuid import uuid4

import aiofiles
import aiofiles.os
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from src.main.config import get_settings
from src.usecase.errors import AppError
from src.usecase.dto.imports import ImportJobDTO
from src.domain.models.imports import ImportJob, ImportErrorRow
from src.infrastructure.adapters.expenses import poke_worker

MAX_CSV_BYTES = 128 * 1024 * 1024

class SqlImportAdapter:
    def __init__(self, session, redis):
        self.session, self.redis = session, redis

    async def submit(self, actor, file):
        if not file.filename or not file.filename.lower().endswith(".csv"):
            raise AppError(422, "INVALID_CSV", "Upload a CSV file")
        spool_dir = Path(get_settings().import_spool_dir)
        await aiofiles.os.makedirs(str(spool_dir), exist_ok=True)
        path = spool_dir / f"{uuid4()}.csv"
        sha, size = hashlib.sha256(), 0
        try:
            async with aiofiles.open(path, "wb") as output:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_CSV_BYTES:
                        raise AppError(413, "CSV_TOO_LARGE", "CSV must be no larger than 128 MB")
                    sha.update(chunk)
                    await output.write(chunk)
            if size == 0:
                raise AppError(422, "EMPTY_CSV", "CSV file is empty")
            digest = sha.hexdigest()
            inserted = (await self.session.execute(pg_insert(ImportJob).values(
                user_id=actor.id, sha256=digest, spool_path=str(path), status="queued",
            ).on_conflict_do_nothing(index_elements=["user_id", "sha256"]).returning(ImportJob.id))).scalar_one_or_none()
            await self.session.commit()
            if inserted is None:
                await aiofiles.os.remove(path)
                job = await self.session.scalar(select(ImportJob).where(
                    ImportJob.user_id == actor.id, ImportJob.sha256 == digest))
            else:
                job = await self.session.get(ImportJob, inserted)
            await poke_worker(self.redis)
            return ImportJobDTO(id=job.id, status=job.status, rows_done=job.rows_done,
                                rows_failed=job.rows_failed, total_rows=job.total_rows, last_error=job.last_error)
        except Exception:
            if await aiofiles.os.path.exists(path):
                await aiofiles.os.remove(path)
            raise
        finally:
            await file.close()

    async def status(self, actor, job_id, error_after, error_limit):
        job = await self.session.scalar(select(ImportJob).where(
            ImportJob.id == job_id, ImportJob.user_id == actor.id))
        if job is None:
            raise AppError(404, "IMPORT_NOT_FOUND", "Import job not found")
        rows = (await self.session.scalars(select(ImportErrorRow).where(
            ImportErrorRow.job_id == job.id, ImportErrorRow.row_number > error_after
        ).order_by(ImportErrorRow.row_number).limit(error_limit + 1))).all()
        return ImportJobDTO(id=job.id, status=job.status, rows_done=job.rows_done,
                            rows_failed=job.rows_failed, total_rows=job.total_rows, last_error=job.last_error,
                            errors=[{"row_number": e.row_number, "reason": e.reason} for e in rows[:error_limit]],
                            next_error_cursor=rows[error_limit - 1].row_number if len(rows) > error_limit else None)
