import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import authorize_role
from app.models import (
    Course, CourseModule, Enrollment, Invoice, LearningProgress, Order, User,
)
from app.schemas import (
    ApiResponse, EnrollmentCreatedOut, EnrollmentCreateIn, MyCourseOut,
    ProgressIn, ProgressOut, ok,
)

router = APIRouter(prefix="/enrollments", tags=["Enrollments"])
student_only = authorize_role("student")


@router.post("", status_code=201, response_model=ApiResponse[EnrollmentCreatedOut])
def create_enrollment(
    body: EnrollmentCreateIn,
    db: Session = Depends(get_db),
    user: User = Depends(student_only),
):
    course = db.get(Course, body.course_id)
    if course is None or not course.is_published:
        raise HTTPException(404, "Kursus tidak ditemukan")

    already = db.scalar(
        select(Enrollment).where(
            Enrollment.student_id == user.id, Enrollment.course_id == course.id
        )
    )
    if already:
        raise HTTPException(409, "Anda sudah terdaftar di kursus ini")

    # Order -> Invoice -> Enrollment dalam SATU transaksi
    order = Order(student_id=user.id, course_id=course.id, total_amount=course.price)
    db.add(order)
    db.flush()  # agar order.id terisi

    invoice = Invoice(
        order_id=order.id,
        invoice_number=f"INV-{datetime.now():%Y%m%d}-{order.id.hex[:8].upper()}",
        amount=course.price,
    )
    enrollment = Enrollment(
        student_id=user.id, course_id=course.id, order_id=order.id,
        status="pending_payment",
    )
    db.add_all([invoice, enrollment])
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Anda sudah terdaftar di kursus ini")

    return ok(
        {"enrollment": enrollment, "order": order, "invoice": invoice},
        "Enrollment dibuat, silakan lakukan pembayaran",
    )


@router.get("/mycourses", response_model=ApiResponse[list[MyCourseOut]])
def my_courses(db: Session = Depends(get_db), user: User = Depends(student_only)):
    enrollments = db.scalars(
        select(Enrollment)
        .where(Enrollment.student_id == user.id)
        .options(selectinload(Enrollment.course).selectinload(Course.modules))
        .order_by(Enrollment.created_at.desc())
    ).all()

    done_map = dict(
        db.execute(
            select(LearningProgress.enrollment_id, func.count())
            .where(
                LearningProgress.enrollment_id.in_([e.id for e in enrollments]),
                LearningProgress.status == "completed",
            )
            .group_by(LearningProgress.enrollment_id)
        ).all()
    )

    result = []
    for e in enrollments:
        total = len(e.course.modules)
        done = done_map.get(e.id, 0)
        result.append(
            {
                "enrollment_id": e.id,
                "course_id": e.course_id,
                "title": e.course.title,
                "status": e.status,
                "completed_modules": done,
                "total_modules": total,
                "progress_percentage": round(done / total * 100, 2) if total else 0.0,
            }
        )
    return ok(result)


@router.patch("/{enrollment_id}/progress", response_model=ApiResponse[ProgressOut])
def update_progress(
    enrollment_id: uuid.UUID,
    body: ProgressIn,
    db: Session = Depends(get_db),
    user: User = Depends(student_only),
):
    enrollment = db.get(Enrollment, enrollment_id)
    # 404 (bukan 403) agar tidak membocorkan keberadaan data milik orang lain
    if enrollment is None or enrollment.student_id != user.id:
        raise HTTPException(404, "Enrollment tidak ditemukan")
    if enrollment.status == "pending_payment":
        raise HTTPException(403, "Enrollment belum aktif, selesaikan pembayaran terlebih dahulu")

    module = db.get(CourseModule, body.module_id)
    if module is None or module.course_id != enrollment.course_id:
        raise HTTPException(404, "Modul tidak ditemukan di kursus ini")

    progress = db.scalar(
        select(LearningProgress).where(
            LearningProgress.enrollment_id == enrollment.id,
            LearningProgress.module_id == module.id,
        )
    )
    if progress is None:
        progress = LearningProgress(enrollment_id=enrollment.id, module_id=module.id)
        db.add(progress)

    progress.status = body.status
    progress.completed_at = datetime.now(timezone.utc) if body.status == "completed" else None
    db.flush()

    total = db.scalar(
        select(func.count()).select_from(CourseModule)
        .where(CourseModule.course_id == enrollment.course_id)
    )
    done = db.scalar(
        select(func.count()).select_from(LearningProgress)
        .where(
            LearningProgress.enrollment_id == enrollment.id,
            LearningProgress.status == "completed",
        )
    )
    enrollment.status = "completed" if total and done == total else "active"
    db.commit()

    return ok(
        {
            "enrollment_id": enrollment.id,
            "enrollment_status": enrollment.status,
            "completed_modules": done,
            "total_modules": total,
            "progress_percentage": round(done / total * 100, 2) if total else 0.0,
        },
        "Progress diperbarui",
    )
