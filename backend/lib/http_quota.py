"""Quota classification shared by HTTP provider adapters."""

import httpx


def parse_retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def classify_quota(response: httpx.Response) -> tuple[bool, float | None]:
    header_delay = parse_retry_after(response.headers.get("Retry-After"))
    retry_after = header_delay
    daily = header_delay is not None and header_delay > 300

    try:
        body = response.json()
    except ValueError:
        return daily, retry_after
    if isinstance(body, list):
        body = body[0] if len(body) == 1 else None
    if not isinstance(body, dict):
        return daily, retry_after
    error = body.get("error")
    if isinstance(error, list):
        error = error[0] if len(error) == 1 else None
    if not isinstance(error, dict):
        return daily, retry_after

    code = str(error.get("code", "")).lower()
    error_type = str(error.get("type", "")).lower()
    if code in {"insufficient_quota", "quota_exceeded"}:
        daily = True
    if error_type in {"insufficient_quota", "quota_exceeded"}:
        daily = True
    message = str(error.get("message", "")).lower()
    if any(token in message for token in ("per day", "daily", "requests per day")):
        daily = True

    details = error.get("details")
    if not isinstance(details, list):
        if retry_after is not None and retry_after > 300:
            daily = True
        return daily, retry_after

    for detail in details:
        if not isinstance(detail, dict):
            continue
        detail_type = str(detail.get("@type", ""))
        if detail_type.endswith("RetryInfo"):
            parsed = _parse_duration(detail.get("retryDelay"))
            if parsed is not None:
                retry_after = parsed
        if not detail_type.endswith("QuotaFailure"):
            continue
        violations = detail.get("violations")
        if not isinstance(violations, list):
            continue
        for violation in violations:
            if not isinstance(violation, dict):
                continue
            quota_text = " ".join(
                str(violation.get(key, "")) for key in ("quotaId", "quotaMetric")
            ).lower()
            if (
                "perday" in quota_text
                or "per day" in quota_text
                or "daily" in quota_text
            ):
                daily = True

    if retry_after is not None and retry_after > 300:
        daily = True
    return daily, retry_after


def _parse_duration(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return max(0.0, float(value))
    if isinstance(value, str) and value.endswith("s"):
        try:
            return max(0.0, float(value[:-1]))
        except ValueError:
            return None
    return None
