from __future__ import annotations

import argparse
import json
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class FlashResult:
    label: str
    ok: bool
    status: int | None
    elapsed_s: float
    json: dict[str, Any] | None
    error: str | None
    request_id: str


def _post_json(url: str, payload: dict[str, Any], request_id: str, timeout_s: float) -> tuple[int, dict[str, Any]]:
    body = json.dumps(payload).encode("utf-8")
    req = Request(
        url,
        method="POST",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Request-ID": request_id,
        },
    )
    with urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read()
        data = json.loads(raw.decode("utf-8")) if raw else {}
        return int(resp.status), data


def _get_json(url: str, request_id: str, timeout_s: float) -> tuple[int, dict[str, Any]]:
    req = Request(
        url,
        method="GET",
        headers={
            "Accept": "application/json",
            "X-Request-ID": request_id,
        },
    )
    with urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read()
        data = json.loads(raw.decode("utf-8")) if raw else {}
        return int(resp.status), data


def flash_book_many(
    *,
    base_url: str = "http://localhost:5001",
    appointment_payloads: list[dict[str, Any]],
    timeout_s: float = 15.0,
    confirm: bool = False,
    auto_pick_slot: bool = True,
    force_same_technician: bool = True,
    fallback_technician_id: int | str = 1,
) -> list[FlashResult]:
    """
    Fire N concurrent POST /appointments requests (race) for the same slot.
    Expected behavior: 1 success (202) + (N-1) conflicts (409).
    """
    if len(appointment_payloads) < 2:
        raise ValueError("appointment_payloads must have at least 2 payloads.")

    base_url = base_url.rstrip("/")
    post_url = f"{base_url}/appointments"

    if force_same_technician:
        chosen_tech = None
        for p in appointment_payloads:
            chosen_tech = chosen_tech or p.get("technician_id")
        if not chosen_tech:
            d_id = None
            st_id = None
            for p in appointment_payloads:
                d_id = d_id or p.get("dealership_id")
                st_id = st_id or p.get("service_type_id")
            if d_id is None or st_id is None:
                raise ValueError("force_same_technician requires dealership_id and service_type_id in payload(s).")
            try:
                chosen_tech = pick_first_technician_id(
                    base_url=base_url,
                    dealership_id=d_id,
                    service_type_id=st_id,
                    timeout_s=timeout_s,
                )
            except Exception:
                chosen_tech = str(fallback_technician_id)
        for p in appointment_payloads:
            p["technician_id"] = chosen_tech

    if auto_pick_slot and any(not p.get("desired_start") for p in appointment_payloads):
        d_id = None
        st_id = None
        tech_id = None
        for p in appointment_payloads:
            d_id = d_id or p.get("dealership_id")
            st_id = st_id or p.get("service_type_id")
            tech_id = tech_id or p.get("technician_id")
        if d_id is None or st_id is None:
            raise ValueError("auto_pick_slot requires dealership_id and service_type_id in payload(s).")
        desired_start = pick_first_available_slot(
            base_url=base_url,
            dealership_id=d_id,
            service_type_id=st_id,
            technician_id=tech_id,
            timeout_s=timeout_s,
        )
        for p in appointment_payloads:
            p.setdefault("desired_start", desired_start)

    barrier = threading.Barrier(len(appointment_payloads) + 1)
    out: list[FlashResult] = []
    out_lock = threading.Lock()

    def worker(idx: int, payload: dict[str, Any]):
        label = f"R{idx + 1}"
        rid = f"flash-{label}-{uuid.uuid4().hex[:12]}"
        barrier.wait()
        t0 = time.perf_counter()
        try:
            status, data = _post_json(post_url, payload, rid, timeout_s)
            ok = 200 <= status < 300
            err = None
        except HTTPError as e:
            status = int(getattr(e, "code", 0) or 0)
            try:
                raw = e.read()
                data = json.loads(raw.decode("utf-8")) if raw else None
            except Exception:
                data = None
            ok = False
            err = f"HTTPError({status})"
        except URLError as e:
            status = None
            data = None
            ok = False
            err = f"URLError: {e}"
        except Exception as e:
            status = None
            data = None
            ok = False
            err = f"{type(e).__name__}: {e}"
        elapsed = time.perf_counter() - t0

        with out_lock:
            out.append(
                FlashResult(
                    label=label,
                    ok=ok,
                    status=status,
                    elapsed_s=elapsed,
                    json=data if isinstance(data, dict) else None,
                    error=err,
                    request_id=rid,
                )
            )

    threads = [
        threading.Thread(target=worker, args=(i, appointment_payloads[i]), daemon=True)
        for i in range(len(appointment_payloads))
    ]
    for t in threads:
        t.start()
    barrier.wait()  # release all threads at once
    for t in threads:
        t.join()

    def _sort_key(r: FlashResult):
        if r.label.startswith("R") and r.label[1:].isdigit():
            return int(r.label[1:])
        return r.label

    out_sorted = sorted(out, key=_sort_key)

    if confirm:
        for r in out_sorted:
            appt_id = None
            if r.json and isinstance(r.json.get("appointment"), dict):
                appt_id = r.json["appointment"].get("id")
            if r.ok and appt_id is not None:
                _confirm_appointment(base_url=base_url, appointment_id=str(appt_id), timeout_s=timeout_s)

    return out_sorted


