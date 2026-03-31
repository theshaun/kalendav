from app.config import settings
from app.database import async_session, init_db
from app.models import User, Calendar
from app.auth.basic import hash_password
from sqlalchemy import select


async def create_admin_user():
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.username == settings.admin_user)
        )
        if not result.scalar_one_or_none():
            admin = User(
                username=settings.admin_user,
                email="admin@localhost",
                password_hash=hash_password(settings.admin_password),
                is_admin=True,
            )
            session.add(admin)
            
            default_calendar = Calendar(
                user=admin,
                name="Default",
                is_default=True,
            )
            session.add(default_calendar)
            
            await session.commit()
            print(f"Created admin user: {settings.admin_user}")
