#!/usr/bin/env python3
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

RUNPOD_BASE_URL = "https://rest.runpod.io/v1"
TELEGRAM_BASE_URL = "https://api.telegram.org"

CACHE_PATH = Path(".cache/runpod_reminder.json")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_iso8601(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    if ts.endswith("Z"):
        ts = ts.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def load_cache() -> Dict[str, Any]:
    if not CACHE_PATH.exists():
        return {"last_update_id": None, "alerted": {}}
    try:
        return json.loads(CACHE_PATH.read_text())
    except json.JSONDecodeError:
        return {"last_update_id": None, "alerted": {}}


def save_cache(cache: Dict[str, Any]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2, sort_keys=True))


def runpod_headers(api_key: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def list_running_pods(api_key: str) -> List[Dict[str, Any]]:
    response = requests.get(
        f"{RUNPOD_BASE_URL}/pods",
        headers=runpod_headers(api_key),
        params={"desiredStatus": "RUNNING"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def terminate_pod(api_key: str, pod_id: str) -> Tuple[bool, str]:
    response = requests.delete(
        f"{RUNPOD_BASE_URL}/pods/{pod_id}",
        headers=runpod_headers(api_key),
        timeout=30,
    )
    if 200 <= response.status_code < 300:
        return True, "Termination requested."
    return False, f"Failed ({response.status_code}): {response.text[:300]}"


def telegram_request(
    token: str, method: str, payload: Dict[str, Any]
) -> Dict[str, Any]:
    response = requests.post(
        f"{TELEGRAM_BASE_URL}/bot{token}/{method}", json=payload, timeout=30
    )
    response.raise_for_status()
    return response.json()


def send_telegram_message(token: str, chat_id: str, text: str) -> None:
    telegram_request(token, "sendMessage", {"chat_id": chat_id, "text": text})


def get_telegram_updates(
    token: str, offset: Optional[int]
) -> List[Dict[str, Any]]:
    payload: Dict[str, Any] = {"timeout": 0, "limit": 100}
    if offset is not None:
        payload["offset"] = offset
    data = telegram_request(token, "getUpdates", payload)
    return data.get("result", [])


def format_pod_alert(pod: Dict[str, Any], runtime: timedelta) -> str:
    hours = runtime.total_seconds() / 3600
    name = pod.get("name") or "unnamed"
    pod_id = pod.get("id", "unknown")
    image = pod.get("image") or "unknown"
    gpu = (pod.get("gpu") or {}).get("displayName") or "unknown"
    started = pod.get("lastStartedAt") or "unknown"
    return (
        "Runpod pod running > 2 hours\n"
        f"ID: {pod_id}\n"
        f"Name: {name}\n"
        f"Image: {image}\n"
        f"GPU: {gpu}\n"
        f"Last started: {started}\n"
        f"Runtime: {hours:.2f} hours\n\n"
        f"To terminate: /terminate {pod_id}"
    )


def parse_terminate_command(text: str) -> Optional[str]:
    text = text.strip()
    if text.startswith("/terminate"):
        parts = text.split()
        if len(parts) >= 2:
            return parts[1].strip()
    if text.lower().startswith("terminate "):
        return text.split(None, 1)[1].strip()
    return None


def main() -> None:
    runpod_api_key = os.environ.get("RUNPOD_API_KEY")
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not runpod_api_key or not telegram_token:
        raise SystemExit("RUNPOD_API_KEY and TELEGRAM_BOT_TOKEN are required.")

    max_age_hours = float(os.environ.get("MAX_AGE_HOURS", "2"))
    alert_interval_minutes = float(os.environ.get("ALERT_INTERVAL_MINUTES", "30"))
    max_age = timedelta(hours=max_age_hours)
    alert_interval = timedelta(minutes=alert_interval_minutes)

    cache = load_cache()
    last_update_id = cache.get("last_update_id")
    alerted: Dict[str, str] = cache.get("alerted", {})

    now = utc_now()
    pods = list_running_pods(runpod_api_key)

    for pod in pods:
        started_at = parse_iso8601(pod.get("lastStartedAt"))
        if not started_at:
            continue
        runtime = now - started_at
        if runtime < max_age:
            continue

        pod_id = pod.get("id")
        if not pod_id:
            continue

        last_alerted_at = parse_iso8601(alerted.get(pod_id))
        if last_alerted_at and now - last_alerted_at < alert_interval:
            continue

        if telegram_chat_id:
            send_telegram_message(
                telegram_token, telegram_chat_id, format_pod_alert(pod, runtime)
            )
            alerted[pod_id] = now.isoformat()

    updates = get_telegram_updates(
        telegram_token, (last_update_id + 1) if last_update_id is not None else None
    )
    for update in updates:
        update_id = update.get("update_id")
        if update_id is not None:
            last_update_id = update_id

        message = update.get("message") or {}
        text = message.get("text") or ""
        chat = message.get("chat") or {}
        chat_id = str(chat.get("id")) if chat.get("id") is not None else None

        pod_id = parse_terminate_command(text)
        if not pod_id or not chat_id:
            continue

        if telegram_chat_id and chat_id != str(telegram_chat_id):
            continue

        ok, detail = terminate_pod(runpod_api_key, pod_id)
        status = "terminated" if ok else "failed"
        send_telegram_message(
            telegram_token,
            chat_id,
            f"Termination {status} for pod {pod_id}. {detail}",
        )

    cache["last_update_id"] = last_update_id
    cache["alerted"] = alerted
    save_cache(cache)


if __name__ == "__main__":
    main()
