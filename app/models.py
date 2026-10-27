import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, Integer,
    Numeric, String, Text, UniqueConstraint, Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('student','instructor','admin')", name="ck_users_role"),
    )
    id: Mapped[uuid.UUID] = pk()
    full_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="student")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Category(Base):
    __tablename__ = "categories"
    id: Mapped[uuid.UUID] = pk()
    name: Mapped[str] = mapped_column(String(100), unique=True)


class Course(Base):
    __tablename__ = "courses"
    id: Mapped[uuid.UUID] = pk()
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.id"))
    instructor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(Text, default="")
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    is_published: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    modules: Mapped[list["CourseModule"]] = relationship(
        order_by="CourseModule.position", back_populates="course"
    )


class CourseModule(Base):
    __tablename__ = "course_modules"
    __table_args__ = (UniqueConstraint("course_id", "position", name="uq_module_position"),)
    id: Mapped[uuid.UUID] = pk()
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id"))
    title: Mapped[str] = mapped_column(String(150))
    position: Mapped[int] = mapped_column(Integer)

    course: Mapped["Course"] = relationship(back_populates="modules")


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("status IN ('pending','paid','cancelled')", name="ck_orders_status"),
    )
    id: Mapped[uuid.UUID] = pk()
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id"))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        CheckConstraint("status IN ('unpaid','paid','void')", name="ck_invoices_status"),
    )
    id: Mapped[uuid.UUID] = pk()
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"), unique=True)
    invoice_number: Mapped[str] = mapped_column(String(50), unique=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(20), default="unpaid")
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("status IN ('pending','paid','failed')", name="ck_payments_status"),
    )
    id: Mapped[uuid.UUID] = pk()
    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id"))
    method: Mapped[str] = mapped_column(String(30))
    external_ref: Mapped[str] = mapped_column(String(60), unique=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint("student_id", "course_id", name="uq_enrollment_student_course"),
        CheckConstraint(
            "status IN ('pending_payment','active','completed')", name="ck_enrollments_status"
        ),
    )
    id: Mapped[uuid.UUID] = pk()
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id"))
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="pending_payment")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    course: Mapped["Course"] = relationship()


class LearningProgress(Base):
    __tablename__ = "learning_progress"
    __table_args__ = (
        UniqueConstraint("enrollment_id", "module_id", name="uq_progress_enrollment_module"),
        CheckConstraint("status IN ('in_progress','completed')", name="ck_progress_status"),
    )
    id: Mapped[uuid.UUID] = pk()
    enrollment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("enrollments.id"))
    module_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("course_modules.id"))
    status: Mapped[str] = mapped_column(String(20), default="in_progress")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
