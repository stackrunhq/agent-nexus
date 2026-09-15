"""Bounded, scope-bound continuation positions; cursors never grant access."""

import base64
import hashlib
import json

from agent_nexus.core.errors import GatewayError


def scope_key(tenant, app, version, model, status, error):
    return hashlib.sha256(
        json.dumps([tenant, app, version, model, status, error]).encode()
    ).hexdigest()


def encode(row, scope):
    return base64.urlsafe_b64encode(
        json.dumps([1, row["created_at"], row["id"], scope]).encode()
    ).decode()


def decode(value, scope):
    try:
        data = json.loads(base64.b64decode(value, altchars=b"-_", validate=True))
        if (
            not isinstance(data, list)
            or len(data) != 4
            or data[0] != 1
            or type(data[1]) is not int
            or not 0 <= data[1] <= 2**63 - 1
            or not isinstance(data[2], str)
            or not 1 <= len(data[2]) <= 200
            or data[3] != scope
        ):
            raise ValueError()
        return data[1], data[2]
    except (ValueError, TypeError, UnicodeError):
        raise GatewayError(
            422, "invalid_index_cursor", "Invalid cursor or changed query scope"
        ) from None
