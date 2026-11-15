from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DemoImportRun(Base):
    __tablename__ = "demo_import_runs"

    import_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
