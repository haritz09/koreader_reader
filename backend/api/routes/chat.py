"""Spoiler-safe chat over the reader's visible text."""

from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies import get_answer_question_use_case, get_current_owner
from api.presenters.chat import chat_response
from api.schemas.chat import ChatRequest, ChatResponse
from core.domain.errors import BookNotFoundError, BookNotReadyError
from rag.application.answer_question import AnswerQuestionUseCase
from rag.domain.errors import RagIndexNotReadyError

router = APIRouter(prefix="/ebooks", tags=["chat"])


@router.post("/{book_id}/chat", response_model=ChatResponse)
async def chat_with_book(
    book_id: str,
    payload: ChatRequest,
    owner_id: str = Depends(get_current_owner),
    use_case: AnswerQuestionUseCase = Depends(get_answer_question_use_case),
) -> ChatResponse:
    try:
        answer = await use_case.execute(owner_id, book_id, payload.question)
    except BookNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Book not found"
        ) from error
    except (BookNotReadyError, RagIndexNotReadyError) as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error

    return chat_response(answer)
