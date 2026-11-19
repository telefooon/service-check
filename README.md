# Service Check

Service Check is a Python CLI for finding where a web request fails. It resolves the hostname, connects to the port, validates TLS for HTTPS, and checks the HTTP response status. Run it once or watch several services and log outages to CSV.

Requires Python 3.10 or later. Uses only the standard library.

## Run the local demo

Extract the project and open three terminals in the folder containing `service_check.py`. On Windows you can use `py` in place of `python`.

In terminal 1, start the frontend.

```sh
python -m http.server 8000 --bind 127.0.0.1 --directory demo/frontend
```

In terminal 2, start the mock backend. It serves a small file at `/health`.

```sh
python -m http.server 8001 --bind 127.0.0.1 --directory demo/backend
```

In terminal 3, start the monitor.

```sh
python service_check.py --config services.example.json --watch 5 --csv history.csv
```

Both services should show UP. Press Ctrl+C in terminal 2. On the next check the backend should show DOWN with a TCP failure while the frontend stays UP. Restart terminal 2's command to see recovery and the time between the first failed check and the first successful one. Ctrl+C in terminal 3 stops monitoring.

## Check one URL

```sh
python service_check.py http://localhost:8000/
python service_check.py http://localhost:8001/missing --expect 200
python service_check.py https://example.com/ --timeout 5
```

With the demo running, the second command reaches the backend and receives a 404. Its failed stage is HTTP. The third command exercises TLS and requires internet access. To demonstrate a TLS handshake failure locally, run `python service_check.py https://localhost:8000/` against the plain HTTP frontend. For a certificate failure, use an HTTPS service with an expired or untrusted certificate. TCP can pass while TLS reports the verification error and HTTP is skipped.

| Stage | What the result measures |
|---|---|
| DNS | Operating system name resolution, including cached or local names such as localhost |
| TCP | Time to connect to a resolved address on the requested port |
| TLS | HTTPS handshake and certificate validation against the hostname and trusted authorities. A pass shows TLS version, UTC expiry date, and whole days left |
| HTTP | Time to send GET and receive response headers over the established connection. The checker reports redirects directly |

## CLI options

| Option | Behavior |
|---|---|
| `URL` or `--config FILE` | Check one URL or a JSON array of services. Each entry needs a unique name and URL. See `services.example.json` |
| `--expect CODE` | Require a specific response code. Default accepts 200 through 399 |
| `--timeout SECONDS` | TCP connect budget and socket operation timeout, default 3 seconds. DNS timing follows the system resolver |
| `--watch SECONDS` | Check services in order, then wait this many seconds before starting the next round |
| `--csv FILE` | Append one row per service check, including UTC time, state, failed stage, HTTP status, state changes, and stage timings |

Config entries can override the CLI defaults with `expect` and `timeout`. An initial check establishes the observed state. Subsequent changes print `UP -> DOWN` or `DOWN -> UP`. Outage timing starts at the first failed observation in the current run. Short outages between checks can go undetected.

One-time checks exit with 0 when all services pass or 1 when any service fails. Invalid arguments or configuration exit with 2. Interrupting watch mode exits with 130.
