"""Lectures, chunked upload, and job monitoring router."""

import uuid

from fastapi import APIRouter, Body, Depends, Header, Path, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models.user import User
from app.schemas.course import StatusResponse
from app.schemas.lecture import (
    ChunkUploadResponse,
    JobOut,
    LectureCreate,
    LectureCreateResponse,
    LectureOut,
    LectureUpdate,
    UploadCompleteResponse,
)
from app.services.lecture_service import (
    complete_lecture_upload,
    create_lecture,
    delete_lecture,
    get_lecture_detail,
    list_course_lectures,
    list_lecture_jobs,
    save_upload_chunk,
    update_lecture,
)

router = APIRouter(tags=["lectures"])


@router.get(
    "/courses/{id}/lectures",
    response_model=list[LectureOut],
    summary="List lectures in a course",
    description="Members see course lectures (students see only published and ready lectures).",
)
async def get_course_lectures(
    course_id: uuid.UUID = Path(..., alias="id"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[LectureOut]:
    lectures = await list_course_lectures(db=db, course_id=course_id, user=current_user)
    return [LectureOut.model_validate(lec) for lec in lectures]


@router.post(
    "/courses/{id}/lectures",
    response_model=LectureCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create lecture record",
    description="Course owners create a lecture and obtain a resumable upload URL.",
)
async def create_new_lecture(
    course_id: uuid.UUID = Path(..., alias="id"),
    payload: LectureCreate = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LectureCreateResponse:
    lecture, upload_url = await create_lecture(
        db=db,
        course_id=course_id,
        user=current_user,
        data=payload,
    )
    return LectureCreateResponse(
        lecture=LectureOut.model_validate(lecture),
        upload_url=upload_url,
    )


@router.put(
    "/lectures/{id}/upload",
    response_model=ChunkUploadResponse,
    summary="Resumable chunked upload",
    description="Upload raw byte chunks with Content-Range header.",
)
async def upload_lecture_chunk(
    request: Request,
    lecture_id: uuid.UUID = Path(..., alias="id"),
    content_range: str | None = Header(None, alias="Content-Range"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChunkUploadResponse:
    chunk_data = await request.body()
    written, current_size, total = await save_upload_chunk(
        db=db,
        lecture_id=lecture_id,
        user=current_user,
        content_range_hdr=content_range,
        chunk_data=chunk_data,
    )
    is_complete = total is not None and current_size >= total
    return ChunkUploadResponse(
        bytes_written=written,
        current_size=current_size,
        total_size=total,
        status="uploaded" if is_complete else "incomplete",
    )


@router.post(
    "/lectures/{id}/upload/complete",
    response_model=UploadCompleteResponse,
    summary="Complete lecture upload",
    description="Mark upload complete, set status to processing, and queue transcoding.",
)
async def complete_upload(
    lecture_id: uuid.UUID = Path(..., alias="id"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UploadCompleteResponse:
    lecture, job = await complete_lecture_upload(
        db=db,
        lecture_id=lecture_id,
        user=current_user,
    )
    return UploadCompleteResponse(
        status="processing",
        job_id=job.id,
        lecture=LectureOut.model_validate(lecture),
    )


@router.get(
    "/lectures/{id}",
    response_model=LectureOut,
    summary="Get lecture details",
    description="View lecture details if enrolled and ready or course owner/admin.",
)
async def get_lecture(
    lecture_id: uuid.UUID = Path(..., alias="id"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LectureOut:
    lecture = await get_lecture_detail(
        db=db,
        lecture_id=lecture_id,
        user=current_user,
    )
    return LectureOut.model_validate(lecture)


@router.patch(
    "/lectures/{id}",
    response_model=LectureOut,
    summary="Update lecture",
    description="Edit lecture title, description, order, or published status (owner only).",
)
async def patch_lecture(
    lecture_id: uuid.UUID = Path(..., alias="id"),
    payload: LectureUpdate = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LectureOut:
    lecture = await update_lecture(
        db=db,
        lecture_id=lecture_id,
        user=current_user,
        data=payload,
    )
    return LectureOut.model_validate(lecture)


@router.delete(
    "/lectures/{id}",
    response_model=StatusResponse,
    summary="Delete lecture",
    description="Delete lecture and all associated media files from disk.",
)
async def remove_lecture(
    lecture_id: uuid.UUID = Path(..., alias="id"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StatusResponse:
    await delete_lecture(
        db=db,
        lecture_id=lecture_id,
        user=current_user,
    )
    return StatusResponse(status="ok")


@router.get(
    "/lectures/{id}/jobs",
    response_model=list[JobOut],
    summary="List lecture jobs",
    description="View pipeline processing jobs for a lecture (owner only).",
)
async def get_lecture_jobs(
    lecture_id: uuid.UUID = Path(..., alias="id"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[JobOut]:
    jobs = await list_lecture_jobs(
        db=db,
        lecture_id=lecture_id,
        user=current_user,
    )
    return [JobOut.model_validate(j) for j in jobs]
