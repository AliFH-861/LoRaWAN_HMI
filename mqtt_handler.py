"""
mqtt_handler.py — Thread-safe MQTT client for LoRaWAN HMI.
IEC 62443 / ISA-99 principles: credential isolation, TLS, audit logging.
"""

import json
import logging
import ssl
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import paho.mqtt.client as mqtt

logger = logging.getLogger("lorawan.mqtt")

_MISSING = object()


class MQTTHandler:
    _MAX_BACKOFF = 60

    def __init__(self, config: dict, client_id: str = "lorawan_hmi"):
        self._broker:    str  = config.get("broker", "localhost")
        self._port:      int  = int(config.get("port", 1883))
        self._keepalive: int  = int(config.get("keepalive", 60))
        self._tls_cfg:   dict = config.get("tls") or {}
        self._client_id: str  = client_id

        self._data:             Dict[str, Dict[str, Any]] = {}
        self._heartbeat_topics: Dict[str, float]          = {}
        self._subscriptions:    List[str]                 = []
        self._sub_set:          set                       = set()

        self._lock      = threading.Lock()
        self._connected = threading.Event()
        self._stop_flag = threading.Event()

        self._client = mqtt.Client(
            client_id=client_id, clean_session=True, protocol=mqtt.MQTTv311,
        )
        self._client.on_connect    = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message    = self._on_message
        self._thread: Optional[threading.Thread] = None

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    def start(self, username: Optional[str] = None, password: Optional[str] = None) -> None:
        if username:
            self._client.username_pw_set(username, password)
        self._client.will_set(
            f"hmi/{self._client_id}/status", payload="offline", qos=1, retain=True,
        )
        if self._tls_cfg.get("enabled"):
            self._configure_tls()
        self._thread = threading.Thread(
            target=self._connection_loop, daemon=True, name="mqtt-net",
        )
        self._thread.start()
        logger.info("MQTT handler started → %s:%s", self._broker, self._port)

    def stop(self) -> None:
        self._stop_flag.set()
        self._client.disconnect()
        if self._thread:
            self._thread.join(timeout=5)

    def subscribe(self, topics: list) -> None:
        if not topics:
            return
        with self._lock:
            new = [t for t in topics if t not in self._sub_set]
            self._subscriptions.extend(new)
            self._sub_set.update(new)
        if self._connected.is_set() and new:
            self._client.subscribe([(t, 1) for t in new])

    def set_subscriptions(self, desired: list) -> None:
        desired_set = set(desired)
        with self._lock:
            current_set = set(self._sub_set)
        to_add    = desired_set - current_set
        to_remove = current_set - desired_set
        if to_remove:
            if self._connected.is_set():
                self._client.unsubscribe(list(to_remove))
            with self._lock:
                self._sub_set      -= to_remove
                self._subscriptions = [t for t in self._subscriptions if t not in to_remove]
                for t in to_remove:
                    self._data.pop(t, None)
        if to_add:
            with self._lock:
                self._sub_set.update(to_add)
                self._subscriptions.extend(to_add)
            if self._connected.is_set():
                self._client.subscribe([(t, 1) for t in to_add])

    def register_heartbeat(self, topic: str) -> None:
        with self._lock:
            if topic not in self._heartbeat_topics:
                self._heartbeat_topics[topic] = 0.0

    def get_value(self, topic: str) -> Optional[Any]:
        with self._lock:
            entry = self._data.get(topic)
        return entry["value"] if entry else None

    def get_entry(self, topic: str) -> Optional[Dict]:
        with self._lock:
            return dict(self._data[topic]) if topic in self._data else None

    def is_heartbeat_alive(self, topic: str, timeout_s: float = 30.0) -> bool:
        with self._lock:
            last = self._heartbeat_topics.get(topic, 0.0)
        return last > 0 and (time.monotonic() - last) < timeout_s

    def publish(self, topic: str, payload: Any, qos: int = 1, retain: bool = False) -> bool:
        if not self._connected.is_set():
            logger.warning("Publish skipped — broker offline: %s", topic)
            return False
        if not topic or not isinstance(topic, str):
            return False
        if "+" in topic or "#" in topic:
            logger.error("Publish rejected — wildcards not allowed: %s", topic)
            return False
        try:
            encoded = payload if isinstance(payload, (bytes, bytearray)) else str(payload).encode("utf-8")
            info = self._client.publish(topic, payload=encoded, qos=qos, retain=retain)
            if qos > 0:
                info.wait_for_publish(timeout=3.0)
            return info.rc == mqtt.MQTT_ERR_SUCCESS
        except Exception as exc:
            logger.error("Publish exception: %s — topic=%s", exc, topic)
            return False

    def _configure_tls(self) -> None:
        tls = self._tls_cfg
        version_map = {"TLSv1.2": ssl.PROTOCOL_TLSv1_2, "TLSv1.3": ssl.PROTOCOL_TLS_CLIENT}
        cert_map    = {"CERT_REQUIRED": ssl.CERT_REQUIRED, "CERT_OPTIONAL": ssl.CERT_OPTIONAL, "CERT_NONE": ssl.CERT_NONE}
        tls_version = version_map.get(tls.get("tls_version", "TLSv1.2"), ssl.PROTOCOL_TLSv1_2)
        cert_reqs   = cert_map.get(tls.get("cert_reqs",   "CERT_REQUIRED"), ssl.CERT_REQUIRED)
        if cert_reqs == ssl.CERT_NONE:
            logger.warning("TLS: CERT_NONE — certificate validation DISABLED (dev/air-gap only)")
        self._client.tls_set(
            ca_certs=tls.get("ca_cert"), certfile=tls.get("client_cert"),
            keyfile=tls.get("client_key"), tls_version=tls_version, cert_reqs=cert_reqs,
        )

    def _connection_loop(self) -> None:
        backoff = 1
        while not self._stop_flag.is_set():
            try:
                self._client.connect(self._broker, self._port, self._keepalive)
                self._client.loop_forever()
            except Exception as exc:
                self._connected.clear()
                logger.warning("Connection failed: %s — retry in %ss", exc, backoff)
                time.sleep(backoff)
                backoff = min(backoff * 2, self._MAX_BACKOFF)

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self._connected.set()
            logger.info("MQTT connected")
            with self._lock:
                subs = list(self._sub_set)
            if subs:
                client.subscribe([(t, 1) for t in subs])
            client.publish(f"hmi/{self._client_id}/status", payload="online", qos=1, retain=True)
        else:
            self._connected.clear()
            logger.error("MQTT connect refused (rc=%s)", rc)

    def _on_disconnect(self, client, userdata, rc):
        self._connected.clear()
        if rc != 0:
            logger.warning("Unexpected MQTT disconnect (rc=%s) — reconnecting …", rc)

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        raw   = msg.payload.decode("utf-8", errors="replace").strip()
        value = self._parse(raw)
        ts    = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        with self._lock:
            self._data[topic] = {"value": value, "ts": ts, "raw": raw}
            if topic in self._heartbeat_topics:
                self._heartbeat_topics[topic] = time.monotonic()

    @staticmethod
    def _parse(raw: str) -> Any:
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            pass
        try:
            return float(raw)
        except ValueError:
            return raw
