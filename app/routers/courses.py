import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import authorize_role
from app.models import Category, Course, User
from app.schemas import ApiResponse, CourseCreateIn, CourseDetailOut, CourseOut, ok

router = APIRouter(prefix="/courses", tags=["Courses"])


@router.get("", response_model=ApiResponse[list[CourseOut]])
def list_courses(
    q: str | None = None,
    category_id: uuid.UUID | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = select(Course).where(Course.is_published.is_(True))
    if q:
        stmt = stmt.where(Course.title.ilike(f"%{q}%"))
    if category_id:
        stmt = stmt.where(Course.category_id == category_id)
    stmt = stmt.order_by(Course.created_at.desc()).limit(limit).offset(offset)
    return ok(db.scalars(stmt).all())


@router.get("/{course_id}", response_model=ApiResponse[CourseDetailOut])
def get_course(course_id: uuid.UUID, db: Session = Depends(get_db)):
    course = db.scalar(
        select(Course)
        .where(Course.id == course_id, Course.is_published.is_(True))
        .options(selectinload(Course.modules))
    )
    if course is None:
        raise HTTPException(404, "Kursus tidak ditemukan")
    return ok(course)


@router.post("", status_code=201, response_model=ApiResponse[CourseOut])
def create_course(
    body: CourseCreateIn,
    db: Session = Depends(get_db),
    user: User = Depends(authorize_role("instructor", "admin")),
):
    if db.get(Category, body.category_id) is None:
        raise HTTPException(404, "Kategori tidak ditemukan")
    course = Course(**body.model_dump(), instructor_id=user.id)
    db.add(course)
    db.commit()
    return ok(course, "Kursus berhasil dibuat")
