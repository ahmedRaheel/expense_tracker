from uuid import UUID
from fastapi import APIRouter, UploadFile, File, Query
from src.main.ioc.dependencies import ImportsDep, UserDep
from src.usecase.dto.imports import ImportJobDTO

router = APIRouter(tags=["CSV imports"])

@router.post("/expenses/import", response_model=ImportJobDTO, status_code=202)
async def upload_csv(service: ImportsDep, user: UserDep, file: UploadFile = File(...)):
    return await service.submit(user, file)

@router.get("/imports/{job_id}", response_model=ImportJobDTO)
async def status(job_id: UUID, service: ImportsDep, user: UserDep,
                 error_after: int = Query(0, ge=0), error_limit: int = Query(100, ge=1, le=1000)):
    return await service.status(user, job_id, error_after, error_limit)
