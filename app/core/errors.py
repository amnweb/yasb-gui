"""
Error handling - converting technical exceptions into friendly messages.

Helps translate network errors, timeouts, SSL problems, etc. into user-friendly
translated messages that actually make sense to regular users.
"""

from core.localization import t


def get_friendly_error_message(e: Exception) -> str:
    """Turn a technical error into something a human can understand."""
    error_str = str(e).lower()

    # Connection/DNS errors
    if "getaddrinfo failed" in error_str or "name or service not known" in error_str:
        return t("error_no_connection")

    # Timeout errors
    if "timed out" in error_str or "timeout" in error_str:
        return t("error_timeout")

    # Connection refused/reset
    if "connection refused" in error_str or "connection reset" in error_str:
        return t("error_connection_failed")

    # SSL/Certificate errors
    if "ssl" in error_str or "certificate" in error_str:
        return t("error_ssl_failed")

    # HTTP errors
    if "http error" in error_str or "404" in error_str:
        return t("error_not_found")

    if "403" in error_str:
        return t("error_access_denied")

    if "500" in error_str or "502" in error_str or "503" in error_str:
        return t("error_server_error")

    # URL errors
    if "urlopen error" in error_str:
        reason = str(e)
        if hasattr(e, "reason"):
            reason = str(e.reason)
        if "no host" in reason.lower() or "nodename" in reason.lower():
            return t("error_no_connection")
        return t("error_network")

    # Generic fallback
    return t("error_download_failed")
