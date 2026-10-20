"""Domain errors and the API error codes (plan Section 0: error envelope).

The HTTP status is derived from the code, so a rule can only raise a code the API documents.
`HTTP_ERROR` has no fixed status: the API uses it only for framework HTTP errors without a code of
their own, so it is not in `STATUS_BY_CODE` and a `DomainError` cannot carry it.
"""

HTTP_ERROR = "HTTP_ERROR"

STATUS_BY_CODE: dict[str, int] = {
    "IDENTITY_UNCONFIRMED": 409,
    "EVIDENCE_INCOMPLETE": 409,
    "APPROVAL_REQUIRED": 409,
    "APPROVAL_STALE": 409,
    "ACTION_EXPIRED": 409,
    "INSUFFICIENT_SANDBOX_FUNDS": 409,
    "DUPLICATE_EXECUTION": 409,
    "INVALID_STATE": 409,
    "FORBIDDEN_ROLE": 403,
    "UNAUTHENTICATED": 401,
    "NOT_FOUND": 404,
    "VALIDATION_FAILED": 422,
    "IDEMPOTENCY_KEY_REQUIRED": 400,
    "BAD_REQUEST": 400,
    "METHOD_NOT_ALLOWED": 405,
    "INTERNAL_ERROR": 500,
}

CODE_BY_HTTP_STATUS: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN_ROLE",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    422: "VALIDATION_FAILED",
}


class DomainError(Exception):
    def __init__(self, code: str, message: str, details: dict | None = None) -> None:
        if code not in STATUS_BY_CODE:
            raise ValueError(f"unknown error code {code!r}")
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.details = details or {}
        self.status = STATUS_BY_CODE[code]
