from fastapi import APIRouter, Depends, status

from app.core.idempotency import IdempotencyState, idempotency
from app.dependencies import get_camera_usecase
from app.schemas.camera import CameraCreate, CameraResponse
from app.usecases.camera_usecase import CameraUseCase

router = APIRouter(prefix="/cameras", tags=["cameras"])


@router.post("", response_model=CameraResponse, status_code=status.HTTP_201_CREATED)
async def create_camera(
    payload: CameraCreate,
    usecase: CameraUseCase = Depends(get_camera_usecase),
    idem: IdempotencyState = Depends(idempotency),
) -> CameraResponse | dict:
    if idem.is_hit:
        return idem.cached_response
    result = await usecase.create(payload)
    await idem.store(result.model_dump(mode="json", by_alias=True))
    return result


@router.get("", response_model=list[CameraResponse])
async def list_cameras(
    usecase: CameraUseCase = Depends(get_camera_usecase),
) -> list[CameraResponse]:
    return await usecase.list()


@router.get("/{camera_id}", response_model=CameraResponse)
async def get_camera(
    camera_id: str,
    usecase: CameraUseCase = Depends(get_camera_usecase),
) -> CameraResponse:
    return await usecase.get(camera_id)


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_camera(
    camera_id: str,
    usecase: CameraUseCase = Depends(get_camera_usecase),
) -> None:
    await usecase.delete(camera_id)
