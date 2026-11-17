"""Check DNS, TCP, and HTTP for a single service URL."""

import argparse
import http.client
import socket
from urllib.parse import urlsplit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="A complete URL, such as http://localhost:8000/")
    args = parser.parse_args()

    try:
        url = urlsplit(args.url)
        if url.scheme not in ("http", "https") or not url.hostname or url.username is not None:
            raise ValueError("Enter an HTTP or HTTPS URL without credentials.")
        port = url.port
        if port is None:
            port = 443 if url.scheme == "https" else 80
        if port == 0:
            raise ValueError("Port must be between 1 and 65535.")
    except ValueError as error:
        parser.error(str(error))

    host = url.hostname
    try:
        records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as error:
        print(f"DNS failed for {host}: {error}")
        return 1
    addresses = dict.fromkeys(record[4][0] for record in records)
    print(f"DNS OK: {host} -> {', '.join(addresses)}")

    try:
        with socket.create_connection((host, port), timeout=3) as connection:
            print(f"TCP OK: connected to {connection.getpeername()[0]} on port {port}")
    except OSError as error:
        print(f"TCP failed on port {port}: {error}")
        return 1

    connection_class = (
        http.client.HTTPSConnection if url.scheme == "https" else http.client.HTTPConnection
    )
    path = url.path or "/"
    if url.query:
        path += "?" + url.query
    connection = connection_class(host, port, timeout=3)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        print(f"HTTP response: {response.status} {response.reason}")
        return 0 if 200 <= response.status < 400 else 1
    except (OSError, http.client.HTTPException, ValueError) as error:
        print(f"HTTP request failed: {error}")
        return 1
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
