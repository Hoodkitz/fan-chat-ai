"""Permissions."""
from enum import Enum
from typing import Set


class Permission(str, Enum):
    READ_FAN = "read:fan"
    CREATE_FAN = "create:fan"
    UPDATE_FAN = "update:fan"
    DELETE_FAN = "delete:fan"
    READ_CHAT = "read:chat"
    SEND_REPLY = "send:reply"
    AUTO_RESPOND = "auto:respond"
    READ_HISTORY = "read:history"
    READ_PRESONAE = "read:persona"
    UPDATE_PRESONAE = "update:persona"
    READ_STATS = "read:stats"
    EXPORT = "export"


class Role(str, Enum):
    MODEL = "model"
    ADMIN = "admin"
    AGENT = "agent"
    AUDIT = "audit"


PERMISSIONS: dict[Role, set[str]] = {
    Role.MODEL: {
        Permission.READ_FAN, Permission.CREATE_FAN, Permission.UPDATE_FAN,
        Permission.READ_CHAT, Permission.SEND_REPLY, Permission.READ_HISTORY,
        Permission.READ_PRESONAE, Permission.READ_STATS, Permission.EXPORT,
    },
    Role.ADMIN: {
        Permission.READ_FAN, Permission.CREATE_FAN, Permission.UPDATE_FAN, Permission.DELETE_FAN,
        Permission.READ_CHAT, Permission.SEND_REPLY, Permission.AUTO_RESPOND,
        Permission.READ_HISTORY, Permission.READ_PRESONAE, Permission.UPDATE_PRESONAE,
        Permission.READ_STATS, Permission.EXPORT,
    },
    Role.AGENT: {
        Permission.READ_FAN, Permission.READ_CHAT, Permission.SEND_REPLY,
        Permission.AUTO_RESPOND, Permission.READ_HISTORY, Permission.READ_STATS,
    },
    Role.AUDIT: {
        Permission.READ_FAN, Permission.READ_CHAT, Permission.READ_HISTORY,
        Permission.READ_STATS, Permission.EXPORT,
    },
}
