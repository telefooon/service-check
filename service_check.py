"""Check HTTP service availability and diagnose failures by network stage."""

import argparse
import csv
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
import http.client
import json
from pathlib import Path
import socket
import ssl
import time
from urllib.parse import urlsplit


@dataclass
class Service:
    name: str
    url: str
    timeout: float = 3
    expect: int | None = None

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Each service needs a name.")
        if not isinstance(self.url, str) or any(ord(c) <= 32 or ord(c) == 127 for c in self.url):
            raise ValueError("URLs must be strings without spaces or control characters.")
        target = urlsplit(self.url)
        if target.scheme not in ("http", "https") or not target.hostname or target.username is not None:
            raise ValueError("Use an HTTP or HTTPS URL without credentials.")
        if target.port == 0:
            raise ValueError("Port must be between 1 and 65535.")
        if type(self.timeout) not in (int, float) or not 0 < self.timeout <= 86400:
            raise ValueError("Timeout must be in (0, 86400] seconds.")
        if self.expect is not None and (type(self.expect) is not int or not 100 <= self.expect <= 599):
            raise ValueError("Expected HTTP status must be between 100 and 599.")


def connect(records, timeout):
    """Connect to the first reachable address within the TCP time budget."""
    deadline = time.monotonic() + timeout
    last_error = OSError("No addresses available")
    for family, kind, protocol, _, address in records:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("TCP connection timed out")
        sock = socket.socket(family, kind, protocol)
        try:
            sock.settimeout(remaining)
            sock.connect(address)
            sock.settimeout(timeout)
            return sock
        except OSError as error:
            sock.close()
            last_error = error
    raise last_error


def probe(service):
    """Check each network stage on the same connection."""
    url = urlsplit(service.url)
    secure = url.scheme == "https"
    port = url.port or (443 if secure else 80)
    host = url.hostname
    stages = {name: ("SKIP", None, "") for name in ("DNS", "TCP", "TLS", "HTTP")}
    stage = "DNS"
    start = time.perf_counter()
    status = None
    sock = None
    try:
        host = host.encode("idna").decode("ascii")
        records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        addresses = dict.fromkeys(record[4][0] for record in records)
        stages[stage] = ("PASS", elapsed(start), ", ".join(addresses))

        stage, start = "TCP", time.perf_counter()
        sock = connect(records, service.timeout)
        stages[stage] = ("PASS", elapsed(start), f"{sock.getpeername()[0]} port {port}")

        if secure:
            stage, start = "TLS", time.perf_counter()
            context = ssl.create_default_context()
            sock = context.wrap_socket(sock, server_hostname=host)
            expiry = ssl.cert_time_to_seconds(sock.getpeercert()["notAfter"])
            date = datetime.fromtimestamp(expiry, timezone.utc).date()
            days = int((expiry - time.time()) // 86400)
            stages[stage] = ("PASS", elapsed(start), f"{sock.version()}, expires {date} UTC ({days}d remaining)")
        else:
            stages["TLS"] = ("SKIP", None, "plain HTTP")

        stage, start = "HTTP", time.perf_counter()
        with closing(http.client.HTTPConnection(host, port, timeout=service.timeout)) as client:
            client.sock = sock
            path = url.path or "/"
            if url.query:
                path += "?" + url.query
            authority = url.netloc if url.netloc.isascii() else host
            if not url.netloc.isascii() and url.port is not None:
                authority += f":{port}"
            client.request("GET", path, headers={"Host": authority})
            with client.getresponse() as response:
                status = response.status
            good = status == service.expect if service.expect is not None else 200 <= status < 400
            expected = service.expect if service.expect is not None else "200-399"
            stages[stage] = ("PASS" if good else "FAIL", elapsed(start), f"{status} (expected {expected})")
    except (OSError, ValueError, http.client.HTTPException) as error:
        stages[stage] = ("FAIL", elapsed(start), str(error))
    finally:
        if sock is not None:
            sock.close()
    return stages, status


def elapsed(start):
    """Return elapsed milliseconds."""
    return round((time.perf_counter() - start) * 1000, 2)


def report(service, outages, writer):
    """Print the check and record observed downtime."""
    stages, status = probe(service)
    failed = next((name for name, value in stages.items() if value[0] == "FAIL"), "")
    state = "DOWN" if failed else "UP"
    now = time.monotonic()
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    previous = outages.get(service.name)
    event = ""
    if failed and previous is None:
        if service.name in outages:
            event = "UP -> DOWN"
        outages[service.name] = now
    elif not failed:
        if previous is not None:
            event = f"DOWN -> UP after {now - previous:.1f}s observed down"
        outages[service.name] = None
    print(f"\n{stamp}  {service.name}  {state}  {event}".rstrip())
    for name, (result, ms, detail) in stages.items():
        timing = "" if ms is None else f"  {ms:.2f} ms"
        print(f"  {name:4} {result:4}  {detail}{timing}".rstrip())
    if writer:
        writer.writerow([stamp, service.name, state, failed, status, event,
                         *(value[1] for value in stages.values())])
    return not failed


def load_services(args):
    """Load a URL or a JSON list of named services."""
    if args.config is None:
        return [Service(args.url, args.url, args.timeout, args.expect)]
    data = json.loads(args.config.read_text(encoding="utf-8-sig"))
    if not isinstance(data, list) or not data:
        raise ValueError("Config must contain a nonempty list of services.")
    services = []
    names = set()
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("Each config entry must be an object.")
        service = Service(**({"timeout": args.timeout, "expect": args.expect} | item))
        if service.name in names:
            raise ValueError(f"Duplicate service name: {service.name}")
        names.add(service.name)
        services.append(service)
    return services


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("url", nargs="?")
    target.add_argument("--config", type=Path)
    parser.add_argument("--expect", type=int, help="Expected HTTP status (default: 200-399)")
    parser.add_argument("--timeout", type=float, default=3, help="Socket timeout in seconds")
    parser.add_argument("--watch", type=float, help="Seconds between rounds")
    parser.add_argument("--csv", type=Path, help="Append check results to this file")
    args = parser.parse_args()
    try:
        services = load_services(args)
        if args.watch is not None and not 0 < args.watch <= 86400:
            raise ValueError("Watch interval must be in (0, 86400] seconds.")
    except (ValueError, TypeError, OSError) as error:
        parser.error(str(error))

    log = None
    try:
        writer = None
        if args.csv:
            log = args.csv.open("a", newline="", encoding="utf-8")
            writer = csv.writer(log)
            if log.tell() == 0:
                writer.writerow(["timestamp_utc", "service", "state", "failed_stage", "http_status",
                                 "event", "dns_ms", "tcp_ms", "tls_ms", "http_ms"])
        outages = {}
        while True:
            results = [report(service, outages, writer) for service in services]
            if log:
                log.flush()
            if args.watch is None:
                return 0 if all(results) else 1
            time.sleep(args.watch)
    except KeyboardInterrupt:
        return 130
    except OSError as error:
        parser.exit(2, f"Monitor error: {error}\n")
    finally:
        if log:
            log.close()


if __name__ == "__main__":
    raise SystemExit(main())
