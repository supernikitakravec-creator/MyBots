from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    create_engine,
    ForeignKey,
    Float,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tg_user_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=lambda: dt.datetime.utcnow())

    subscriptions: Mapped[list[Subscription]] = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")
    orders: Mapped[list[Order]] = relationship("Order", back_populates="user", cascade="all, delete-orphan")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    region: Mapped[str] = mapped_column(String(8))  # TR or NL
    months: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime, default=lambda: dt.datetime.utcnow())
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime)
    hiddify_username: Mapped[str] = mapped_column(String(128), index=True)
    subscription_url: Mapped[str] = mapped_column(String(2048))
    traffic_limit_gb: Mapped[float] = mapped_column(Float, default=0.0)  # 0 — без лимита
    traffic_used_gb: Mapped[float] = mapped_column(Float, default=0.0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped[User] = relationship("User", back_populates="subscriptions")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    months: Mapped[int] = mapped_column(Integer)
    region: Mapped[str] = mapped_column(String(8))
    amount_rub: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending/succeeded/canceled/expired
    yk_payment_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=lambda: dt.datetime.utcnow())
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=lambda: dt.datetime.utcnow(), onupdate=lambda: dt.datetime.utcnow())

    user: Mapped[User] = relationship("User", back_populates="orders")


def make_engine(db_url: str):
    return create_engine(db_url, future=True)


def make_session_factory(db_url: str):
    engine = make_engine(db_url)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)

