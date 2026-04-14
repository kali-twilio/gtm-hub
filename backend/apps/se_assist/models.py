from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class User(Base):
    __tablename__ = "se_assist_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_login: Mapped[datetime | None] = mapped_column(DateTime)

    emails: Mapped[list[GongEmail]] = relationship(back_populates="user")
    transcripts: Mapped[list[Transcript]] = relationship(back_populates="user")
    syncs: Mapped[list[SFDCSync]] = relationship(back_populates="user")


class GongEmail(Base):
    __tablename__ = "se_assist_gong_emails"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("se_assist_users.id"), nullable=False)
    gmail_message_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(255))
    call_date: Mapped[datetime | None] = mapped_column(DateTime)
    duration: Mapped[str | None] = mapped_column(String(50))
    parsed_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    received_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped[User] = relationship(back_populates="emails")
    analysis: Mapped[AIAnalysis | None] = relationship(back_populates="gong_email", uselist=False, cascade="all, delete-orphan")
    syncs: Mapped[list[SFDCSync]] = relationship(back_populates="gong_email", cascade="all, delete-orphan")


class AIAnalysis(Base):
    __tablename__ = "se_assist_ai_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    gong_email_id: Mapped[int] = mapped_column(Integer, ForeignKey("se_assist_gong_emails.id"), nullable=False)
    raw_response: Mapped[dict] = mapped_column(JSON, nullable=False)
    use_case_category: Mapped[str | None] = mapped_column(String(100))
    presales_stage: Mapped[str | None] = mapped_column(String(100))
    sfdc_use_case_description: Mapped[str | None] = mapped_column(Text)
    sfdc_solutions_notes: Mapped[str | None] = mapped_column(Text)
    sfdc_technical_risks: Mapped[str | None] = mapped_column(Text)
    model_used: Mapped[str | None] = mapped_column(String(100))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    gong_email: Mapped[GongEmail] = relationship(back_populates="analysis")
    syncs: Mapped[list[SFDCSync]] = relationship(back_populates="ai_analysis")


class Transcript(Base):
    __tablename__ = "se_assist_transcripts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("se_assist_users.id"), nullable=False)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    call_date: Mapped[datetime | None] = mapped_column(DateTime)
    duration: Mapped[str | None] = mapped_column(String(50))
    transcript_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="uploaded")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped[User] = relationship(back_populates="transcripts")
    analysis: Mapped[TranscriptAnalysis | None] = relationship(back_populates="transcript", uselist=False, cascade="all, delete-orphan")


class TranscriptAnalysis(Base):
    __tablename__ = "se_assist_transcript_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    transcript_id: Mapped[int] = mapped_column(Integer, ForeignKey("se_assist_transcripts.id"), nullable=False)
    raw_response: Mapped[dict] = mapped_column(JSON, nullable=False)
    use_case_category: Mapped[str | None] = mapped_column(String(100))
    presales_stage: Mapped[str | None] = mapped_column(String(100))
    sfdc_use_case_description: Mapped[str | None] = mapped_column(Text)
    sfdc_solutions_notes: Mapped[str | None] = mapped_column(Text)
    sfdc_technical_risks: Mapped[str | None] = mapped_column(Text)
    model_used: Mapped[str | None] = mapped_column(String(100))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    transcript: Mapped[Transcript] = relationship(back_populates="analysis")


class SFDCSync(Base):
    __tablename__ = "se_assist_sfdc_syncs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("se_assist_users.id"), nullable=False)
    gong_email_id: Mapped[int] = mapped_column(Integer, ForeignKey("se_assist_gong_emails.id"), nullable=False)
    ai_analysis_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("se_assist_ai_analyses.id"))
    sfdc_opportunity_id: Mapped[str] = mapped_column(String(255), nullable=False)
    sfdc_opportunity_name: Mapped[str | None] = mapped_column(String(255))
    fields_sent: Mapped[dict] = mapped_column(JSON, nullable=False)
    fields_before: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(50), default="success")
    error_message: Mapped[str | None] = mapped_column(Text)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped[User] = relationship(back_populates="syncs")
    gong_email: Mapped[GongEmail] = relationship(back_populates="syncs")
    ai_analysis: Mapped[AIAnalysis | None] = relationship(back_populates="syncs")
