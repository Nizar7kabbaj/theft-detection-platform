from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status

from app.core.idempotency import IdempotencyState, idempotency
from app.dependencies import get_detection_usecase, get_inference_client
from app.schemas.detection import DetectionCreate, DetectionResponse
from app.services.inference_service import InferenceClient
from app.usecases.detection_usecase import DetectionUseCase

router = APIRouter(prefix="/detections", tags=["detections"])


@router.post("", response_model=DetectionResponse, status_code=status.HTTP_201_CREATED)
async def create_detection(
    payload: DetectionCreate,
    usecase: DetectionUseCase = Depends(get_detection_usecase),
    idem: IdempotencyState = Depends(idempotency),
) -> DetectionResponse:
    if idem.is_hit:
        return DetectionResponse.model_validate(idem.cached_response)
    result = await usecase.create(payload)
    await idem.store(result.model_dump(mode="json", by_alias=True))
    return result


@router.post(
    "/analyze",
    response_model=DetectionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def analyze_frame(
    session_id: int = Form(...),
    frame_index: int = Form(...),
    camera_id: str = Form("default"),
    file: UploadFile = File(...),
    usecase: DetectionUseCase = Depends(get_detection_usecase),
    client: InferenceClient = Depends(get_inference_client),
) -> DetectionResponse:
    payload = await file.read()
    return await usecase.analyze_frame(
        client=client,
        payload=payload,
        session_id=session_id,
        frame_index=frame_index,
        camera_id=camera_id,
    )


@router.get("", response_model=list[DetectionResponse])
async def list_detections(
    limit: int = Query(default=50, le=200),
    skip: int = Query(default=0, ge=0),
    usecase: DetectionUseCase = Depends(get_detection_usecase),
) -> list[DetectionResponse]:
    return await usecase.list(limit=limit, skip=skip)


@router.get("/session/{session_id}", response_model=list[DetectionResponse])
async def list_detections_by_session(
    session_id: int,
    usecase: DetectionUseCase = Depends(get_detection_usecase),
) -> list[DetectionResponse]:
    return await usecase.list_by_session(session_id)


@router.delete("/{detection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_detection(
    detection_id: str,
    usecase: DetectionUseCase = Depends(get_detection_usecase),
) -> None:
    await usecase.delete(detection_id)