def pick_first_available_slot(
    *,
    base_url: str,
    dealership_id: int | str,
    service_type_id: int | str,
    technician_id: int | str | None = None,
    from_date: str | None = None,
    days: int = 14,
    timeout_s: float = 15.0,
) -> str:
    """
    Returns the first available slot start time as an ISO string with 'Z',
    by calling GET /dealerships/{id}/availability (calendar mode).

    This guarantees:
    - future time (server logic starts from now+1h rounded to 30min)
    - 30-min stepping
    - business-hours compliant (08:00–18:00 local)
    """
    base_url = base_url.rstrip("/")
    if from_date is None:
        from_date = datetime.now(timezone.utc).date().isoformat()

    params: dict[str, str] = {
        "service_type_id": str(service_type_id),
        "from_date": from_date,
        "days": str(days),
    }
    if technician_id is not None:
        params["technician_id"] = str(technician_id)

    url = f"{base_url}/dealerships/{dealership_id}/availability?{urlencode(params)}"
    rid = f"flash-avail-{uuid.uuid4().hex[:12]}"
    try:
        _, data = _get_json(url, rid, timeout_s)
    except Exception as e:
        raise RuntimeError(f"Failed to fetch availability: {e}") from e

    slots = data.get("slots")
    if not isinstance(slots, list):
        raise RuntimeError(f"Availability response missing 'slots': {data}")

    for day in slots:
        if not isinstance(day, dict):
            continue
        times = day.get("available_times")
        if not isinstance(times, list) or not times:
            continue
        first = times[0]
        if isinstance(first, dict) and isinstance(first.get("start"), str):
            return first["start"]

    raise RuntimeError(f"No available slots found (days={days}, from_date={from_date}).")


def pick_first_technician_id(
    *,
    base_url: str,
    dealership_id: int | str,
    service_type_id: int | str,
    timeout_s: float = 15.0,
) -> str:
    """
    Returns the first qualified technician id by calling:
      GET /dealerships/{id}/technicians?service_type_id=...
    """
    base_url = base_url.rstrip("/")
    url = f"{base_url}/dealerships/{dealership_id}/technicians?{urlencode({'service_type_id': str(service_type_id)})}"
    rid = f"flash-techs-{uuid.uuid4().hex[:12]}"
    try:
        _, data = _get_json(url, rid, timeout_s)
    except Exception as e:
        raise RuntimeError(f"Failed to fetch technicians: {e}") from e

    items = data.get("data")
    if not isinstance(items, list) or not items:
        raise RuntimeError(f"No technicians returned: {data}")

    first = items[0]
    if isinstance(first, dict) and first.get("id") is not None:
        return str(first["id"])

    raise RuntimeError(f"Technicians payload missing id: {data}")


