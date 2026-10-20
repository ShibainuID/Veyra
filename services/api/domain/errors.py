"""Domain error codes from PRD Section 6, returned as `{"error": {"code", "message", "details"}}`."""

from enum import StrEnum


class ErrorCode(StrEnum):
    UNAUTHENTICATED = "UNAUTHENTICATED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    CONFLICT = "CONFLICT"
    # Workflow codes named in the PRD.
    IDENTITY_UNCONFIRMED = "IDENTITY_UNCONFIRMED"
    EVIDENCE_INCOMPLETE = "EVIDENCE_INCOMPLETE"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVAL_STALE = "APPROVAL_STALE"
    ACTION_EXPIRED = "ACTION_EXPIRED"
    INSUFFICIENT_SANDBOX_FUNDS = "INSUFFICIENT_SANDBOX_FUNDS"


STATUS = {
    ErrorCode.UNAUTHENTICATED: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.VALIDATION_FAILED: 422,
    ErrorCode.PAYLOAD_TOO_LARGE: 413,
    ErrorCode.CONFLICT: 409,
    ErrorCode.IDENTITY_UNCONFIRMED: 409,
    ErrorCode.EVIDENCE_INCOMPLETE: 422,
    ErrorCode.APPROVAL_REQUIRED: 409,
    ErrorCode.APPROVAL_STALE: 409,
    ErrorCode.ACTION_EXPIRED: 409,
    ErrorCode.INSUFFICIENT_SANDBOX_FUNDS: 409,
}


class APIError(Exception):
    def __init__(self, code: ErrorCode, message: str, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    @property
    def status_code(self) -> int:
        return STATUS[self.code]

    def body(self) -> dict:
        return {"error": {"code": self.code.value, "message": self.message, "details": self.details}}
