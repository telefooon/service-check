# Service Check

A small Python command-line tool that checks whether a web service can be reached. It uses the Python 3 standard library and runs on Windows and Linux.

## Run the demo

Open two terminals in the project directory. In the first terminal, start a local HTTP server.

```sh
python -m http.server 8000 --bind 127.0.0.1
```

Run these commands in the second terminal. On Linux, use `python3` if `python` is unavailable.

```sh
python service_check.py http://localhost:8000/
python service_check.py http://localhost:8000/missing
```

The first command should resolve localhost, connect to port 8000, and show HTTP 200. The second should connect successfully and show HTTP 404 because the requested path is missing.

Press Ctrl+C in the first terminal and repeat the first command. Name resolution should still succeed, but the TCP connection should now fail because the server stopped listening.

## What each check tells you

| Check | What it tests |
|---|---|
| DNS | Can the operating system resolve the hostname to an IP address? Local names can also come from the hosts file. |
| TCP | Can this machine establish a connection to the target port? |
| HTTP | Does the service respond to a GET request, and what status does it return? HTTPS requests also verify the server certificate. |

The HTTP request opens its own connection. Exit status 0 means the service returned a 2xx or 3xx response. Redirects are reported as received. Exit status 1 means a check failed or the response fell outside that range.

## Interview practice

- Explain why stopping the server leaves name resolution working.
- Explain why HTTP 404 proves the server responded and where you would look next.
- Explain why a connection timeout gives you several leads, such as routing, firewall rules, or an unavailable host.

Based on the local demo, a resume bullet you can use after you run and understand the checks is:

> Built a Python CLI to diagnose web service reachability with DNS, TCP port, and HTTP status checks. Tested successful responses, missing routes, and stopped services.
