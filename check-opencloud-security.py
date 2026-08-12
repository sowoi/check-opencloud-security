import ipaddress
import json
import re
import socket
from urllib.parse import urlparse
import httpx

# Liste der zu prüfenden Sicherheits-Header
SECURITY_HEADERS = [
    "Strict-Transport-Security",
    "Content-Security-Policy",
    "X-Frame-Options",
    "X-Content-Type-Options",
    "Referrer-Policy",
]


def validate_target(url: str) -> tuple[bool, str]:
    """Schützt vor SSRF: Prüft, ob die Ziel-IP im öffentlichen Netz liegt."""
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        return False, "Ungültige URL"

    try:
        ip_addr = socket.gethostbyname(hostname)
        ip = ipaddress.ip_address(ip_addr)
        if ip.is_private or ip.is_loopback or ip.is_reserved:
            return False, f"Zugriff verweigert: IP {ip} ist privat/intern."
        return True, "OK"
    except socket.gaierror:
        return False, "Domain konnte nicht aufgelöst werden."


def scan_version(client: httpx.Client, base_url: str) -> dict:
    """Sucht nach Versionsinformationen an typischen Endpunkten."""
    status_url = f"{base_url.rstrip('/')}/status.php"
    result = {
        "endpoint": status_url,
        "product": None,
        "productversion": None,
        "versionstring": None,
        "installed": None,
        "maintenance": None
    }

    try:
        response = client.get(status_url, timeout=5.0)
        if response.status_code == 200:
            try:
                data = response.json()

                # Primär productversion nutzen, sonst Fallbacks
                result["productversion"] = (
                        data.get("productversion")
                        or data.get("versionstring")
                        or data.get("version")
                )

                # Metadaten mit erfassen
                result["product"] = data.get("productname") or data.get("product")
                result["versionstring"] = data.get("versionstring")
                result["installed"] = data.get("installed", True)
                result["maintenance"] = data.get("maintenance", False)

            except json.JSONDecodeError:
                # Fallback bei Plaintext-Antwort
                match = re.search(r"\d+\.\d+\.\d+", response.text)
                if match:
                    result["productversion"] = match.group(0)

    except httpx.RequestError as e:
        result["error"] = str(e)

    return result

def scan_headers(client: httpx.Client, base_url: str) -> dict:
    """Überprüft das Vorhandensein essenzieller Security-Header."""
    header_results = {}
    try:
        response = client.get(base_url, timeout=5.0)
        headers = response.headers

        for header in SECURITY_HEADERS:
            present = header in headers
            header_results[header] = {
                "present": present,
                "value": headers.get(header) if present else None,
            }
    except httpx.RequestError as e:
        header_results["error"] = str(e)

    return header_results


def run_security_scan(target_url: str) -> dict:
    """Hauptfunktion für den Scan-Ablauf."""
    # Ensure scheme
    if not target_url.startswith(("http://", "https://")):
        target_url = "https://" + target_url

    # SSRF Validation
    is_valid, msg = validate_target(target_url)
    if not is_valid:
        return {"status": "error", "message": msg}

    # Execute Scan
    with httpx.Client(follow_redirects=True, headers={"User-Agent": "OpenCloud-SecurityScanner/1.0"}) as client:
        version_data = scan_version(client, target_url)
        header_data = scan_headers(client, target_url)

    return {
        "status": "success",
        "target": target_url,
        "version_check": version_data,
        "header_check": header_data,
    }


if __name__ == "__main__":
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "https://cloud.example.com"
    report = run_security_scan(target)
    print(json.dumps(report, indent=2))