def flash_book_same_slot(
    *,
    base_url: str = "http://localhost:5001",
    appointment_payload_a: dict[str, Any],
    appointment_payload_b: dict[str, Any],
    timeout_s: float = 15.0,
    confirm: bool = False,
    auto_pick_slot: bool = True,
    force_same_technician: bool = True,
    fallback_technician_id: int | str = 1,
) -> list[FlashResult]:
    """
    Fire 2 concurrent POST /appointments requests (race) for the same slot.

    Expected behavior for your constraint/race-condition assignment:
    - Exactly 1 request returns 202 with a PENDING hold
    - The other returns 409 ResourceUnavailable

    If confirm=True and a hold was created, this also calls PATCH /appointments/{id}/confirm
    sequentially for each successful booking (to finalize CONFIRMED).
    """
    return flash_book_many(
        base_url=base_url,
        appointment_payloads=[appointment_payload_a, appointment_payload_b],
        timeout_s=timeout_s,
        confirm=confirm,
        auto_pick_slot=auto_pick_slot,
        force_same_technician=force_same_technician,
        fallback_technician_id=fallback_technician_id,
    )


def _patch_json(url: str, request_id: str, timeout_s: float) -> tuple[int, dict[str, Any]]:
    req = Request(
        url,
        method="PATCH",
        data=b"{}",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Request-ID": request_id,
        },
    )
    with urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read()
        data = json.loads(raw.decode("utf-8")) if raw else {}
        return int(resp.status), data


def _confirm_appointment(*, base_url: str, appointment_id: str, timeout_s: float) -> None:
    url = f"{base_url.rstrip('/')}/appointments/{appointment_id}/confirm"
    rid = f"flash-confirm-{uuid.uuid4().hex[:12]}"
    try:
        _patch_json(url, rid, timeout_s)
    except Exception:
        # Confirmation is optional in this helper; ignore errors to keep the race signal clean.
        return


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Manual concurrency test: fire N concurrent POST /appointments to race on the same slot."
    )
    p.add_argument("--base-url", default="http://127.0.0.1:5001")
    p.add_argument("--n", type=int, default=5, help="Number of concurrent booking attempts.")
    p.add_argument("--timeout", type=float, default=15.0)
    p.add_argument("--confirm", action="store_true", help="Confirm any successful PENDING holds.")

    p.add_argument("--dealership-id", default="1")
    p.add_argument("--service-type-id", default="1")
    p.add_argument("--customer-id", default="C-000001")
    p.add_argument("--vehicle-id", default="VH-000001")
    p.add_argument("--technician-id", default=None, help="Optional. If omitted, a qualified tech is auto-picked.")
    p.add_argument(
        "--desired-start",
        default=None,
        help="Optional ISO datetime. If omitted, script auto-picks first available slot.",
    )
    return p.parse_args()


def main() -> int:
    a = _parse_args()

    payload: dict[str, Any] = {
        "dealership_id": a.dealership_id,
        "customer_id": a.customer_id,
        "vehicle_id": a.vehicle_id,
        "service_type_id": a.service_type_id,
    }
    if a.technician_id is not None:
        payload["technician_id"] = a.technician_id
    if a.desired_start is not None:
        payload["desired_start"] = a.desired_start

    res = flash_book_many(
        base_url=a.base_url,
        appointment_payloads=[payload.copy() for _ in range(max(a.n, 2))],
        timeout_s=a.timeout,
        confirm=bool(a.confirm),
        auto_pick_slot=True,
        force_same_technician=True,
    )

    ok = sum(1 for r in res if r.ok)
    by_status: dict[str, int] = {}
    for r in res:
        k = str(r.status)
        by_status[k] = by_status.get(k, 0) + 1

    desired_start = payload.get("desired_start") or (res[0].json or {}).get("requested_start")
    print(f"flash_booking: n={len(res)} ok={ok} statuses={by_status} desired_start={desired_start}")
    for r in res:
        appt_id = None
        if r.json and isinstance(r.json.get("appointment"), dict):
            appt_id = r.json["appointment"].get("id")
        print(f"[{r.label}] status={r.status} ok={r.ok} elapsed={r.elapsed_s:.3f}s appt_id={appt_id} req={r.request_id}")
        if r.error:
            print(f"  error={r.error}")
        if r.json and "error" in r.json:
            print(f"  api_error={r.json.get('error')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
