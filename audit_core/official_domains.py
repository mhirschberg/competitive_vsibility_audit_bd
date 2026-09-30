"""Resolve a submitted official website before starting paid audit work.

Only public DNS names are accepted. Connections are pinned to DNS-validated
public IP addresses so a redirect cannot reach a private service or metadata
endpoint. A verified redirect is enough to identify the destination even if
the destination later blocks automated HEAD requests.
"""

import http.client
import ipaddress
import re
import socket
import ssl
from urllib.parse import urljoin, urlsplit, urlunsplit


class OfficialDomainResolutionError(ValueError):
    pass


_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".test", ".invalid", ".example")


def _normalized_public_url(value, *, submitted=False):
    raw = str(value or "").strip()
    if submitted and "://" not in raw:
        raw = "https://" + raw
    try:
        parsed = urlsplit(raw)
        hostname = (parsed.hostname or "").encode("idna").decode("ascii").lower()
        port = parsed.port
    except (UnicodeError, ValueError) as exc:
        raise OfficialDomainResolutionError("Invalid official website address") from exc
    if parsed.scheme not in {"http", "https"} or not hostname:
        raise OfficialDomainResolutionError("Official website must be an HTTP(S) address")
    if parsed.scheme == "http":
        if not submitted:
            raise OfficialDomainResolutionError("Official website redirected to insecure HTTP")
        parsed = parsed._replace(scheme="https")
    if parsed.username or parsed.password or port not in {None, 443}:
        raise OfficialDomainResolutionError("Official website cannot contain credentials or a custom port")
    if (
        "." not in hostname
        or hostname.endswith(_BLOCKED_SUFFIXES)
        or not re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+", hostname)
        or any(part.startswith("-") or part.endswith("-") for part in hostname.split("."))
    ):
        raise OfficialDomainResolutionError("Official website must use a public DNS name")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise OfficialDomainResolutionError("IP addresses are not accepted as official websites")
    path = parsed.path or "/"
    if len(path) > 2048 or len(parsed.query) > 2048:
        raise OfficialDomainResolutionError("Official website URL is too long")
    return urlunsplit(("https", hostname, path, parsed.query, ""))


def _public_ip_for(hostname):
    try:
        records = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise OfficialDomainResolutionError(f"Could not resolve official website {hostname}") from exc
    addresses = {record[4][0] for record in records}
    if not addresses:
        raise OfficialDomainResolutionError(f"No IP address for official website {hostname}")
    if any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise OfficialDomainResolutionError("Official website resolves to a non-public address")
    return sorted(addresses)[0]


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, hostname, address, timeout):
        super().__init__(hostname, timeout=timeout, context=ssl.create_default_context())
        self._pinned_address = address

    def connect(self):
        raw_socket = socket.create_connection((self._pinned_address, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw_socket, server_hostname=self.host)
        except Exception:
            raw_socket.close()
            raise


def _request_site_headers(url, *, timeout=6):
    parsed = urlsplit(url)
    address = _public_ip_for(parsed.hostname)
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    connection = _PinnedHTTPSConnection(parsed.hostname, address, timeout)
    try:
        connection.request("HEAD", path, headers={"User-Agent": "Qaviso-Audit/1.0"})
        response = connection.getresponse()
        status, location = response.status, response.getheader("Location")
        if status in {405, 501}:
            connection.close()
            connection = _PinnedHTTPSConnection(parsed.hostname, address, timeout)
            connection.request("GET", path, headers={
                "User-Agent": "Qaviso-Audit/1.0", "Range": "bytes=0-0"
            })
            response = connection.getresponse()
            status, location = response.status, response.getheader("Location")
        return status, location
    except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
        raise OfficialDomainResolutionError(
            f"Could not verify official website {parsed.hostname}: {type(exc).__name__}"
        ) from exc
    finally:
        connection.close()


def resolve_official_site(value, *, request_headers=None, max_redirects=5):
    """Return the verified final HTTPS host or raise before paid work begins."""
    request_headers = request_headers or _request_site_headers
    submitted_url = _normalized_public_url(value, submitted=True)
    current_url = submitted_url
    visited = set()
    chain = []
    for _ in range(max_redirects + 1):
        if current_url in visited:
            raise OfficialDomainResolutionError("Official website has a redirect loop")
        visited.add(current_url)
        status, location = request_headers(current_url)
        if status in _REDIRECT_STATUSES:
            if not location:
                raise OfficialDomainResolutionError("Official website redirect has no destination")
            if len(chain) >= max_redirects:
                raise OfficialDomainResolutionError("Official website has too many redirects")
            next_url = _normalized_public_url(urljoin(current_url, location))
            chain.append({"from": current_url, "to": next_url, "status": status})
            current_url = next_url
            continue
        if 200 <= status < 300 or (chain and status in {401, 403}):
            hostname = urlsplit(current_url).hostname
            return {
                "submitted_url": submitted_url,
                "canonical_url": f"https://{hostname}/",
                "submitted_hostname": urlsplit(submitted_url).hostname,
                "canonical_hostname": hostname,
                "redirect_chain": chain,
                "final_http_status": status,
                "verification": "verified_redirect" if chain else "verified_response",
            }
        raise OfficialDomainResolutionError(
            f"Official website could not be verified (HTTP {status})"
        )
    raise OfficialDomainResolutionError("Official website has too many redirects")
