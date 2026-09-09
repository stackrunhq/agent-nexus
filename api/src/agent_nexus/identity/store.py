import hashlib
import secrets
import time
from uuid import uuid4

from agent_nexus.core.errors import GatewayError
from agent_nexus.storage.database import run

SESSION_SECONDS = 3600


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    value = hashlib.scrypt(
        password.encode(),
        salt=bytes.fromhex(salt),
        n=2**17,
        r=8,
        p=1,
        maxmem=256 * 1024 * 1024,
        dklen=32,
    ).hex()
    return f"scrypt${salt}${value}"


def verify_password(password, encoded):
    _, salt, _ = encoded.split("$")
    return secrets.compare_digest(password_hash(password, salt), encoded)


def fingerprint(token):
    return hashlib.sha256(token.encode()).hexdigest()


class IdentityStore:
    def __init__(self, database):
        self.database = database

    @staticmethod
    def record(db, user_id, actor, action):
        run(
            db,
            "INSERT INTO user_events(user_id, actor, action, created_at) "
            "VALUES (:id, :actor, :action, :now)",
            id=user_id,
            actor=actor,
            action=action,
            now=int(time.time()),
        )

    def create(self, body, actor):
        # A shared identity lock bounds expensive hashing and serializes lifecycle changes.
        with self.database.write("identity") as db:
            if run(db, "SELECT id FROM users WHERE username=:name", name=body.username).first():
                raise GatewayError(409, "username_exists", "Username already exists")
            if (
                body.tenant_id
                and not run(
                    db, "SELECT id FROM tenants WHERE id=:id AND enabled=1", id=body.tenant_id
                ).first()
            ):
                raise GatewayError(422, "invalid_tenant", "Choose an enabled tenant")
            user_id = str(uuid4())
            run(
                db,
                "INSERT INTO users(id, username, password_hash, role, tenant_id) "
                "VALUES (:id, :name, :password, :role, :tenant)",
                id=user_id,
                name=body.username,
                password=password_hash(body.password),
                role=body.role,
                tenant=body.tenant_id,
            )
            self.record(db, user_id, actor, "created")
        return {
            "id": user_id,
            "username": body.username,
            "role": body.role,
            "tenant_id": body.tenant_id,
            "enabled": True,
        }

    def list(self):
        with self.database.read() as db:
            return [
                {**row, "enabled": bool(row["enabled"])}
                for row in run(
                    db, "SELECT id, username, role, tenant_id, enabled FROM users ORDER BY username"
                ).mappings()
            ]

    def login(self, username, password):
        result = None
        now = int(time.time())
        with self.database.write("identity") as db:
            user = (
                run(db, "SELECT * FROM users WHERE username=:name", name=username)
                .mappings()
                .first()
            )
            if user and user["blocked_until"] > now:
                # Keep password work comparable to unknown-user and wrong-password attempts.
                verify_password(password, "scrypt$" + "0" * 32 + "$" + "0" * 64)
            else:
                encoded = user["password_hash"] if user else "scrypt$" + "0" * 32 + "$" + "0" * 64
                valid = verify_password(password, encoded)
                tenant_ok = (
                    not user
                    or not user["tenant_id"]
                    or run(
                        db,
                        "SELECT id FROM tenants WHERE id=:id AND enabled=1",
                        id=user["tenant_id"],
                    ).first()
                )
                if user and valid and user["enabled"] and tenant_ok:
                    run(
                        db,
                        "UPDATE users SET failed_attempts=0, blocked_until=0 WHERE id=:id",
                        id=user["id"],
                    )
                    # One active session per account; successful re-login revokes the old session.
                    run(
                        db,
                        "DELETE FROM user_sessions WHERE user_id=:id OR expires_at<=:now",
                        id=user["id"],
                        now=now,
                    )
                    token = "ns_" + secrets.token_urlsafe(32)
                    run(
                        db,
                        "INSERT INTO user_sessions(key_hash, user_id, expires_at) VALUES (:hash, :id, :expiry)",
                        hash=fingerprint(token),
                        id=user["id"],
                        expiry=now + SESSION_SECONDS,
                    )
                    self.record(db, user["id"], user["id"], "login")
                    result = {
                        "access_token": token,
                        "token_type": "bearer",
                        "expires_in": SESSION_SECONDS,
                        "user": {key: user[key] for key in ("id", "username", "role", "tenant_id")},
                    }
                elif user:
                    failures = user["failed_attempts"] + 1 if user["blocked_until"] == 0 else 1
                    run(
                        db,
                        "UPDATE users SET failed_attempts=:failures, blocked_until=:until WHERE id=:id",
                        id=user["id"],
                        failures=failures,
                        until=now + 300 if failures >= 5 else 0,
                    )
                    self.record(db, user["id"], "anonymous", "login_failed")
        # Raise after commit so failed-login throttling survives the request.
        if result is None:
            raise GatewayError(
                401, "invalid_login", "Invalid credentials or login temporarily unavailable"
            )
        return result

    def authenticate(self, token):
        with self.database.read() as db:
            row = (
                run(
                    db,
                    "SELECT u.id, u.username, u.role, u.tenant_id FROM user_sessions s "
                    "JOIN users u ON u.id=s.user_id LEFT JOIN tenants t ON t.id=u.tenant_id "
                    "WHERE s.key_hash=:hash AND s.expires_at>:now AND u.enabled=1 "
                    "AND (u.tenant_id IS NULL OR t.enabled=1)",
                    hash=fingerprint(token),
                    now=int(time.time()),
                )
                .mappings()
                .first()
            )
            return dict(row) if row else None

    def logout(self, token, user_id):
        with self.database.write("identity") as db:
            run(db, "DELETE FROM user_sessions WHERE key_hash=:hash", hash=fingerprint(token))
            self.record(db, user_id, user_id, "logout")

    def update(self, user_id, actor, *, enabled=None, password=None):
        with self.database.write("identity") as db:
            if not run(db, "SELECT id FROM users WHERE id=:id", id=user_id).first():
                raise GatewayError(404, "user_not_found", "User does not exist")
            if password is not None:
                run(
                    db,
                    "UPDATE users SET password_hash=:password, failed_attempts=0, blocked_until=0 WHERE id=:id",
                    password=password_hash(password),
                    id=user_id,
                )
            else:
                run(
                    db,
                    "UPDATE users SET enabled=:enabled WHERE id=:id",
                    enabled=int(enabled),
                    id=user_id,
                )
            run(db, "DELETE FROM user_sessions WHERE user_id=:id", id=user_id)
            self.record(
                db,
                user_id,
                actor,
                "password_reset" if password is not None else "enabled" if enabled else "disabled",
            )

    def events(self):
        with self.database.read() as db:
            return [
                dict(row)
                for row in run(
                    db, "SELECT * FROM user_events ORDER BY id DESC LIMIT 100"
                ).mappings()
            ]
