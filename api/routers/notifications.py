from fastapi import APIRouter
from api.notifications import (
    read_notifications, mark_all_read,
    delete_notification, clear_all, unread_count,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
def list_notifications(limit: int = 100, offset: int = 0):
    notifications = read_notifications(limit=limit, offset=offset)
    return {
        "items": notifications,
        "unread": unread_count(),
    }


@router.post("/mark-read")
def mark_read():
    mark_all_read()
    return {"ok": True}


@router.delete("/{nid}")
def delete_one(nid: str):
    ok = delete_notification(nid)
    return {"ok": ok}


@router.delete("")
def clear_notifications():
    clear_all()
    return {"ok": True}
