import uuid
from datetime import datetime
from decimal import Decimal
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    message: str
    data: T | None = None
    errors: list[dict] | None = None


def ok(data=None, message: str = "Berhasil") -> dict:
    return {"message": message, "data": data, "errors": None}


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Auth ----------
class RegisterIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8)

    @field_validator("password")
    @classmethod
    def max_72_bytes(cls, v: str) -> str:
        # bcrypt hanya membaca 72 byte pertama; tolak yang lebih panjang
        if len(v.encode()) > 72:
            raise ValueError("Password maksimal 72 byte")
        return v


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(ORMModel):
    id: uuid.UUID
    full_name: str
    email: str
    role: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str
    user: UserOut


# ---------- Courses ----------
class CourseCreateIn(BaseModel):
    category_id: uuid.UUID
    title: str = Field(min_length=3, max_length=150)
    description: str = ""
    price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)


class ModuleOut(ORMModel):
    id: uuid.UUID
    title: str
    position: int


class CourseOut(ORMModel):
    id: uuid.UUID
    category_id: uuid.UUID
    instructor_id: uuid.UUID
    title: str
    description: str
    price: Decimal
    is_published: bool


class CourseDetailOut(CourseOut):
    modules: list[ModuleOut]


# ---------- Enrollments ----------
class EnrollmentCreateIn(BaseModel):
    course_id: uuid.UUID


class EnrollmentOut(ORMModel):
    id: uuid.UUID
    course_id: uuid.UUID
    order_id: uuid.UUID
    status: str
    created_at: datetime


class OrderOut(ORMModel):
    id: uuid.UUID
    total_amount: Decimal
    status: str


class InvoiceOut(ORMModel):
    id: uuid.UUID
    invoice_number: str
    amount: Decimal
    status: str


class EnrollmentCreatedOut(BaseModel):
    enrollment: EnrollmentOut
    order: OrderOut
    invoice: InvoiceOut


class MyCourseOut(BaseModel):
    enrollment_id: uuid.UUID
    course_id: uuid.UUID
    title: str
    status: str
    completed_modules: int
    total_modules: int
    progress_percentage: float


class ProgressIn(BaseModel):
    module_id: uuid.UUID
    status: Literal["in_progress", "completed"]


class ProgressOut(BaseModel):
    enrollment_id: uuid.UUID
    enrollment_status: str
    completed_modules: int
    total_modules: int
    progress_percentage: float


# ---------- Payments ----------
class PaymentCreateIn(BaseModel):
    invoice_id: uuid.UUID
    method: Literal["bank_transfer", "ewallet", "qris"]


class PaymentOut(ORMModel):
    id: uuid.UUID
    invoice_id: uuid.UUID
    method: str
    external_ref: str
    amount: Decimal
    status: str


class PaymentCallbackIn(BaseModel):
    external_ref: str
    status: Literal["paid", "failed"]
    amount: Decimal
