import re
from urllib.parse import urlparse, urlunparse


def validate_and_sanitize_repo_url(url: str, allowed_providers: list[str]) -> tuple[bool, str, str]:
    if not url or not str(url).strip():
        return True, "", ""

    url = str(url).strip()
    if "://" not in url:
        url = "https://" + url

    try:
        parsed = urlparse(url)
        if parsed.scheme not in ["http", "https"]:
            return False, "Only HTTP/HTTPS URLs supported", ""
        if not parsed.netloc:
            return False, "Invalid URL format", ""

        path = parsed.path
        tree_match = re.match(r"^(/[^/]+/[^/]+)/tree/.+$", path)
        if tree_match:
            path = tree_match.group(1)
        if path.endswith(".git"):
            path = path[:-4]

        sanitized = urlunparse((parsed.scheme, parsed.netloc.lower(), path, "", "", ""))
        hostname = parsed.netloc.lower()
        if not any(hostname == provider or hostname.endswith("." + provider) for provider in allowed_providers):
            return False, f"Repository host '{hostname}' not authorized", ""
    except Exception as e:
        return False, f"URL parsing error: {e}", ""

    dangerous_patterns = [";", "||", "&&", "$(", "`", "\n", "\r"]
    if any(pat in sanitized for pat in dangerous_patterns):
        return False, "URL contains suspicious characters", ""

    return True, "", sanitized
