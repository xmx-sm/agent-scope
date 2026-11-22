"""知识库模型。"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.common import new_id, utc_now


class VectorLibrary(Base):
    __tablename__ = "vector_libraries"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_vector_library_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    vector_type: Mapped[str] = mapped_column(String(50), nullable=False, default="sqlite")
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    embedding: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    config: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    origin: Mapped[str] = mapped_column(String(20), nullable=False, default="platform")
    auto_parse: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    parse_interval: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    last_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class VectorDocument(Base):
    __tablename__ = "vector_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    library_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("vector_libraries.id", ondelete="CASCADE"), nullable=False,
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    source_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    filesize: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VectorLog(Base):
    __tablename__ = "vector_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    library_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    document_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    operation: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    details: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class VectorChunk(Base):
    __tablename__ = "vector_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("vector_documents.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    library_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class VectorLibraryShare(Base):
    __tablename__ = "vector_library_shares"
    __table_args__ = (
        UniqueConstraint("library_id", "target_user_id", name="uq_vector_share_target"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    library_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("vector_libraries.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    owner_user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    target_user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    permission: Mapped[str] = mapped_column(String(20), nullable=False, default="read")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
