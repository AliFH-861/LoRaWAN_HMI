"""
app.py — LoRaWAN Transformer Fleet Monitor HMI
ISA-101 light/blue design system · MQTT live data · schema-driven from metadata.yaml

Pages
-----
  (default)       Dashboard  — KPI cards + fleet status grid + active alarms
  ?page=fleet     Fleet      — Full transformer fleet table
  ?page=map       Map        — SVG coverage map with zone markers
  ?page=alarms    Alarms     — All active alarms/faults

Device detail
  ?plant=X&asset=Y  — Individual transformer page
"""

from __future__ import annotations

import logging
import math
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import streamlit as st
import yaml
from dotenv import load_dotenv

from mqtt_handler import MQTTHandler

# ── Bootstrap ────────────────────────────────────────────────────────────────
load_dotenv()
Path("logs").mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.FileHandler("logs/lorawan_hmi.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log       = logging.getLogger("lorawan.app")
audit_log = logging.getLogger("lorawan.audit")

# ── Streamlit page config ────────────────────────────────────────────────────
st.set_page_config(
    page_title="LoRaWAN Transformer Monitor",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Global CSS (ISA-101 light/blue design system) ────────────────────────────
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');

#MainMenu,footer,header{display:none!important}
[data-testid="stHeader"],[data-testid="collapsedControl"],section[data-testid="stSidebar"]{display:none!important}
.stApp{overflow:hidden!important;background:#F8F9FA!important}
[data-testid="stAppViewContainer"],[data-testid="stMain"]{padding:0!important;overflow:hidden!important;height:100vh!important}
.block-container{padding:0!important;max-width:100%!important;height:100vh!important;overflow:hidden!important}

:root{
  --bg-page:#F8F9FA; --bg-card:#FFFFFF; --bg-input:#F1F4F9;
  --blue:#007BFF; --blue-light:#E3F0FF; --blue-lighter:#F0F7FF; --blue-navy:#1A237E;
  --amber:#F59E0B; --amber-bg:#FFFBEB; --amber-bd:#FDE68A;
  --red:#EF4444; --red-bg:#FEF2F2; --red-bd:#FECACA;
  --gray-bd:#E5E7EB; --gray-mid:#CBD5E1; --gray-lbl:#9CA3AF; --gray-txt:#6B7280;
  --txt:#0F172A; --txt2:#475569; --txt3:#94A3B8;
  --sh:0 1px 3px rgba(0,0,0,.06),0 1px 2px rgba(0,0,0,.04);
  --sh-md:0 4px 12px rgba(0,0,0,.07),0 1px 3px rgba(0,0,0,.05);
  --icon-w:60px; --side-w:228px; --top-h:58px; --r:10px;
  --font:'Plus Jakarta Sans','Segoe UI',system-ui,sans-serif;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html,body{width:100%;height:100%}

.root{display:grid;grid-template-columns:var(--icon-w) var(--side-w) 1fr;grid-template-rows:var(--top-h) 1fr;height:100vh;font-family:var(--font);font-size:13.5px;color:var(--txt);background:var(--bg-page);-webkit-font-smoothing:antialiased}

/* TOPBAR */
.topbar{grid-column:1/-1;grid-row:1;background:#fff;border-bottom:1px solid var(--gray-bd);display:flex;align-items:center;padding:0 20px;gap:16px;z-index:50}
.logo{display:flex;align-items:center;gap:9px;text-decoration:none}
.logo-mark{width:32px;height:32px;background:linear-gradient(135deg,#007BFF,#1A237E);border-radius:8px;display:flex;align-items:center;justify-content:center}
.logo-mark svg{width:17px;height:17px;stroke:white;fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
.logo-text{font-size:14px;font-weight:700;color:var(--txt);letter-spacing:-.01em}
.logo-sub{font-size:10px;color:var(--txt3);letter-spacing:.05em;text-transform:uppercase}
.tb-div{width:1px;height:22px;background:var(--gray-bd)}
.breadcrumb{font-size:12px;color:var(--txt3);display:flex;align-items:center;gap:5px}
.breadcrumb b{color:var(--txt2);font-weight:600}
.tb-end{margin-left:auto;display:flex;align-items:center;gap:10px}
.sys-pill{display:flex;align-items:center;gap:6px;padding:4px 12px;border-radius:20px;font-size:11.5px;font-weight:600}
.sys-pill.ok{background:#ECFDF5;color:#065F46;border:1px solid #A7F3D0}
.sys-pill.err{background:var(--red-bg);color:#991B1B;border:1px solid var(--red-bd)}
.sys-dot{width:7px;height:7px;border-radius:50%;animation:blink 2s ease-in-out infinite}
.sys-pill.ok .sys-dot{background:#10B981}
.sys-pill.err .sys-dot{background:var(--red);animation:blink-f 1s ease-in-out infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.4}}
@keyframes blink-f{0%,100%{opacity:1}50%{opacity:.3}}
.clock{font-size:12px;font-weight:600;color:var(--txt2);background:var(--bg-input);padding:4px 10px;border-radius:6px;border:1px solid var(--gray-bd);font-variant-numeric:tabular-nums;min-width:78px;text-align:center}

/* ICON RAIL */
.icon-rail{grid-column:1;grid-row:2;background:#fff;border-right:1px solid var(--gray-bd);display:flex;flex-direction:column;align-items:center;padding:14px 0;gap:4px}
.rail-btn{width:38px;height:38px;border-radius:8px;border:1px solid transparent;background:transparent;color:var(--txt3);display:flex;align-items:center;justify-content:center;transition:all .15s;text-decoration:none;position:relative}
.rail-btn:hover{background:var(--blue-lighter);color:var(--blue)}
.rail-btn.active{background:var(--blue-light);color:var(--blue);border-color:rgba(0,123,255,.2)}
.rail-btn svg{width:17px;height:17px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
.rail-sep{width:28px;height:1px;background:var(--gray-bd);margin:4px 0}
.rail-badge{position:absolute;top:4px;right:4px;width:8px;height:8px;border-radius:50%;background:var(--red);border:1.5px solid white}

/* SIDEBAR */
.sidebar{grid-column:2;grid-row:2;background:#fff;border-right:1px solid var(--gray-bd);overflow-y:auto;padding:16px 12px}
.nav-section{margin-bottom:18px}
.nav-grp{font-size:10px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--gray-lbl);padding:0 8px;margin-bottom:4px}
.nav-item{display:flex;align-items:center;gap:9px;padding:7px 8px;border-radius:7px;font-size:13px;font-weight:500;color:var(--txt2);transition:all .13s;border:1px solid transparent;margin-bottom:1px;text-decoration:none}
.nav-item:hover{background:var(--blue-lighter);color:var(--txt)}
.nav-item.active{background:var(--blue-light);color:var(--blue);font-weight:600;border-color:rgba(0,123,255,.15)}
.nav-item svg{width:15px;height:15px;flex-shrink:0;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
.nav-badge{margin-left:auto;font-size:10px;font-weight:700;padding:1px 7px;border-radius:10px;background:var(--red-bg);color:var(--red);border:1px solid var(--red-bd)}

/* MAIN */
.main{grid-column:3;grid-row:2;background:var(--bg-page);overflow-y:auto;padding:22px 24px;display:flex;flex-direction:column;gap:20px}
.page-header{display:flex;align-items:center;justify-content:space-between}
.page-title{font-size:18px;font-weight:700;color:var(--txt);letter-spacing:-.02em}
.page-sub{font-size:12.5px;color:var(--txt3);margin-top:1px}
.header-actions{display:flex;gap:8px;align-items:center}
.btn{display:inline-flex;align-items:center;gap:5px;padding:7px 14px;border-radius:7px;font-family:var(--font);font-size:12.5px;font-weight:600;border:1px solid transparent;transition:all .14s;text-decoration:none}
.btn-outline{background:#fff;color:var(--txt2);border-color:var(--gray-bd);box-shadow:var(--sh)}
.btn-outline:hover{background:var(--bg-input)}
.btn svg{width:13px;height:13px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}

/* CARDS */
.card{background:#fff;border-radius:var(--r);border:1px solid var(--gray-bd);box-shadow:var(--sh)}
.card-head{display:flex;align-items:center;padding:12px 16px;border-bottom:1px solid var(--gray-bd);gap:8px}
.card-title{font-size:13px;font-weight:700;color:var(--txt);flex:1}
.card-body{padding:16px}

/* KPI CARDS */
.metrics-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}
.metric-card{background:#fff;border-radius:var(--r);border:1px solid var(--gray-bd);box-shadow:var(--sh);padding:16px;position:relative;overflow:hidden;transition:box-shadow .18s,transform .18s}
.metric-card:hover{box-shadow:var(--sh-md);transform:translateY(-1px)}
.metric-card::before{content:'';position:absolute;left:0;top:12px;bottom:12px;width:3px;border-radius:0 3px 3px 0;background:var(--mc-accent,var(--blue))}
.mc-icon{width:36px;height:36px;border-radius:8px;display:flex;align-items:center;justify-content:center;background:var(--mc-bg,var(--blue-light));margin-bottom:10px}
.mc-icon svg{width:17px;height:17px;fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
.mc-label{font-size:11px;font-weight:600;letter-spacing:.05em;text-transform:uppercase;color:var(--txt3);margin-bottom:4px}
.mc-value{font-size:26px;font-weight:700;line-height:1;color:var(--txt);letter-spacing:-.02em}
.mc-unit{font-size:13px;font-weight:500;color:var(--txt3);margin-left:2px}
.mc-foot{display:flex;align-items:center;gap:5px;margin-top:8px;font-size:11.5px;color:var(--txt3)}

/* BADGE */
.badge{display:inline-flex;align-items:center;gap:4px;padding:2px 9px;border-radius:20px;font-size:11px;font-weight:700}
.badge.ok{background:#ECFDF5;color:#065F46;border:1px solid #A7F3D0}
.badge.warn{background:var(--amber-bg);color:#92400E;border:1px solid var(--amber-bd)}
.badge.fault{background:var(--red-bg);color:#991B1B;border:1px solid var(--red-bd);animation:pfault 1.2s ease-in-out infinite}
.badge.idle{background:#F1F5F9;color:var(--gray-txt);border:1px solid var(--gray-bd)}
@keyframes pfault{0%,100%{opacity:1}50%{opacity:.55}}

/* STATUS DOT */
.sdot{width:8px;height:8px;border-radius:50%;display:inline-block;flex-shrink:0}
.sdot.ok{background:var(--blue)}
.sdot.warn{background:var(--amber);animation:blink-f 1s ease-in-out infinite}
.sdot.fault{background:var(--red);animation:blink-f 1s ease-in-out infinite}
.sdot.off{background:var(--gray-mid)}

/* SECTION DIVIDER */
.sec-row{display:flex;align-items:center;gap:10px;margin-bottom:10px}
.sec-lbl{font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--txt3)}
.sec-hr{flex:1;height:1px;background:var(--gray-bd)}

/* FLEET TABLE */
.fleet-table{width:100%;border-collapse:collapse}
.fleet-table th{text-align:left;font-size:10.5px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--txt3);padding:8px 12px;border-bottom:1px solid var(--gray-bd);background:#FAFBFC;white-space:nowrap}
.fleet-table td{padding:10px 12px;border-bottom:1px solid var(--gray-bd);font-size:12.5px;color:var(--txt2);vertical-align:middle}
.fleet-table tr:last-child td{border-bottom:none}
.fleet-table tbody tr:hover td{background:#F3F7FF}
.ft-name{font-weight:600;color:var(--txt)}
.ft-desc{font-size:11px;color:var(--txt3)}

/* SIGNAL BARS */
.sig-bars{display:inline-flex;align-items:flex-end;gap:2px;height:16px}
.sig-bar{width:4px;border-radius:2px 2px 0 0;background:var(--gray-bd)}
.sig-bar.lit{background:var(--sb-col,#007BFF)}

/* OIL MINI BAR */
.oil-wrap{display:flex;align-items:center;gap:7px;min-width:90px}
.oil-track{flex:1;height:6px;background:var(--bg-input);border-radius:3px;overflow:hidden;border:1px solid var(--gray-bd)}
.oil-fill{height:100%;border-radius:3px;transition:width .5s}
.oil-pct{font-size:11.5px;font-weight:600;min-width:32px;text-align:right;font-variant-numeric:tabular-nums}

/* BATTERY */
.batt-wrap{display:flex;align-items:center;gap:5px}
.batt-body{width:18px;height:10px;border:1.5px solid currentColor;border-radius:2px;position:relative;overflow:hidden;display:inline-flex}
.batt-fill{position:absolute;left:0;top:0;bottom:0;border-radius:1px}
.batt-tip{width:3px;height:5px;background:currentColor;border-radius:0 1px 1px 0;margin-left:1px;align-self:center;flex-shrink:0}
.batt-pct{font-size:12px;font-weight:600;font-variant-numeric:tabular-nums}

/* FLEET STATUS CARDS (dashboard grid) */
.fsc-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:12px}
.fsc-card{background:#fff;border-radius:var(--r);border:1px solid var(--gray-bd);box-shadow:var(--sh);padding:14px;display:flex;flex-direction:column;gap:8px;transition:box-shadow .15s;text-decoration:none}
.fsc-card:hover{box-shadow:var(--sh-md)}
.fsc-hd{display:flex;align-items:center;gap:8px}
.fsc-name{font-size:13px;font-weight:700;color:var(--txt);flex:1}
.fsc-zone{font-size:10px;color:var(--txt3);font-weight:500;letter-spacing:.05em;text-transform:uppercase}
.fsc-row{display:flex;align-items:center;justify-content:space-between;font-size:12px;gap:6px}
.fsc-key{color:var(--txt3)}
.fsc-val{font-weight:600;color:var(--txt);font-variant-numeric:tabular-nums}

/* ALARM ROWS */
.alarm-row{display:flex;align-items:center;gap:10px;padding:9px 14px;border-bottom:1px solid var(--gray-bd)}
.alarm-row:last-child{border-bottom:none}
.alarm-icon{width:28px;height:28px;border-radius:6px;display:flex;align-items:center;justify-content:center;flex-shrink:0}
.alarm-icon svg{width:14px;height:14px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.alarm-name{font-size:12.5px;font-weight:600;color:var(--txt)}
.alarm-sub{font-size:11px;color:var(--txt3)}
.alarm-val{margin-left:auto}

/* DEVICE DETAIL */
.device-grid{display:grid;grid-template-columns:160px 1fr;gap:20px;align-items:start}
.panels-2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.panels-3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px}
.info-tbl{width:100%;border-collapse:collapse}
.info-tbl td{padding:8px 12px;border-bottom:1px solid var(--gray-bd);font-size:12.5px}
.info-tbl tr:last-child td{border-bottom:none}
.info-lbl{font-weight:600;color:var(--txt2);width:45%}
.info-val{color:var(--txt);font-variant-numeric:tabular-nums}

/* GAUGE CELLS */
.gauge-row{display:flex;flex-wrap:wrap;gap:14px}
.gauge-cell{flex:1;min-width:120px;max-width:160px;background:#fff;border-radius:var(--r);border:1px solid var(--gray-bd);box-shadow:var(--sh);padding:14px 12px 10px;display:flex;flex-direction:column;align-items:center}
.gauge-lbl{font-size:11px;font-weight:600;color:var(--txt3);letter-spacing:.04em;text-transform:uppercase;margin-top:6px;text-align:center}
</style>""", unsafe_allow_html=True)

# ── Constants ────────────────────────────────────────────────────────────────
_ARC_COLORS = {
    "normal":   {"arc": "#007BFF", "track": "#EBF5FF", "text": "#007BFF"},
    "warning":  {"arc": "#F59E0B", "track": "#FFFBEB", "text": "#F59E0B"},
    "critical": {"arc": "#EF4444", "track": "#FEF2F2", "text": "#EF4444"},
    "offline":  {"arc": "#CBD5E1", "track": "#F1F5F9", "text": "#94A3B8"},
}
_STATUS_HEX = {
    "normal": "#007BFF", "warning": "#F59E0B",
    "critical": "#EF4444", "offline": "#CBD5E1",
}
_ZONE_COLORS = [
    {"fill": "#EBF5FF", "stroke": "#007BFF", "label": "#1565C0"},
    {"fill": "#FFFBEB", "stroke": "#F59E0B", "label": "#92400E"},
    {"fill": "#F5F3FF", "stroke": "#7C3AED", "label": "#5B21B6"},
    {"fill": "#F0FDF4", "stroke": "#059669", "label": "#065F46"},
]

_JS_CLOCK = """<script>
(function(){
  function tick(){
    var t=new Date();
    var s=t.toLocaleTimeString('en-US',{hour12:false,hour:'2-digit',minute:'2-digit',second:'2-digit'});
    var c=document.getElementById('lw-clock');
    if(c)c.textContent=s+' UTC';
  }
  tick();setInterval(tick,1000);
})();
</script>"""

# ── Helpers ──────────────────────────────────────────────────────────────────
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")

def _san(s: object, maxlen: int = 120) -> str:
    return _CTRL_RE.sub("", str(s))[:maxlen].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def _classify_gauge(val, tag: dict) -> str:
    if val is None:
        return "offline"
    try:
        v = float(val)
    except (TypeError, ValueError):
        return "offline"
    cmin = tag.get("critical_min"); cmax = tag.get("critical_max")
    wmin = tag.get("warning_min");  wmax = tag.get("warning_max")
    nmin = tag.get("normal_min");   nmax = tag.get("normal_max")
    if cmin is not None and cmax is not None and cmin <= v <= cmax:
        return "critical"
    if wmin is not None and wmax is not None and wmin <= v <= wmax:
        return "warning"
    if nmin is not None and nmax is not None and nmin <= v <= nmax:
        return "normal"
    return "warning"

def _get_num(mqtt_h: MQTTHandler, topic: str) -> Optional[float]:
    if not topic:
        return None
    v = mqtt_h.get_value(topic)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

def _count_alarms(asset: dict, mqtt_h: MQTTHandler) -> int:
    count = 0
    for tag in asset.get("tags", []):
        topic = tag.get("mqtt_topic", "")
        if not topic:
            continue
        val = mqtt_h.get_value(topic)
        if val is None:
            continue
        if tag.get("type") == "alarm":
            if str(val).strip() == str(tag.get("alarm_value", "")).strip():
                count += 1
        elif tag.get("type") == "status":
            nv = [str(x) for x in tag.get("normal_values", [])]
            if str(val).strip() not in nv:
                count += 1
    return count

def _is_online(asset: dict, mqtt_h: MQTTHandler) -> bool:
    hb_t = asset.get("heartbeat_topic")
    if not hb_t:
        return True
    return mqtt_h.is_heartbeat_alive(hb_t, asset.get("heartbeat_timeout_s", 120))

def _join_ok(asset: dict, mqtt_h: MQTTHandler) -> Optional[bool]:
    jt = asset.get("lorawan", {}).get("join_status_topic", "")
    if not jt:
        return None
    raw = mqtt_h.get_value(jt)
    if raw is None:
        return None
    return str(raw).strip().lower() in ("joined", "1", "true", "yes")

# ── Metadata ─────────────────────────────────────────────────────────────────
@st.cache_resource
def load_metadata() -> dict:
    with open("metadata.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)

# ── MQTT handler ─────────────────────────────────────────────────────────────
@st.cache_resource
def get_mqtt_handler(_cfg_id: int) -> MQTTHandler:
    cfg    = load_metadata()
    mqtt_h = MQTTHandler(cfg.get("mqtt", {}), client_id=os.getenv("MQTT_CLIENT_ID", "lorawan_hmi"))
    topics: list[str] = []
    for plant in cfg.get("plants", []):
        for asset in plant.get("assets", []):
            hb = asset.get("heartbeat_topic")
            if hb:
                topics.append(hb)
                mqtt_h.register_heartbeat(hb)
            jt = asset.get("lorawan", {}).get("join_status_topic")
            if jt:
                topics.append(jt)
            for tag in asset.get("tags", []):
                tp = tag.get("mqtt_topic")
                if tp:
                    topics.append(tp)
    mqtt_h.subscribe(topics)
    mqtt_h.start(
        username=os.getenv("MQTT_USERNAME"),
        password=os.getenv("MQTT_PASSWORD"),
    )
    return mqtt_h

# ── Component builders ────────────────────────────────────────────────────────

def html_topbar(page: str, total_alarms: int, connected: bool, now_str: str) -> str:
    page_labels = {
        "dashboard": "Dashboard",
        "fleet":     "Fleet View",
        "map":       "Coverage Map",
        "alarms":    "Alarms",
        "device":    "Device Detail",
    }
    breadcrumb = page_labels.get(page, "Dashboard")
    conn_cls   = "ok" if connected else "err"
    conn_lbl   = "Broker Online" if connected else "Broker Offline"
    alarm_badge = (f'<span style="background:#FEF2F2;color:#991B1B;border:1px solid #FECACA;'
                   f'padding:3px 10px;border-radius:20px;font-size:11px;font-weight:700;">'
                   f'{total_alarms} Active Alarm{"s" if total_alarms != 1 else ""}</span>'
                   if total_alarms else "")
    return (
        f'<div class="topbar">'
        f'<a class="logo" href="?" target="_self">'
        f'<div class="logo-mark"><svg viewBox="0 0 24 24"><path d="M5 12.55a11 11 0 0 1 14.08 0"/>'
        f'<path d="M1.42 9a16 16 0 0 1 21.16 0"/><path d="M8.53 16.11a6 6 0 0 1 6.95 0"/>'
        f'<circle cx="12" cy="20" r="1" fill="white" stroke="white"/></svg></div>'
        f'<div><div class="logo-text">LoRaWAN Monitor</div>'
        f'<div class="logo-sub">Transformer Fleet</div></div></a>'
        f'<div class="tb-div"></div>'
        f'<div class="breadcrumb"><span>Fleet</span>'
        f'<svg viewBox="0 0 24 24" style="width:12px;height:12px;fill:none;stroke:currentColor;stroke-width:2"><polyline points="9 18 15 12 9 6"/></svg>'
        f'<b>{breadcrumb}</b></div>'
        f'<div class="tb-end">'
        f'{alarm_badge}'
        f'<div class="sys-pill {conn_cls}"><div class="sys-dot"></div>{conn_lbl}</div>'
        f'<div class="clock" id="lw-clock">{now_str}</div>'
        f'</div>'
        f'</div>'
    )


def html_icon_rail(page: str, alarm_count: int) -> str:
    badge = '<span class="rail-badge"></span>' if alarm_count else ""

    def _btn(p, title, svg_inner, extra=""):
        cls = "rail-btn active" if page == p else "rail-btn"
        href = "?" if p == "dashboard" else f"?page={p}"
        return (f'<a class="{cls}" href="{href}" title="{title}" target="_self">'
                f'{extra}<svg viewBox="0 0 24 24">{svg_inner}</svg></a>')

    return (
        f'<nav class="icon-rail">'
        + _btn("dashboard", "Dashboard",
               '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/>'
               '<rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>')
        + _btn("fleet", "Fleet View",
               '<line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/>'
               '<line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/>'
               '<line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>')
        + _btn("map", "Coverage Map",
               '<polygon points="3 6 9 3 15 6 21 3 21 18 15 21 9 18 3 21"/>'
               '<line x1="9" y1="3" x2="9" y2="18"/><line x1="15" y1="6" x2="15" y2="21"/>')
        + f'<div class="rail-sep"></div>'
        + _btn("alarms", "Alarms", '<bell/>'
               '<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>'
               '<path d="M13.73 21a2 2 0 0 1-3.46 0"/>', badge)
        + f'</nav>'
    )


def html_sidebar(cfg: dict, page: str, sel_plant_id: str, sel_asset_id: str,
                 mqtt_h: MQTTHandler) -> str:
    asset_svg = ('<svg viewBox="0 0 24 24"><rect x="2" y="7" width="20" height="14" rx="2"/>'
                 '<path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/></svg>')

    def _nav(p, label, svg_inner, href=None):
        is_act = (page == p)
        lnk    = href or ("?" if p == "dashboard" else f"?page={p}")
        return (f'<a class="nav-item{"  active" if is_act else ""}"'
                f' href="{lnk}" target="_self">'
                f'<svg viewBox="0 0 24 24">{svg_inner}</svg>{label}</a>')

    pages_section = (
        f'<div class="nav-section">'
        f'<div class="nav-grp">Navigation</div>'
        + _nav("dashboard", "Dashboard",
               '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/>'
               '<rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>')
        + _nav("fleet", "Fleet View",
               '<line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/>'
               '<line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/>'
               '<line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>')
        + _nav("map", "Coverage Map",
               '<polygon points="3 6 9 3 15 6 21 3 21 18 15 21 9 18 3 21"/>'
               '<line x1="9" y1="3" x2="9" y2="18"/><line x1="15" y1="6" x2="15" y2="21"/>')
        + _nav("alarms", "Alarms",
               '<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>'
               '<path d="M13.73 21a2 2 0 0 1-3.46 0"/>')
        + f'</div>'
    )

    fleet_section = f'<div class="nav-section"><div class="nav-grp">Devices</div>'
    for plant in cfg.get("plants", []):
        fleet_section += f'<div style="font-size:11px;font-weight:600;color:#94A3B8;padding:6px 8px 2px;">{_san(plant["name"])}</div>'
        for asset in plant.get("assets", []):
            is_act = (page == "device" and plant["id"] == sel_plant_id and asset["id"] == sel_asset_id)
            ac     = _count_alarms(asset, mqtt_h)
            online = _is_online(asset, mqtt_h)
            dot_cls = "ok" if (online and ac == 0) else ("fault" if ac else "off")
            badge   = f'<span class="nav-badge">{ac}</span>' if ac else ""
            fleet_section += (
                f'<a class="nav-item{"  active" if is_act else ""}"'
                f' href="?page=device&plant={plant["id"]}&asset={asset["id"]}" target="_self">'
                f'<span class="sdot {dot_cls}"></span>{_san(asset["name"])}{badge}</a>'
            )
    fleet_section += '</div>'

    return f'<nav class="sidebar">{pages_section}{fleet_section}</nav>'


def _kpi_card(label: str, value: str, unit: str, accent: str, bg: str,
              icon_path: str, foot: str) -> str:
    return (
        f'<div class="metric-card" style="--mc-accent:{accent};--mc-bg:{bg};">'
        f'<div class="mc-icon"><svg viewBox="0 0 24 24" style="stroke:{accent};">{icon_path}</svg></div>'
        f'<div class="mc-label">{label}</div>'
        f'<div class="mc-value">{value}<span class="mc-unit">{unit}</span></div>'
        f'<div class="mc-foot">{foot}</div>'
        f'</div>'
    )


def _signal_bars(rssi_val: Optional[float], state: str) -> str:
    color  = _STATUS_HEX.get(state, "#CBD5E1")
    heights = [4, 7, 11, 16]
    if rssi_val is None:
        lit = 0
    elif rssi_val >= -70:
        lit = 4
    elif rssi_val >= -85:
        lit = 3
    elif rssi_val >= -100:
        lit = 2
    else:
        lit = 1
    bars = ""
    for i, h in enumerate(heights):
        cls = f'sig-bar lit" style="height:{h}px;--sb-col:{color}' if i < lit else f'sig-bar" style="height:{h}px'
        bars += f'<div class="{cls}"></div>'
    val_str = f"{rssi_val:.0f} dBm" if rssi_val is not None else "--"
    return f'<div style="display:flex;align-items:center;gap:6px;"><div class="sig-bars">{bars}</div><span style="font-size:11.5px;font-weight:600;color:{color};font-variant-numeric:tabular-nums;">{val_str}</span></div>'


def _battery_bar(pct: Optional[float], state: str) -> str:
    color = _STATUS_HEX.get(state, "#CBD5E1")
    fill_w = f"{max(0, min(100, pct or 0)):.0f}%"
    pct_str = f"{pct:.0f}%" if pct is not None else "--"
    return (
        f'<div class="batt-wrap" style="color:{color};">'
        f'<div style="display:inline-flex;align-items:center;">'
        f'<div class="batt-body"><div class="batt-fill" style="width:{fill_w};background:{color};"></div></div>'
        f'<div class="batt-tip"></div></div>'
        f'<span class="batt-pct" style="color:{color};">{pct_str}</span>'
        f'</div>'
    )


def _oil_mini_bar(pct: Optional[float], state: str) -> str:
    color   = _STATUS_HEX.get(state, "#CBD5E1")
    fill_w  = f"{max(0, min(100, pct or 0)):.1f}%"
    pct_str = f"{pct:.0f}%" if pct is not None else "--"
    return (
        f'<div class="oil-wrap">'
        f'<div class="oil-track"><div class="oil-fill" style="width:{fill_w};background:{color};"></div></div>'
        f'<span class="oil-pct" style="color:{color};">{pct_str}</span>'
        f'</div>'
    )


def html_oil_tank_gauge(pct: Optional[float], state: str, uid: str = "g") -> str:
    colors = _ARC_COLORS.get(state, _ARC_COLORS["offline"])
    arc_c  = colors["arc"]
    trk_c  = colors["track"]
    raw    = max(0.0, min(100.0, float(pct) if pct is not None else 0.0))
    tank_h = 128
    fill_h = tank_h * raw / 100.0
    fill_y = 32 + tank_h - fill_h
    warn_y = 32 + tank_h * (1 - 0.25)
    crit_y = 32 + tank_h * (1 - 0.10)
    label  = f"{raw:.0f}%" if pct is not None else "--"
    cid    = f"tc{uid}"
    return (
        f'<svg viewBox="0 0 120 200" width="120" height="200" xmlns="http://www.w3.org/2000/svg">'
        f'<rect x="52" y="14" width="16" height="6" rx="2" fill="#CBD5E1"/>'
        f'<rect x="55" y="20" width="10" height="12" fill="#94A3B8"/>'
        f'<clipPath id="{cid}"><rect x="10" y="32" width="100" height="{tank_h}" rx="8"/></clipPath>'
        f'<g clip-path="url(#{cid})">'
        f'<rect x="10" y="32" width="100" height="{tank_h}" fill="{trk_c}"/>'
        f'<rect x="10" y="{fill_y:.1f}" width="100" height="{fill_h:.1f}" fill="{arc_c}" opacity="0.9"/>'
        f'</g>'
        f'<rect x="10" y="32" width="100" height="{tank_h}" rx="8" fill="none" stroke="#CBD5E1" stroke-width="2"/>'
        f'<line x1="12" y1="{warn_y:.1f}" x2="108" y2="{warn_y:.1f}" stroke="#F59E0B" stroke-width="1.5" stroke-dasharray="4 3"/>'
        f'<line x1="12" y1="{crit_y:.1f}" x2="108" y2="{crit_y:.1f}" stroke="#EF4444" stroke-width="1.5" stroke-dasharray="4 3"/>'
        f'<text x="60" y="110" text-anchor="middle" font-size="20" font-weight="700" fill="{arc_c}" font-family="system-ui">{label}</text>'
        f'<text x="60" y="126" text-anchor="middle" font-size="9" fill="#94A3B8" font-family="system-ui" letter-spacing="0.08em">OIL LEVEL</text>'
        f'<text x="112" y="{warn_y+3:.0f}" font-size="8" fill="#F59E0B" font-family="system-ui">25%</text>'
        f'<text x="112" y="{crit_y+3:.0f}" font-size="8" fill="#EF4444" font-family="system-ui">10%</text>'
        f'<rect x="35" y="{32+tank_h}" width="50" height="8" rx="2" fill="#CBD5E1"/>'
        f'<rect x="42" y="{32+tank_h+8}" width="36" height="6" rx="2" fill="#94A3B8"/>'
        f'</svg>'
    )


def html_arc_gauge(val: Optional[float], tag: dict, state: str,
                   w: int = 130, h: int = 120) -> str:
    colors = _ARC_COLORS.get(state, _ARC_COLORS["offline"])
    arc_c  = colors["arc"]
    trk_c  = colors["track"]
    CX, CY, R = w / 2, h * 0.56, min(w, h) * 0.4
    START, SPAN = -120, 240
    unit   = _san(tag.get("unit", ""), 10)
    dmin   = float(tag.get("display_min", 0))
    dmax   = float(tag.get("display_max", 100))

    def _arc(deg_start, deg_span):
        pts = []
        steps = max(2, int(abs(deg_span) / 5))
        for i in range(steps + 1):
            a = math.radians(deg_start + deg_span * i / steps - 90)
            pts.append((CX + R * math.cos(a), CY + R * math.sin(a)))
        d = f"M {pts[0][0]:.1f} {pts[0][1]:.1f}"
        for px, py in pts[1:]:
            d += f" L {px:.1f} {py:.1f}"
        return d

    track_d = _arc(START, SPAN)
    if val is not None and state != "offline":
        pct      = max(0.0, min(1.0, (float(val) - dmin) / max(dmax - dmin, 1e-9)))
        fill_span = SPAN * pct
        fill_d   = _arc(START, fill_span)
    else:
        fill_d = None

    val_str  = f"{float(val):.1f}" if val is not None else "--"
    lbl_str  = _san(tag.get("name", ""), 20)

    svg = (
        f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" xmlns="http://www.w3.org/2000/svg">'
        f'<path d="{track_d}" fill="none" stroke="{trk_c}" stroke-width="7" stroke-linecap="round"/>'
    )
    if fill_d:
        svg += f'<path d="{fill_d}" fill="none" stroke="{arc_c}" stroke-width="7" stroke-linecap="round"/>'
    svg += (
        f'<text x="{CX:.0f}" y="{CY:.0f}" text-anchor="middle" dominant-baseline="middle"'
        f' font-size="{int(R*0.42)}" font-weight="700" fill="{arc_c}" font-family="system-ui">{val_str}</text>'
        f'<text x="{CX:.0f}" y="{CY + R*0.35:.0f}" text-anchor="middle"'
        f' font-size="{int(R*0.24)}" fill="#94A3B8" font-family="system-ui">{unit}</text>'
        f'</svg>'
    )
    return svg


def _page_wrapper(topbar: str, icon_rail: str, sidebar: str,
                  title: str, sub: str, actions: str, body: str) -> str:
    return (
        f'<div class="root">'
        f'{topbar}{icon_rail}{sidebar}'
        f'<main class="main">'
        f'<div class="page-header">'
        f'<div><div class="page-title">{title}</div><div class="page-sub">{sub}</div></div>'
        f'<div class="header-actions">{actions}</div>'
        f'</div>'
        f'{body}'
        f'</main>'
        f'</div>'
    ) + _JS_CLOCK

# ── Page builders ─────────────────────────────────────────────────────────────

def html_dashboard_page(cfg: dict, mqtt_h: MQTTHandler,
                        total_alarms: int, now_str: str) -> str:
    plants     = cfg.get("plants", [])
    all_assets = [a for p in plants for a in p.get("assets", [])]
    n_total    = len(all_assets)
    n_online   = sum(1 for a in all_assets if _is_online(a, mqtt_h))
    n_joined   = sum(1 for a in all_assets if _join_ok(a, mqtt_h) is True)
    n_alarms   = total_alarms

    kpi_accent = "#007BFF" if n_alarms == 0 else "#EF4444"
    kpi_bg     = "#EBF5FF" if n_alarms == 0 else "#FEF2F2"

    kpis = (
        _kpi_card("Total Devices",  str(n_total),  "",    "#007BFF", "#EBF5FF",
                  '<rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>',
                  f'{n_online} online')
        + _kpi_card("Online", str(n_online), f"/{n_total}", "#007BFF" if n_online == n_total else "#F59E0B",
                    "#EBF5FF" if n_online == n_total else "#FFFBEB",
                    '<path d="M5 12.55a11 11 0 0 1 14.08 0"/><path d="M1.42 9a16 16 0 0 1 21.16 0"/>'
                    '<path d="M8.53 16.11a6 6 0 0 1 6.95 0"/><circle cx="12" cy="20" r="1" fill="currentColor"/>',
                    "heartbeat OK" if n_online == n_total else f"{n_total-n_online} offline")
        + _kpi_card("Active Alarms", str(n_alarms), "",
                    kpi_accent, kpi_bg,
                    '<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>',
                    "All clear" if n_alarms == 0 else "Requires attention")
        + _kpi_card("Network Joined", str(n_joined), f"/{n_total}",
                    "#007BFF" if n_joined == n_total else "#F59E0B",
                    "#EBF5FF" if n_joined == n_total else "#FFFBEB",
                    '<path d="M1.42 9a16 16 0 0 1 21.16 0"/><path d="M5 12.55a11 11 0 0 1 14.08 0"/>'
                    '<path d="M8.53 16.11a6 6 0 0 1 6.95 0"/><circle cx="12" cy="20" r="1" fill="currentColor"/>',
                    "All joined" if n_joined == n_total else f"{n_total-n_joined} not joined")
    )

    fsc_cards = ""
    for plant in plants:
        for asset in plant.get("assets", []):
            online  = _is_online(asset, mqtt_h)
            ac      = _count_alarms(asset, mqtt_h)
            joined  = _join_ok(asset, mqtt_h)
            state   = "critical" if ac > 0 else ("normal" if online else "offline")
            dot_cls = "ok" if state == "normal" else ("fault" if state == "critical" else "off")

            oil_tag = next((t for t in asset.get("tags", []) if t["id"] == "oil_level_pct"), None)
            batt_tag= next((t for t in asset.get("tags", []) if t["id"] == "battery_pct"), None)
            rssi_tag= next((t for t in asset.get("tags", []) if t["id"] == "rssi"), None)

            oil_v   = _get_num(mqtt_h, (oil_tag  or {}).get("mqtt_topic", ""))
            batt_v  = _get_num(mqtt_h, (batt_tag or {}).get("mqtt_topic", ""))
            rssi_v  = _get_num(mqtt_h, (rssi_tag or {}).get("mqtt_topic", ""))

            oil_st  = _classify_gauge(oil_v,  oil_tag  or {})
            batt_st = _classify_gauge(batt_v, batt_tag or {})
            rssi_st = _classify_gauge(rssi_v, rssi_tag or {})

            oil_c   = _STATUS_HEX.get(oil_st,  "#CBD5E1")
            batt_c  = _STATUS_HEX.get(batt_st, "#CBD5E1")

            join_dot = ""
            if joined is True:
                join_dot = '<span class="sdot ok" style="width:7px;height:7px;"></span> Joined'
            elif joined is False:
                join_dot = '<span class="sdot warn" style="width:7px;height:7px;"></span> Not Joined'
            else:
                join_dot = '<span class="sdot off" style="width:7px;height:7px;"></span> Unknown'

            alarm_badge = (f'<span class="badge fault">{ac} Alarm{"s" if ac!=1 else ""}</span>' if ac
                           else '<span class="badge ok">Clear</span>')

            href = f'?page=device&plant={plant["id"]}&asset={asset["id"]}'
            fsc_cards += (
                f'<a class="fsc-card" href="{href}" target="_self">'
                f'<div class="fsc-hd"><span class="sdot {dot_cls}"></span>'
                f'<span class="fsc-name">{_san(asset["name"])}</span>'
                f'<span class="fsc-zone">{_san(plant["name"])}</span></div>'
                f'<div class="fsc-row"><span class="fsc-key">Network</span>'
                f'<span style="display:flex;align-items:center;gap:4px;font-size:11.5px;font-weight:600;">{join_dot}</span></div>'
                f'<div class="fsc-row"><span class="fsc-key">Oil Level</span>'
                f'<span style="display:flex;align-items:center;gap:6px;">'
                f'<div style="width:60px;height:5px;background:#F1F4F9;border-radius:3px;overflow:hidden;border:1px solid #E2E8F0;">'
                f'<div style="width:{oil_v or 0:.0f}%;height:100%;background:{oil_c};border-radius:3px;"></div></div>'
                f'<span class="fsc-val" style="color:{oil_c};">{oil_v:.0f}%' if oil_v is not None else
                f'<span class="fsc-val" style="color:#CBD5E1;">--%'
                f'</span></span></div>'
                f'<div class="fsc-row"><span class="fsc-key">Battery</span>'
                f'<span class="fsc-val" style="color:{batt_c};">{batt_v:.0f}%' if batt_v is not None else
                f'<span class="fsc-val" style="color:#CBD5E1;">--%'
                f'</span></div>'
                f'<div class="fsc-row"><span class="fsc-key">Signal</span>'
                f'{_signal_bars(rssi_v, rssi_st)}</div>'
                f'<div style="margin-top:2px;">{alarm_badge}</div>'
                f'</a>'
            )

    active_alarms_html = ""
    alarm_entries = []
    for plant in plants:
        for asset in plant.get("assets", []):
            for tag in asset.get("tags", []):
                topic = tag.get("mqtt_topic", "")
                if not topic:
                    continue
                val = mqtt_h.get_value(topic)
                if val is None:
                    continue
                is_alarm = False
                if tag.get("type") == "alarm" and str(val).strip() == str(tag.get("alarm_value", "")):
                    is_alarm = True
                elif tag.get("type") == "status":
                    if str(val).strip() not in [str(x) for x in tag.get("normal_values", [])]:
                        is_alarm = True
                if is_alarm:
                    alarm_entries.append((plant, asset, tag, val))

    if alarm_entries:
        rows = ""
        for plant, asset, tag, val in alarm_entries[:10]:
            rows += (
                f'<div class="alarm-row">'
                f'<div class="alarm-icon" style="background:#FEF2F2;">'
                f'<svg viewBox="0 0 24 24" style="stroke:#EF4444;">'
                f'<polygon points="7.86 2 16.14 2 22 7.86 22 16.14 16.14 22 7.86 22 2 16.14 2 7.86"/>'
                f'<line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>'
                f'</svg></div>'
                f'<div><div class="alarm-name">{_san(tag.get("alarm_label", tag.get("name", "")))}</div>'
                f'<div class="alarm-sub">{_san(asset["name"])} — {_san(plant["name"])}</div></div>'
                f'<div class="alarm-val"><span class="badge fault">ACTIVE</span></div>'
                f'</div>'
            )
        active_alarms_html = (
            f'<div class="sec-row"><span class="sec-lbl">Active Alarms</span><div class="sec-hr"></div></div>'
            f'<div class="card"><div class="card-body" style="padding:0;">{rows}</div></div>'
        )

    body = (
        f'<div class="metrics-grid">{kpis}</div>'
        f'<div class="sec-row"><span class="sec-lbl">Fleet Status</span><div class="sec-hr"></div>'
        f'<a href="?page=fleet" class="btn btn-outline" style="padding:4px 10px;font-size:11px;" target="_self">'
        f'<svg viewBox="0 0 24 24"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/>'
        f'<line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/>'
        f'<line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>'
        f'Full Table</a></div>'
        f'<div class="fsc-grid">{fsc_cards}</div>'
        + active_alarms_html
    )
    return _page_wrapper(
        html_topbar("dashboard", total_alarms, True, now_str),
        html_icon_rail("dashboard", total_alarms),
        html_sidebar(cfg, "dashboard", "", "", mqtt_h),
        "Dashboard",
        f"Fleet overview &middot; {n_total} transformers &middot; Last updated <span id='lw-clock'>{now_str}</span>",
        f'<a href="?" class="btn btn-outline" target="_self">'
        f'<svg viewBox="0 0 24 24"><polyline points="23 4 23 10 17 10"/>'
        f'<path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>Refresh</a>',
        body,
    )


def html_fleet_page(cfg: dict, mqtt_h: MQTTHandler,
                    total_alarms: int, now_str: str) -> str:
    plants = cfg.get("plants", [])
    rows   = ""
    for plant in plants:
        for asset in plant.get("assets", []):
            online  = _is_online(asset, mqtt_h)
            ac      = _count_alarms(asset, mqtt_h)
            joined  = _join_ok(asset, mqtt_h)

            oil_tag  = next((t for t in asset.get("tags", []) if t["id"] == "oil_level_pct"), None)
            batt_tag = next((t for t in asset.get("tags", []) if t["id"] == "battery_pct"), None)
            rssi_tag = next((t for t in asset.get("tags", []) if t["id"] == "rssi"), None)
            snr_tag  = next((t for t in asset.get("tags", []) if t["id"] == "snr"), None)
            bv_tag   = next((t for t in asset.get("tags", []) if t["id"] == "battery_voltage"), None)

            oil_v   = _get_num(mqtt_h, (oil_tag  or {}).get("mqtt_topic", ""))
            batt_v  = _get_num(mqtt_h, (batt_tag or {}).get("mqtt_topic", ""))
            rssi_v  = _get_num(mqtt_h, (rssi_tag or {}).get("mqtt_topic", ""))
            snr_v   = _get_num(mqtt_h, (snr_tag  or {}).get("mqtt_topic", ""))
            bv_v    = _get_num(mqtt_h, (bv_tag   or {}).get("mqtt_topic", ""))

            oil_st  = _classify_gauge(oil_v,  oil_tag  or {})
            batt_st = _classify_gauge(batt_v, batt_tag or {})
            rssi_st = _classify_gauge(rssi_v, rssi_tag or {})

            status_dot = ("ok" if (online and ac == 0) else ("fault" if ac else "off"))
            status_lbl = "Online" if online else "Offline"

            join_html = ""
            if joined is True:
                join_html = '<span class="sdot ok" style="width:7px;height:7px;"></span> Joined'
            elif joined is False:
                join_html = '<span class="sdot warn" style="width:7px;height:7px;"></span> Not joined'
            else:
                join_html = '<span class="sdot off" style="width:7px;height:7px;"></span> —'

            alarm_html = (f'<span class="badge fault">{ac}</span>' if ac
                          else '<span class="badge ok">—</span>')

            href = f'?page=device&plant={plant["id"]}&asset={asset["id"]}'
            rows += (
                f'<tr>'
                f'<td><div class="ft-name">{_san(asset["name"])}</div>'
                f'<div class="ft-desc">{_san(asset.get("description",""))}</div></td>'
                f'<td>{_san(plant["name"])}</td>'
                f'<td><div style="display:flex;align-items:center;gap:6px;">'
                f'<span class="sdot {status_dot}"></span>{status_lbl}</div></td>'
                f'<td><div style="display:flex;align-items:center;gap:4px;font-size:12px;font-weight:600;">{join_html}</div></td>'
                f'<td>{_oil_mini_bar(oil_v, oil_st)}</td>'
                f'<td>{_battery_bar(batt_v, batt_st)}</td>'
                f'<td>{_signal_bars(rssi_v, rssi_st)}</td>'
                f'<td style="font-size:12px;font-weight:600;font-variant-numeric:tabular-nums;'
                f'color:{"#F59E0B" if snr_v is not None and snr_v < 5 else "#007BFF" if snr_v is not None else "#CBD5E1"};">'
                f'{f"{snr_v:.1f} dB" if snr_v is not None else "—"}</td>'
                f'<td>{alarm_html}</td>'
                f'<td><a href="{href}" class="btn btn-outline" style="padding:4px 10px;font-size:11px;" target="_self">View</a></td>'
                f'</tr>'
            )

    table = (
        f'<div class="card">'
        f'<table class="fleet-table"><thead><tr>'
        f'<th>Device</th><th>Zone</th><th>Status</th><th>Network</th>'
        f'<th>Oil Level</th><th>Battery</th><th>RSSI</th><th>SNR</th>'
        f'<th>Alarms</th><th></th>'
        f'</tr></thead><tbody>{rows}</tbody></table>'
        f'</div>'
    )
    return _page_wrapper(
        html_topbar("fleet", total_alarms, True, now_str),
        html_icon_rail("fleet", total_alarms),
        html_sidebar(cfg, "fleet", "", "", mqtt_h),
        "Transformer Fleet",
        f"{len([a for p in plants for a in p.get('assets', [])])} devices across {len(plants)} zones",
        f'<a href="?page=fleet" class="btn btn-outline" target="_self">'
        f'<svg viewBox="0 0 24 24"><polyline points="23 4 23 10 17 10"/>'
        f'<path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>Refresh</a>',
        table,
    )


def html_map_page(cfg: dict, mqtt_h: MQTTHandler,
                  total_alarms: int, now_str: str) -> str:
    plants = cfg.get("plants", [])
    SW, SH = 760, 440

    grid_lines = ""
    for xi in range(0, SW, 76):
        grid_lines += f'<line x1="{xi}" y1="0" x2="{xi}" y2="{SH}" stroke="#E2E8F0" stroke-width="0.5"/>'
    for yi in range(0, SH, 44):
        grid_lines += f'<line x1="0" y1="{yi}" x2="{SW}" y2="{yi}" stroke="#E2E8F0" stroke-width="0.5"/>'

    zone_svgs   = ""
    marker_svgs = ""

    for idx, plant in enumerate(plants):
        zc = _ZONE_COLORS[idx % len(_ZONE_COLORS)]
        assets = plant.get("assets", [])
        if not assets:
            continue

        positions = [a.get("map_position", {"x": 50, "y": 50}) for a in assets]
        xs = [p["x"] * SW / 100 for p in positions]
        ys = [p["y"] * SH / 100 for p in positions]
        pad = 40
        zx1 = max(0, min(xs) - pad)
        zy1 = max(0, min(ys) - pad)
        zx2 = min(SW, max(xs) + pad)
        zy2 = min(SH, max(ys) + pad)
        zw  = zx2 - zx1
        zh  = zy2 - zy1

        zone_svgs += (
            f'<rect x="{zx1:.0f}" y="{zy1:.0f}" width="{zw:.0f}" height="{zh:.0f}"'
            f' rx="10" fill="{zc["fill"]}" stroke="{zc["stroke"]}" stroke-width="1.5" opacity="0.7"/>'
            f'<text x="{zx1+10:.0f}" y="{zy1+20:.0f}" font-size="11" font-weight="700"'
            f' fill="{zc["label"]}" font-family="system-ui" letter-spacing="0.05em">{_san(plant["name"]).upper()}</text>'
        )

        for asset in assets:
            pos    = asset.get("map_position", {"x": 50, "y": 50})
            mx     = pos["x"] * SW / 100
            my     = pos["y"] * SH / 100
            online = _is_online(asset, mqtt_h)
            ac     = _count_alarms(asset, mqtt_h)
            joined = _join_ok(asset, mqtt_h)
            state  = "critical" if ac > 0 else ("normal" if online else "offline")
            mc     = _STATUS_HEX.get(state, "#CBD5E1")

            rssi_tag = next((t for t in asset.get("tags", []) if t["id"] == "rssi"), None)
            rssi_v   = _get_num(mqtt_h, (rssi_tag or {}).get("mqtt_topic", ""))
            sig_r    = 60 if rssi_v is None else max(20, min(80, 80 - abs(rssi_v + 60)))

            name_short = _san(asset["name"], 18)
            dev_eui    = _san(asset.get("lorawan", {}).get("dev_eui", ""), 24)

            join_label = ""
            if joined is True:
                join_label = f'<tspan fill="#007BFF"> ● Joined</tspan>'
            elif joined is False:
                join_label = f'<tspan fill="#F59E0B"> ○ Not Joined</tspan>'

            marker_svgs += (
                f'<circle cx="{mx:.0f}" cy="{my:.0f}" r="{sig_r:.0f}"'
                f' fill="{mc}" opacity="0.07" stroke="{mc}" stroke-width="1" stroke-dasharray="5 4"/>'
                f'<circle cx="{mx:.0f}" cy="{my:.0f}" r="12"'
                f' fill="{mc}" stroke="white" stroke-width="2.5"/>'
                f'<path d="M {mx:.0f} {my-6:.0f} q-4,0-4,4 q0,4 4,4 q4,0 4,-4 q0,-4-4,-4"'
                f' fill="white" opacity="0.8"/>'
                f'<text x="{mx+16:.0f}" y="{my-1:.0f}" font-size="11" font-weight="700"'
                f' fill="#0F172A" font-family="system-ui">{name_short}{join_label}</text>'
                f'<text x="{mx+16:.0f}" y="{my+13:.0f}" font-size="9" fill="#94A3B8" font-family="system-ui">{dev_eui}</text>'
            )

    legend_x, legend_y = 10, SH - 75
    legend = (
        f'<rect x="{legend_x}" y="{legend_y}" width="180" height="65" rx="6" fill="white" stroke="#E2E8F0" stroke-width="1" opacity="0.95"/>'
        f'<text x="{legend_x+10}" y="{legend_y+16}" font-size="9" font-weight="700" fill="#94A3B8" font-family="system-ui" letter-spacing="0.08em">LEGEND</text>'
        f'<circle cx="{legend_x+16}" cy="{legend_y+30}" r="5" fill="#007BFF"/>'
        f'<text x="{legend_x+26}" y="{legend_y+34}" font-size="9" fill="#475569" font-family="system-ui">Online / Normal</text>'
        f'<circle cx="{legend_x+100}" cy="{legend_y+30}" r="5" fill="#EF4444"/>'
        f'<text x="{legend_x+110}" y="{legend_y+34}" font-size="9" fill="#475569" font-family="system-ui">Active Alarm</text>'
        f'<circle cx="{legend_x+16}" cy="{legend_y+50}" r="5" fill="#F59E0B"/>'
        f'<text x="{legend_x+26}" y="{legend_y+54}" font-size="9" fill="#475569" font-family="system-ui">Warning / Degraded</text>'
        f'<circle cx="{legend_x+100}" cy="{legend_y+50}" r="5" fill="#CBD5E1"/>'
        f'<text x="{legend_x+110}" y="{legend_y+54}" font-size="9" fill="#475569" font-family="system-ui">Offline</text>'
    )

    svg = (
        f'<svg viewBox="0 0 {SW} {SH}" width="100%" style="border-radius:10px;border:1px solid #E5E7EB;display:block;" xmlns="http://www.w3.org/2000/svg">'
        f'<rect width="{SW}" height="{SH}" fill="#F8F9FA"/>'
        f'{grid_lines}'
        f'{zone_svgs}'
        f'{marker_svgs}'
        f'{legend}'
        f'</svg>'
    )

    n_plants = len(plants)
    n_assets = sum(len(p.get("assets", [])) for p in plants)
    body = (
        f'<div class="card"><div class="card-body" style="padding:12px;">{svg}</div></div>'
        f'<div style="font-size:11.5px;color:#94A3B8;text-align:center;">'
        f'{n_assets} transformer nodes across {n_plants} coverage zones &middot; '
        f'Dashed circles indicate estimated LoRaWAN signal radius'
        f'</div>'
    )
    return _page_wrapper(
        html_topbar("map", total_alarms, True, now_str),
        html_icon_rail("map", total_alarms),
        html_sidebar(cfg, "map", "", "", mqtt_h),
        "Coverage Map",
        "LoRaWAN deployment zones and device positions",
        f'<a href="?page=map" class="btn btn-outline" target="_self">'
        f'<svg viewBox="0 0 24 24"><polyline points="23 4 23 10 17 10"/>'
        f'<path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>Refresh</a>',
        body,
    )


def html_alarms_page(cfg: dict, mqtt_h: MQTTHandler,
                     total_alarms: int, now_str: str) -> str:
    plants  = cfg.get("plants", [])
    entries = []
    for plant in plants:
        for asset in plant.get("assets", []):
            online = _is_online(asset, mqtt_h)
            for tag in asset.get("tags", []):
                topic = tag.get("mqtt_topic", "")
                if not topic:
                    continue
                val = mqtt_h.get_value(topic)
                if val is None:
                    continue
                if tag.get("type") == "alarm":
                    active = str(val).strip() == str(tag.get("alarm_value", ""))
                    entries.append({
                        "plant": plant, "asset": asset, "tag": tag,
                        "val": val, "active": active,
                        "label": tag.get("alarm_label" if active else "normal_label", tag.get("name", "")),
                    })
                elif tag.get("type") == "status":
                    nv     = [str(x) for x in tag.get("normal_values", [])]
                    active = str(val).strip() not in nv
                    entries.append({
                        "plant": plant, "asset": asset, "tag": tag,
                        "val": val, "active": active,
                        "label": tag.get("name", ""),
                    })

    active_entries  = [e for e in entries if e["active"]]
    normal_entries  = [e for e in entries if not e["active"]]

    def _row(e, is_active):
        if is_active:
            icon_bg = "#FEF2F2"; icon_stroke = "#EF4444"; badge = '<span class="badge fault">ACTIVE</span>'
            icon_path = ('<polygon points="7.86 2 16.14 2 22 7.86 22 16.14 16.14 22 7.86 22 2 16.14 2 7.86"/>'
                         '<line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>')
        else:
            icon_bg = "#ECFDF5"; icon_stroke = "#10B981"; badge = '<span class="badge ok">Normal</span>'
            icon_path = '<polyline points="20 6 9 17 4 12"/>'
        return (
            f'<div class="alarm-row">'
            f'<div class="alarm-icon" style="background:{icon_bg};">'
            f'<svg viewBox="0 0 24 24" style="stroke:{icon_stroke};">{icon_path}</svg></div>'
            f'<div><div class="alarm-name">{_san(e["label"])}</div>'
            f'<div class="alarm-sub">{_san(e["asset"]["name"])} — {_san(e["plant"]["name"])}</div></div>'
            f'<div class="alarm-val">{badge}</div>'
            f'</div>'
        )

    active_html = "".join(_row(e, True)  for e in active_entries) or (
        '<div style="padding:20px;text-align:center;color:#94A3B8;font-size:13px;">No active alarms</div>'
    )
    normal_html = "".join(_row(e, False) for e in normal_entries[:20])

    body = (
        f'<div class="sec-row"><span class="sec-lbl">Active Faults</span><div class="sec-hr"></div>'
        f'<span style="background:#FEF2F2;color:#991B1B;border:1px solid #FECACA;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:700;">'
        f'{len(active_entries)}</span></div>'
        f'<div class="card"><div class="card-body" style="padding:0;">{active_html}</div></div>'
        + (f'<div class="sec-row"><span class="sec-lbl">Normal State</span><div class="sec-hr"></div></div>'
           f'<div class="card"><div class="card-body" style="padding:0;">{normal_html}</div></div>'
           if normal_html else "")
    )
    return _page_wrapper(
        html_topbar("alarms", total_alarms, True, now_str),
        html_icon_rail("alarms", total_alarms),
        html_sidebar(cfg, "alarms", "", "", mqtt_h),
        "Alarms &amp; Events",
        f"{len(active_entries)} active fault{'s' if len(active_entries)!=1 else ''} across fleet",
        f'<a href="?page=alarms" class="btn btn-outline" target="_self">'
        f'<svg viewBox="0 0 24 24"><polyline points="23 4 23 10 17 10"/>'
        f'<path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>Refresh</a>',
        body,
    )


def html_device_page(plant: dict, asset: dict, mqtt_h: MQTTHandler,
                     cfg: dict, total_alarms: int, now_str: str) -> str:
    tags      = asset.get("tags", [])
    lora      = asset.get("lorawan", {})
    dev_eui   = _san(lora.get("dev_eui", "—"))
    app_id    = _san(lora.get("app_id",  "—"))
    join_t    = lora.get("join_status_topic", "")
    join_raw  = mqtt_h.get_value(join_t) if join_t else None
    joined    = str(join_raw).strip().lower() in ("joined","1","true","yes") if join_raw is not None else None
    online    = _is_online(asset, mqtt_h)
    ac        = _count_alarms(asset, mqtt_h)

    join_html = ("Joined" if joined is True else "Not Joined" if joined is False else "—")
    join_dot  = ("ok" if joined else "warn" if joined is False else "off")

    def _tag(tid):
        return next((t for t in tags if t.get("id") == tid), None)

    oil_tag  = _tag("oil_level_pct")
    batt_tag = _tag("battery_pct")
    bv_tag   = _tag("battery_voltage")
    rssi_tag = _tag("rssi")
    snr_tag  = _tag("snr")
    dist_tag = _tag("oil_distance_cm")

    oil_v    = _get_num(mqtt_h, (oil_tag  or {}).get("mqtt_topic",""))
    batt_v   = _get_num(mqtt_h, (batt_tag or {}).get("mqtt_topic",""))
    bv_v     = _get_num(mqtt_h, (bv_tag   or {}).get("mqtt_topic",""))
    rssi_v   = _get_num(mqtt_h, (rssi_tag or {}).get("mqtt_topic",""))
    snr_v    = _get_num(mqtt_h, (snr_tag  or {}).get("mqtt_topic",""))
    dist_v   = _get_num(mqtt_h, (dist_tag or {}).get("mqtt_topic",""))

    oil_st   = _classify_gauge(oil_v,  oil_tag  or {})
    batt_st  = _classify_gauge(batt_v, batt_tag or {})
    bv_st    = _classify_gauge(bv_v,   bv_tag   or {})
    rssi_st  = _classify_gauge(rssi_v, rssi_tag or {})
    snr_st   = _classify_gauge(snr_v,  snr_tag  or {})

    tank_svg = html_oil_tank_gauge(oil_v, "offline" if not online else oil_st, uid=asset["id"])

    def _kpi(label, val_str, unit, accent, bg, icon):
        return (f'<div class="metric-card" style="--mc-accent:{accent};--mc-bg:{bg};">'
                f'<div class="mc-icon"><svg viewBox="0 0 24 24" style="stroke:{accent};">{icon}</svg></div>'
                f'<div class="mc-label">{label}</div>'
                f'<div class="mc-value">{val_str}<span class="mc-unit">{unit}</span></div>'
                f'</div>')

    batt_acc = _STATUS_HEX.get(batt_st, "#CBD5E1")
    rssi_acc = _STATUS_HEX.get(rssi_st, "#CBD5E1")
    snr_acc  = _STATUS_HEX.get(snr_st,  "#CBD5E1")
    bv_acc   = _STATUS_HEX.get(bv_st,   "#CBD5E1")

    kpi_row = (
        f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;">'
        + _kpi("Battery", f"{batt_v:.0f}" if batt_v is not None else "—", "%",
               batt_acc, batt_acc.replace("FF","22").replace("#0","#E"),
               '<rect x="1" y="6" width="18" height="12" rx="2"/><line x1="23" y1="11" x2="23" y2="13"/>')
        + _kpi("Batt. Voltage", f"{bv_v:.2f}" if bv_v is not None else "—", "V",
               bv_acc, "#EBF5FF",
               '<path d="M14 2L3 14h9l-1 8 10-12h-9l1-8z"/>')
        + _kpi("RSSI", f"{rssi_v:.0f}" if rssi_v is not None else "—", "dBm",
               rssi_acc, "#EBF5FF",
               '<path d="M5 12.55a11 11 0 0 1 14.08 0"/><path d="M1.42 9a16 16 0 0 1 21.16 0"/>'
               '<path d="M8.53 16.11a6 6 0 0 1 6.95 0"/><circle cx="12" cy="20" r="1" fill="currentColor"/>')
        + _kpi("SNR", f"{snr_v:.1f}" if snr_v is not None else "—", "dB",
               snr_acc, "#EBF5FF",
               '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>')
        + f'</div>'
    )

    section_1 = (
        f'<div class="device-grid">'
        f'<div style="display:flex;flex-direction:column;align-items:center;gap:8px;">'
        f'{tank_svg}'
        f'<div style="font-size:11px;color:#94A3B8;text-align:center;">Oil Distance: '
        f'{"%.1f cm" % dist_v if dist_v is not None else "—"}</div>'
        f'</div>'
        f'<div style="display:flex;flex-direction:column;gap:14px;">{kpi_row}</div>'
        f'</div>'
    )

    lora_rows = (
        f'<tr><td class="info-lbl">Device EUI</td><td class="info-val" style="font-family:monospace;font-size:12px;">{dev_eui}</td></tr>'
        f'<tr><td class="info-lbl">Application</td><td class="info-val">{app_id}</td></tr>'
        f'<tr><td class="info-lbl">Network Status</td><td class="info-val">'
        f'<div style="display:flex;align-items:center;gap:6px;"><span class="sdot {join_dot}"></span>{join_html}</div></td></tr>'
        f'<tr><td class="info-lbl">Device Status</td><td class="info-val">'
        f'<div style="display:flex;align-items:center;gap:6px;">'
        f'<span class="sdot {"ok" if online else "off"}"></span>{"Online" if online else "Offline"}</div></td></tr>'
        f'<tr><td class="info-lbl">Description</td><td class="info-val">{_san(asset.get("description","—"))}</td></tr>'
    )

    alarm_tags  = [t for t in tags if t.get("type") == "alarm"]
    status_tags = [t for t in tags if t.get("type") == "status"]
    alarm_rows  = ""
    for tag in alarm_tags + status_tags:
        topic = tag.get("mqtt_topic","")
        val   = mqtt_h.get_value(topic) if topic else None
        if tag.get("type") == "alarm":
            active = val is not None and str(val).strip() == str(tag.get("alarm_value",""))
            lbl    = tag.get("alarm_label" if active else "normal_label", tag.get("name",""))
            cls    = "fault" if active else "ok"
        else:
            nv     = [str(x) for x in tag.get("normal_values", [])]
            active = val is not None and str(val).strip() not in nv
            lbl    = "Active" if active else "Normal"
            cls    = "fault" if active else "ok"
        alarm_rows += (
            f'<tr><td class="info-lbl">{_san(tag.get("name",""))}</td>'
            f'<td class="info-val"><span class="badge {cls}">{_san(lbl)}</span></td></tr>'
        )

    gauge_tags = [t for t in tags if t.get("type") == "gauge"
                  and t["id"] not in ("oil_level_pct","battery_pct","battery_voltage","rssi","snr","oil_distance_cm")]
    gauge_cells = ""
    for tag in gauge_tags:
        val = _get_num(mqtt_h, tag.get("mqtt_topic",""))
        st  = _classify_gauge(val, tag)
        gauge_cells += (
            f'<div class="gauge-cell">'
            f'{html_arc_gauge(val, tag, "offline" if not online else st, w=120, h=110)}'
            f'<div class="gauge-lbl">{_san(tag.get("name",""))}</div>'
            f'</div>'
        )

    section_2 = (
        f'<div class="panels-2">'
        f'<div class="card"><div class="card-head"><div class="card-title">LoRaWAN Network</div></div>'
        f'<div class="card-body" style="padding:0;"><table class="info-tbl"><tbody>{lora_rows}</tbody></table></div></div>'
        f'<div class="card"><div class="card-head"><div class="card-title">Alarms &amp; Sensors</div></div>'
        f'<div class="card-body" style="padding:0;"><table class="info-tbl"><tbody>{alarm_rows}</tbody></table></div></div>'
        f'</div>'
    )
    section_3 = (f'<div class="gauge-row">{gauge_cells}</div>' if gauge_cells else "")

    body = section_1 + section_2 + (section_3 or "")
    href = f'?page=device&plant={plant["id"]}&asset={asset["id"]}'
    return _page_wrapper(
        html_topbar("device", total_alarms, True, now_str),
        html_icon_rail("device", total_alarms),
        html_sidebar(cfg, "device", plant["id"], asset["id"], mqtt_h),
        _san(asset["name"]),
        f'{_san(plant["name"])} &middot; {dev_eui}',
        f'<a href="{href}" class="btn btn-outline" target="_self">'
        f'<svg viewBox="0 0 24 24"><polyline points="23 4 23 10 17 10"/>'
        f'<path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>Refresh</a>',
        body,
    )


# ── Control submission ────────────────────────────────────────────────────────
def _process_ctrl_submissions(cfg: dict, mqtt_h: MQTTHandler) -> None:
    qp = dict(st.query_params)
    for key, raw_val in qp.items():
        if not key.startswith("ctrl__"):
            continue
        topic = key[6:].replace("__", "/")
        val   = str(raw_val).strip()
        if val not in ("0", "1"):
            continue
        state_key = f"_pub_{key}_{val}"
        if st.session_state.get(state_key):
            continue
        ok = mqtt_h.publish(topic, val)
        audit_log.info("CTRL publish: topic=%s val=%s ok=%s", topic, val, ok)
        st.session_state[state_key] = True


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    cfg    = load_metadata()
    mqtt_h = get_mqtt_handler(id(cfg))
    plants = cfg.get("plants", [])

    qp     = dict(st.query_params)
    page   = str(qp.get("page", "")).strip() or "dashboard"

    all_assets  = [a for p in plants for a in p.get("assets", [])]
    total_alarms = sum(_count_alarms(a, mqtt_h) for a in all_assets)
    now_str      = datetime.utcnow().strftime("%H:%M:%S UTC")
    connected    = mqtt_h.connected

    _process_ctrl_submissions(cfg, mqtt_h)

    if page in ("dashboard", "fleet", "map", "alarms"):
        if page == "dashboard":
            html = html_dashboard_page(cfg, mqtt_h, total_alarms, now_str)
        elif page == "fleet":
            html = html_fleet_page(cfg, mqtt_h, total_alarms, now_str)
        elif page == "map":
            html = html_map_page(cfg, mqtt_h, total_alarms, now_str)
        else:
            html = html_alarms_page(cfg, mqtt_h, total_alarms, now_str)
        st.markdown(html, unsafe_allow_html=True)
        audit_log.info("View: page=%s", page)
        time.sleep(2)
        st.rerun()
        return

    if page == "device":
        sel_plant_id = str(qp.get("plant", "")).strip()
        sel_asset_id = str(qp.get("asset", "")).strip()
        sel_plant    = next((p for p in plants if p["id"] == sel_plant_id), plants[0] if plants else {})
        sel_assets   = sel_plant.get("assets", []) if sel_plant else []
        sel_asset    = next((a for a in sel_assets if a["id"] == sel_asset_id),
                            sel_assets[0] if sel_assets else {})
        if sel_plant and sel_asset:
            html = html_device_page(sel_plant, sel_asset, mqtt_h, cfg, total_alarms, now_str)
            st.markdown(html, unsafe_allow_html=True)
            audit_log.info("View: device=%s/%s", sel_plant_id, sel_asset_id)
            time.sleep(2)
            st.rerun()
            return

    html = html_dashboard_page(cfg, mqtt_h, total_alarms, now_str)
    st.markdown(html, unsafe_allow_html=True)
    time.sleep(2)
    st.rerun()


main()
