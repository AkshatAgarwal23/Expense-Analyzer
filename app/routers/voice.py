from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user_id
from app.models import ExpenseSource
from app.schemas.expenses import ExpenseCreate, ExpenseRead
from app.schemas.voice import ExtractResponse, TranscriptRequest, TranscriptResponse
from app.services import expense_service, extraction_service, transcription_service
from app.services.errors import DomainError, NotFoundError, ValidationError
from app.services.extraction_service import ExtractionError
from app.services.transcription_service import TranscriptionError

router = APIRouter(prefix="/voice", tags=["voice"])


def _map_error(exc: DomainError) -> HTTPException:
    if isinstance(exc, NotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message)
    if isinstance(exc, ValidationError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message)
    if isinstance(exc, (TranscriptionError, ExtractionError)):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=exc.message
        )
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message)


@router.post("/transcribe", response_model=TranscriptResponse)
async def transcribe(
    file: UploadFile = File(...),
    caller_id: int = Depends(get_current_user_id),
) -> TranscriptResponse:
    _ = caller_id  # identity required; whisper itself is not user-scoped
    audio_bytes = await file.read()
    try:
        text = transcription_service.transcribe(
            audio_bytes, filename=file.filename or "audio.wav"
        )
    except DomainError as exc:
        raise _map_error(exc) from exc
    return TranscriptResponse(transcript=text)


@router.post("/extract", response_model=ExtractResponse)
def extract(
    body: TranscriptRequest,
    db: Session = Depends(get_db),
    caller_id: int = Depends(get_current_user_id),
) -> ExtractResponse:
    try:
        return extraction_service.extract_expense_draft(
            db, caller_id=caller_id, transcript=body.transcript
        )
    except DomainError as exc:
        raise _map_error(exc) from exc


@router.post(
    "/confirm",
    response_model=ExpenseRead,
    status_code=status.HTTP_201_CREATED,
)
def confirm(
    body: ExpenseCreate,
    db: Session = Depends(get_db),
    caller_id: int = Depends(get_current_user_id),
) -> ExpenseRead:
    # Voice path always tags source=voice even if client omits/overrides loosely.
    data = body.model_copy(update={"source": ExpenseSource.voice})
    try:
        expense = expense_service.create_expense(db, caller_id=caller_id, data=data)
    except DomainError as exc:
        raise _map_error(exc) from exc
    return ExpenseRead.model_validate(expense)
