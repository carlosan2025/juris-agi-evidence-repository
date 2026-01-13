"""Security utilities for the Evidence Repository."""

import ipaddress
import socket
from urllib.parse import urlparse


class SSRFProtectionError(Exception):
    """Raised when URL fails SSRF protection checks."""

    pass


def is_private_ip(ip: str) -> bool:
    """Check if an IP address is private/internal.

    Args:
        ip: IP address string to check.

    Returns:
        True if the IP is private, loopback, or otherwise internal.
    """
    try:
        ip_obj = ipaddress.ip_address(ip)

        # Check for various private/internal ranges
        return (
            ip_obj.is_private
            or ip_obj.is_loopback
            or ip_obj.is_link_local
            or ip_obj.is_reserved
            or ip_obj.is_multicast
            or ip_obj.is_unspecified
            # IPv4 specific checks
            or (isinstance(ip_obj, ipaddress.IPv4Address) and (
                ip_obj in ipaddress.ip_network("169.254.0.0/16")  # Link-local
                or ip_obj in ipaddress.ip_network("127.0.0.0/8")  # Loopback
                or ip_obj in ipaddress.ip_network("0.0.0.0/8")  # Current network
            ))
            # IPv6 specific checks
            or (isinstance(ip_obj, ipaddress.IPv6Address) and (
                ip_obj in ipaddress.ip_network("::1/128")  # Loopback
                or ip_obj in ipaddress.ip_network("fe80::/10")  # Link-local
                or ip_obj in ipaddress.ip_network("fc00::/7")  # Unique local
            ))
        )
    except ValueError:
        # Invalid IP address
        return True


def validate_url_for_ssrf(url: str) -> str:
    """Validate a URL to prevent SSRF attacks.

    Checks that the URL:
    - Uses http or https scheme
    - Does not resolve to a private/internal IP
    - Does not use suspicious hostnames

    Args:
        url: URL to validate.

    Returns:
        The validated URL.

    Raises:
        SSRFProtectionError: If the URL fails validation.
    """
    # Parse URL
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise SSRFProtectionError(f"Invalid URL format: {e}")

    # Check scheme
    if parsed.scheme not in ("http", "https"):
        raise SSRFProtectionError(
            f"Invalid URL scheme: {parsed.scheme}. Only http and https are allowed."
        )

    # Get hostname
    hostname = parsed.hostname
    if not hostname:
        raise SSRFProtectionError("URL must include a hostname")

    # Block suspicious hostnames
    blocked_hostnames = {
        "localhost",
        "127.0.0.1",
        "::1",
        "0.0.0.0",
        "metadata.google.internal",  # GCP metadata
        "169.254.169.254",  # AWS/Azure/GCP metadata
        "metadata.azure.internal",  # Azure metadata
    }

    hostname_lower = hostname.lower()
    if hostname_lower in blocked_hostnames:
        raise SSRFProtectionError(f"Blocked hostname: {hostname}")

    # Check for internal domain patterns
    blocked_patterns = [
        ".internal",
        ".local",
        ".localhost",
        ".corp",
        ".lan",
    ]
    for pattern in blocked_patterns:
        if hostname_lower.endswith(pattern):
            raise SSRFProtectionError(f"Blocked internal domain pattern: {pattern}")

    # Resolve hostname and check IP
    try:
        # Get all IP addresses for the hostname
        addr_infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC)
        ip_addresses = {info[4][0] for info in addr_infos}

        for ip in ip_addresses:
            if is_private_ip(ip):
                raise SSRFProtectionError(
                    f"URL resolves to private/internal IP: {ip}"
                )
    except socket.gaierror as e:
        raise SSRFProtectionError(f"Failed to resolve hostname: {e}")

    return url


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename for safe storage.

    Removes or replaces potentially dangerous characters.

    Args:
        filename: Original filename.

    Returns:
        Sanitized filename safe for filesystem storage.
    """
    # Replace dangerous characters
    dangerous_chars = ["<", ">", ":", '"', "/", "\\", "|", "?", "*", "\x00"]
    safe_name = filename

    for char in dangerous_chars:
        safe_name = safe_name.replace(char, "_")

    # Remove leading/trailing dots and spaces
    safe_name = safe_name.strip(". ")

    # Ensure we have a valid filename
    if not safe_name:
        safe_name = "unnamed_file"

    # Limit length (keep extension)
    max_length = 255
    if len(safe_name) > max_length:
        # Try to preserve extension
        parts = safe_name.rsplit(".", 1)
        if len(parts) == 2:
            name, ext = parts
            max_name_len = max_length - len(ext) - 1
            safe_name = f"{name[:max_name_len]}.{ext}"
        else:
            safe_name = safe_name[:max_length]

    return safe_name
