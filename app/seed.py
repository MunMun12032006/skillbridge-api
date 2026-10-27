from sqlalchemy import select

from app.database import SessionLocal
from app.models import Category, Course, CourseModule, User
from app.security import hash_password


def run():
    db = SessionLocal()
    try:
        if db.scalar(select(User).where(User.email == "admin@skillbridge.id")):
            print("Seed sudah pernah dijalankan.")
            return

        admin = User(full_name="Admin SkillBridge", email="admin@skillbridge.id",
                     password_hash=hash_password("Admin123!"), role="admin")
        instructor = User(full_name="Instruktur Satu", email="instructor@skillbridge.id",
                          password_hash=hash_password("Instruktur123!"), role="instructor")
        category = Category(name="Backend Development")
        db.add_all([admin, instructor, category])
        db.flush()

        course = Course(
            category_id=category.id, instructor_id=instructor.id,
            title="REST API dengan FastAPI",
            description="Dari nol sampai API siap produksi.",
            price=150000,
        )
        db.add(course)
        db.flush()

        titles = ["Pengenalan REST", "Routing dan Validasi", "Database dan ORM", "Autentikasi JWT"]
        db.add_all(
            CourseModule(course_id=course.id, title=t, position=i)
            for i, t in enumerate(titles, start=1)
        )
        db.commit()
        print("Seed berhasil.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
