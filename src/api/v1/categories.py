from fastapi import APIRouter
from src.main.ioc.dependencies import CategoriesDep, UserDep
from src.usecase.dto.categories import CategoryCreate, CategoryDTO

router = APIRouter(prefix="/categories", tags=["Categories"])

@router.post("", response_model=CategoryDTO, status_code=201)
async def create_category(payload: CategoryCreate, service: CategoriesDep, user: UserDep):
    return await service.create(user, payload)

@router.get("", response_model=list[CategoryDTO])
async def list_categories(service: CategoriesDep, user: UserDep):
    return await service.list(user)
