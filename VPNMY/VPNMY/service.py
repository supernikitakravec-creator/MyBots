from __future__ import annotations

import datetime as dt
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from models import User, Order, Subscription


def days_for_months(months: int) -> int:
    if months == 1:
        return 30
    if months == 3:
        return 90
    if months == 6:
        return 180
    if months == 12:
        return 365
    return months * 30


def get_or_create_user(session: Session, tg_user_id: str) -> User:
    user = session.query(User).filter(User.tg_user_id == tg_user_id).one_or_none()
    if user is None:
        user = User(tg_user_id=tg_user_id)
        session.add(user)
        session.commit()
    return user


def create_order(
    session: Session,
    user: User,
    months: int,
    region: str,
    amount_rub: float,
    yk_payment_id: Optional[str],
) -> Order:
    order = Order(
        user_id=user.id,
        months=months,
        region=region,
        amount_rub=amount_rub,
        status="pending",
        yk_payment_id=yk_payment_id,
    )
    session.add(order)
    session.commit()
    return order


def find_pending_order_by_payment_id(session: Session, payment_id: str) -> Optional[Order]:
    return (
        session.query(Order)
        .filter(Order.yk_payment_id == payment_id, Order.status == "pending")
        .one_or_none()
    )


def mark_order_status(session: Session, order: Order, status: str) -> None:
    order.status = status
    session.commit()


def extend_or_create_subscription(
    session: Session,
    user: User,
    region: str,
    months: int,
    hiddify_username: str,
    subscription_url: str,
    traffic_limit_gb: float = 0.0,
) -> Subscription:
    now = dt.datetime.utcnow()
    sub = (
        session.query(Subscription)
        .filter(Subscription.user_id == user.id, Subscription.region == region, Subscription.active == True)  # noqa: E712
        .order_by(Subscription.id.desc())
        .first()
    )
    add_days = days_for_months(months)
    if sub and sub.expires_at > now:
        sub.expires_at = sub.expires_at + dt.timedelta(days=add_days)
        sub.months += months
        sub.subscription_url = subscription_url
        sub.hiddify_username = hiddify_username
        session.commit()
        return sub

    expires_at = now + dt.timedelta(days=add_days)
    new_sub = Subscription(
        user_id=user.id,
        region=region,
        months=months,
        started_at=now,
        expires_at=expires_at,
        hiddify_username=hiddify_username,
        subscription_url=subscription_url,
        traffic_limit_gb=traffic_limit_gb,
        traffic_used_gb=0.0,
        active=True,
    )
    session.add(new_sub)
    session.commit()
    return new_sub


def get_active_subscription(session: Session, tg_user_id: str) -> Optional[Subscription]:
    user = session.query(User).filter(User.tg_user_id == tg_user_id).one_or_none()
    if not user:
        return None
    now = dt.datetime.utcnow()
    return (
        session.query(Subscription)
        .filter(Subscription.user_id == user.id, Subscription.active == True, Subscription.expires_at > now)  # noqa: E712
        .order_by(Subscription.expires_at.desc())
        .first()
    )

