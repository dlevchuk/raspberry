#!/usr/bin/env python3
import os
import re
import sys
import time
import json
import math
import shutil
import signal
import threading
import subprocess
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

DEVICE = "/dev/video0"
PORT = int(os.environ.get("THERMAL_PORT", "8080"))
BOUNDARY = "frame"
DROP_FRAMES = int(os.environ.get("THERMAL_DROP_FRAMES", "20"))

CAPTURE_FPS = int(os.environ.get("THERMAL_CAPTURE_FPS", "30"))
MAX_STREAM_FPS = float(os.environ.get("THERMAL_MAX_FPS", str(CAPTURE_FPS)))
MIN_STREAM_FPS = float(os.environ.get("THERMAL_MIN_FPS", "3"))
QUALITY = os.environ.get("THERMAL_QUALITY", "3")
SCALE = os.environ.get("THERMAL_SCALE", "")

STALE_AFTER = float(os.environ.get("THERMAL_STALE_SEC", "3"))

REC_DIR = os.environ.get("THERMAL_REC_DIR", os.path.expanduser("~/thermal_recordings"))
STATS_FIFO = "/tmp/thermal_signalstats.fifo"
CONFIG_PATH = os.path.join(REC_DIR, "thermal_config.json")

COLORMAPS = {
    "gray": None,
    "blackhot": "negate",
    "ironbow": "pseudocolor=preset=turbo",
    "rainbow": "pseudocolor=preset=spectral",
}

DEFAULT_CONFIG = {
    "color_mode": os.environ.get("THERMAL_COLORMAP", "gray"),
    "temp_scale": os.environ.get("THERMAL_TEMP_SCALE", ""),
    "temp_offset": float(os.environ.get("THERMAL_TEMP_OFFSET", "0")),
    "alert_max_temp": float(os.environ.get("THERMAL_ALERT_MAX", "70.0")),
    "auto_cleanup_disk_pct": float(os.environ.get("THERMAL_CLEANUP_PCT", "85.0")),
}

config_lock = threading.Lock()
# Serializes disk writes only.  Do not use this lock to protect `config`.
config_file_lock = threading.Lock()
config = DEFAULT_CONFIG.copy()


def load_config():
    if not os.path.exists(CONFIG_PATH):
        return
    try:
        with open(CONFIG_PATH, "r") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("configuration is not an object")
        with config_lock:
            for k, v in data.items():
                if k in config:
                    config[k] = v
    except Exception as e:
        print(f"[Config] Failed to load config: {e}")


def save_config():
    """Save a consistent snapshot without holding config_lock during I/O."""
    try:
        os.makedirs(REC_DIR, exist_ok=True)
        # Serialize saves first, then copy: a slower earlier request cannot overwrite a
        # newer configuration snapshot.  config_lock is released before all disk I/O.
        with config_file_lock:
            with config_lock:
                data = config.copy()
            tmp_path = f"{CONFIG_PATH}.tmp.{os.getpid()}.{threading.get_ident()}"
            try:
                with open(tmp_path, "w") as f:
                    json.dump(data, f, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, CONFIG_PATH)
            finally:
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except OSError:
                    pass
        print(f"[Config] Saved config to {CONFIG_PATH}")
        return True
    except Exception as e:
        print(f"[Config] Failed to save config: {e}")
        return False


load_config()

START_TIME = time.time()
state_lock = threading.Lock()
color_mode = config["color_mode"] if config["color_mode"] in COLORMAPS else "gray"
current_proc = None
restart_count = 0
first_start = True
camera_enabled = True
camera_event = threading.Event()
camera_event.set()


def set_camera_state(enabled: bool):
    global camera_enabled, current_proc
    with state_lock:
        camera_enabled = enabled
        if enabled:
            camera_event.set()
        else:
            camera_event.clear()
            proc = current_proc
    if not enabled:
        stop_recording()
        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass
        with bus.cond:
            bus.cond.notify_all()
    return camera_enabled


def toggle_camera_state():
    with state_lock:
        enabled = not camera_enabled
    return set_camera_state(enabled)


def is_camera_enabled():
    with state_lock:
        return camera_enabled


def format_uptime(seconds):
    sec = int(seconds)
    days, sec = divmod(sec, 86400)
    hours, sec = divmod(sec, 3600)
    minutes, sec = divmod(sec, 60)
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0 or days > 0:
        parts.append(f"{hours}h")
    if minutes > 0 or hours > 0 or days > 0:
        parts.append(f"{minutes}m")
    parts.append(f"{sec}s")
    return " ".join(parts)


def get_system_uptime():
    try:
        if os.path.exists("/proc/uptime"):
            with open("/proc/uptime", "r") as f:
                uptime_sec = float(f.readline().split()[0])
                return format_uptime(uptime_sec)
    except Exception:
        pass
    try:
        out = subprocess.check_output(["uptime", "-p"], text=True, timeout=1).strip()
        if out.startswith("up "):
            return out[3:]
        return out
    except Exception:
        return format_uptime(time.time() - START_TIME)


def get_cpu_temp():
    try:
        if os.path.exists("/sys/class/thermal/thermal_zone0/temp"):
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                return round(float(f.read().strip()) / 1000.0, 1)
    except Exception:
        pass
    try:
        out = subprocess.check_output(["vcgencmd", "measure_temp"], text=True, timeout=1)
        m = re.search(r"temp=([\d.]+)", out)
        if m:
            return float(m.group(1))
    except Exception:
        pass
    return None


def get_mem_usage():
    try:
        mem = {}
        with open("/proc/meminfo", "r") as f:
            for line in f:
                parts = line.split(":")
                if len(parts) == 2:
                    key = parts[0].strip()
                    val = parts[1].strip().split()[0]
                    mem[key] = int(val)
        total = mem.get("MemTotal", 0)
        free = mem.get("MemAvailable", mem.get("MemFree", 0))
        used = total - free
        if total > 0:
            pct = round((used / total) * 100, 1)
            return {
                "used_mb": round(used / 1024, 1),
                "total_mb": round(total / 1024, 1),
                "percent": pct
            }
    except Exception:
        pass
    return None


def get_disk_usage(path="/"):
    try:
        target = path if os.path.exists(path) else "/"
        usage = shutil.disk_usage(target)
        total_gb = round(usage.total / (1024**3), 1)
        used_gb = round(usage.used / (1024**3), 1)
        pct = round((usage.used / usage.total) * 100, 1)
        return {
            "used_gb": used_gb,
            "total_gb": total_gb,
            "percent": pct
        }
    except Exception:
        pass
    return None


def get_load_avg():
    try:
        load = os.getloadavg()
        return [round(l, 2) for l in load]
    except Exception:
        return None


def cleanup_old_recordings():
    """Auto-deletes oldest .avi recordings if disk usage exceeds configured threshold."""
    with config_lock:
        try:
            threshold = float(config.get("auto_cleanup_disk_pct", 85.0))
        except (TypeError, ValueError):
            threshold = 85.0
    usage = get_disk_usage(REC_DIR)
    if not usage or usage["percent"] < threshold:
        return
    if not os.path.exists(REC_DIR):
        return
    with record_lock:
        active_path = record_state["path"] if record_state["active"] else None
    files = []
    for f in os.listdir(REC_DIR):
        if f.endswith(".avi"):
            p = os.path.join(REC_DIR, f)
            if os.path.abspath(p) == os.path.abspath(active_path or ""):
                continue
            try:
                files.append((p, os.path.getmtime(p)))
            except OSError:
                pass
    files.sort(key=lambda x: x[1])  # oldest first
    for filepath, _ in files:
        try:
            os.remove(filepath)
            print(f"[AutoCleanup] Deleted old recording: {filepath}")
        except OSError:
            pass
        usage = get_disk_usage(REC_DIR)
        if usage and usage["percent"] < threshold:
            break


def auto_cleanup_loop():
    while True:
        try:
            cleanup_old_recordings()
        except Exception as e:
            print(f"[AutoCleanup Error] {e}")
        time.sleep(300)


def build_vf_chain(mode):
    chain = [
        f"select='gte(n,{DROP_FRAMES})'",
        "setpts=N/FRAME_RATE/TB",
        f"signalstats,metadata=mode=print:file={STATS_FIFO}",
        "format=gray",
    ]
    if SCALE:
        chain.append(f"scale={SCALE}")
    extra = COLORMAPS.get(mode)
    if extra == "negate":
        chain.append("negate")
    elif extra:
        chain.append(extra)
    return chain


def build_ffmpeg_cmd(mode):
    return [
        "ffmpeg", "-loglevel", "error",
        "-f", "v4l2", "-input_format", "yuyv422",
        "-video_size", "640x512", "-framerate", "30",
        "-i", DEVICE,
        "-vf", ",".join(build_vf_chain(mode)),
        "-r", str(CAPTURE_FPS),
        "-f", "mjpeg", "-q:v", QUALITY,
        "pipe:1",
    ]


PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Thermal cam</title>
<style>
  body{margin:0;background:#0d0d0d;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;color:#ccc;padding:16px}
  .grid{display:grid;grid-template-columns:1fr;gap:16px;max-width:1400px;margin:0 auto}
  @media(min-width:900px){.grid{grid-template-columns:1fr 1fr}}
  .col{display:flex;flex-direction:column;gap:16px}
  .card{background:#1a1a1a;border:1px solid #282828;border-radius:10px;padding:14px;box-shadow:0 4px 12px rgba(0,0,0,0.3)}
  .card h3{margin:0 0 10px 0;font-size:13px;color:#888;text-transform:uppercase;letter-spacing:.05em}
  .card-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}
  .card-header h3{margin:0}

  img#stream{width:100%;max-width:800px;height:auto;display:block;margin:0 auto;image-rendering:pixelated;border-radius:6px;transition:opacity .3s}
  .bar{display:flex;flex-wrap:wrap;gap:6px;justify-content:center;margin-bottom:10px}
  button,.btn{padding:8px 16px;font-size:13px;font-weight:500;cursor:pointer;border-radius:6px;border:1px solid #333;background:#222;color:#ccc;transition:all .15s;text-decoration:none;display:inline-flex;align-items:center;gap:4px}
  button:hover,.btn:hover{background:#2a2a2a;border-color:#444}
  button.active{outline:2px solid #4caf50;background:#2a3a2b;color:#fff}
  button.rec{background:#c62828;color:#fff;border-color:#c62828}
  button.cam-on{background:#2e7d32;color:#fff;border-color:#2e7d32}
  button.cam-off{background:#d32f2f;color:#fff;border-color:#d32f2f}
  .btn-danger{background:#b71c1c;color:#fff;border-color:#b71c1c;padding:4px 8px;font-size:11px}
  .btn-sm{padding:4px 8px;font-size:11px}

  /* Alert Banner */
  .alert-banner{display:none;background:rgba(244,67,54,.2);border:1px solid #f44336;color:#ff8a80;padding:10px 14px;border-radius:8px;margin-bottom:12px;font-weight:600;font-size:13px;align-items:center;justify-content:space-between;animation:pulse 1s infinite alternate}
  @keyframes pulse{from{box-shadow:0 0 4px rgba(244,67,54,.4)}to{box-shadow:0 0 14px rgba(244,67,54,.9)}}

  /* Status badges */
  .status-badge{font-size:12px;font-weight:600;padding:4px 10px;border-radius:12px;display:inline-flex;align-items:center;gap:5px;letter-spacing:.03em}
  .status-badge.ok{background:rgba(76,175,80,.15);color:#4caf50;border:1px solid rgba(76,175,80,.3)}
  .status-badge.bad{background:rgba(244,67,54,.15);color:#f44336;border:1px solid rgba(244,67,54,.3)}
  .status-badge.warn{background:rgba(255,179,0,.15);color:#ffb300;border:1px solid rgba(255,179,0,.3)}

  .stats-grid{display:grid;grid-template-columns:repeat(auto-fit, minmax(120px, 1fr));gap:10px}
  .stat-box{background:#222;border:1px solid #2e2e2e;border-radius:8px;padding:10px;display:flex;flex-direction:column;gap:3px}
  .stat-label{font-size:11px;color:#888;text-transform:uppercase;letter-spacing:.05em}
  .stat-val{font-size:14px;font-weight:600;color:#eee;font-family:ui-monospace,SFMono-Regular,Consolas,monospace}
  .stat-sub{font-size:11px;color:#aaa}

  .temp-range{display:flex;gap:8px;margin-bottom:12px}
  .temp-chip{flex:1;background:#222;border:1px solid #2e2e2e;border-radius:8px;padding:8px 10px;text-align:center}
  .temp-chip .stat-label{display:block;margin-bottom:2px}
  .temp-min{color:#4fc3f7}
  .temp-avg{color:#ffb74d}
  .temp-max{color:#ff5252}

  .progress-bar-bg{background:#333;height:5px;border-radius:3px;overflow:hidden;margin-top:5px}
  .progress-bar-fill{height:100%;background:#4caf50;transition:width .3s}

  .warn-text{color:#ffb300}
  #weather-wrap iframe{width:100%;height:450px;border:0;border-radius:6px}
  #alerts-wrap iframe{width:100%;height:350px;border:0;border-radius:6px}

  /* Form & Table styles */
  .form-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
  .form-group{display:flex;flex-direction:column;gap:4px}
  .form-group label{font-size:11px;color:#aaa;text-transform:uppercase}
  .form-group input{background:#222;border:1px solid #333;border-radius:6px;padding:6px 10px;color:#fff;font-size:13px;outline:none}
  .form-group input:focus{border-color:#4caf50}

  .table-wrap{max-height:240px;overflow-y:auto}
  table.rec-table{width:100%;border-collapse:collapse;font-size:12px;text-align:left}
  table.rec-table th, table.rec-table td{padding:8px;border-bottom:1px solid #2a2a2a}
  table.rec-table th{color:#888;font-weight:600;text-transform:uppercase;font-size:10px;position:sticky;top:0;background:#1a1a1a}
</style></head>
<body>
  <div class="grid">

    <!-- Стовпчик 1: Stream + Галерея + Status + Калібрування -->
    <div class="col">
      <div class="card">
        <h3>Thermal Stream</h3>
        <div id="alertBanner" class="alert-banner">
          <span>⚠️ ПОПЕРЕДЖЕННЯ: Перевищено поріг температури!</span>
          <button class="btn-sm" onclick="muteAudioAlert()">🔕 Mute</button>
        </div>
        <div class="bar">
          <button id="camBtn" class="cam-on" onclick="toggleCamera()">⏸ Stop Camera</button>
          <button onclick="snapshot()">📷 Snapshot</button>
          <button onclick="toggleFullscreen()">⛶ Fullscreen</button>
          <button id="recBtn" onclick="toggleRecord()">⏺ Record</button>
        </div>
        <div class="bar" id="modes">
          <button data-mode="gray" onclick="setMode('gray')">Gray</button>
          <button data-mode="blackhot" onclick="setMode('blackhot')">Blackhot</button>
          <button data-mode="ironbow" onclick="setMode('ironbow')">Ironbow</button>
          <button data-mode="rainbow" onclick="setMode('rainbow')">Rainbow</button>
        </div>
        <img id="stream" src="/stream">
      </div>

      <div class="card">
        <div class="card-header">
          <h3>Галерея Записів</h3>
          <button class="btn-sm" onclick="loadRecordings()">🔄 Оновити</button>
        </div>
        <div class="table-wrap">
          <table class="rec-table">
            <thead>
              <tr>
                <th>Файл</th>
                <th>Розмір</th>
                <th>Час</th>
                <th>Дії</th>
              </tr>
            </thead>
            <tbody id="recTableBody">
              <tr><td colspan="4" style="text-align:center;color:#666">Завантаження...</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3>Camera Status</h3>
          <div id="status-badge" class="status-badge ok">● live</div>
        </div>

        <div class="temp-range">
          <div class="temp-chip">
            <span class="stat-label">Min Temp</span>
            <span id="temp-min" class="stat-val temp-min">-</span>
          </div>
          <div class="temp-chip">
            <span class="stat-label">Avg Temp</span>
            <span id="temp-avg" class="stat-val temp-avg">-</span>
          </div>
          <div class="temp-chip">
            <span class="stat-label">Max Temp</span>
            <span id="temp-max" class="stat-val temp-max">-</span>
          </div>
        </div>

        <div class="stats-grid">
          <div class="stat-box">
            <span class="stat-label">Capture FPS</span>
            <span id="cam-fps" class="stat-val">-</span>
          </div>
          <div class="stat-box">
            <span class="stat-label">Stream FPS</span>
            <span id="cam-stream-fps" class="stat-val">-</span>
          </div>
          <div class="stat-box">
            <span class="stat-label">Frames</span>
            <span id="cam-frames" class="stat-val">-</span>
          </div>
          <div class="stat-box">
            <span class="stat-label">Time</span>
            <span id="clock" class="stat-val" style="font-size:12px">-</span>
          </div>
        </div>
        <div id="cam-extra" style="margin-top:10px;font-size:12px;color:#aaa;display:flex;gap:12px"></div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3>Калібрування та Пороги Тривоги</h3>
          <button class="btn-sm" onclick="saveSettings()">💾 Зберегти</button>
        </div>
        <form id="settingsForm" onsubmit="event.preventDefault(); saveSettings();">
          <div class="form-grid">
            <div class="form-group">
              <label>Scale (Множник)</label>
              <input type="text" id="cfg-scale" placeholder="напр. 0.25">
            </div>
            <div class="form-group">
              <label>Offset (Зсув °C)</label>
              <input type="number" step="0.1" id="cfg-offset" placeholder="0">
            </div>
            <div class="form-group">
              <label>Alert Max Temp (°C/Y)</label>
              <input type="number" step="0.5" id="cfg-alert-max" placeholder="70">
            </div>
            <div class="form-group">
              <label>Auto-cleanup Disk %</label>
              <input type="number" step="1" id="cfg-cleanup-pct" placeholder="85">
            </div>
          </div>
        </form>
      </div>
    </div>

    <!-- Стовпчик 2: Host System + Тривога + Погода -->
    <div class="col">
      <div class="card">
        <div class="card-header">
          <h3>Host System</h3>
          <span id="sys-uptime-badge" style="font-size:12px;color:#888;font-family:monospace">up: -</span>
        </div>
        <div class="stats-grid">
          <div class="stat-box">
            <span class="stat-label">CPU Temp</span>
            <span id="sys-cpu-temp" class="stat-val">-</span>
          </div>
          <div class="stat-box">
            <span class="stat-label">Load Avg</span>
            <span id="sys-load" class="stat-val" style="font-size:12px">-</span>
          </div>
          <div class="stat-box" style="grid-column: span 2">
            <div style="display:flex;justify-content:space-between">
              <span class="stat-label">RAM</span>
              <span id="sys-ram-pct" class="stat-sub">-</span>
            </div>
            <span id="sys-ram" class="stat-val" style="font-size:13px">-</span>
            <div class="progress-bar-bg"><div id="sys-ram-bar" class="progress-bar-fill" style="width:0%"></div></div>
          </div>
          <div class="stat-box" style="grid-column: span 2">
            <div style="display:flex;justify-content:space-between">
              <span class="stat-label">Disk (/)</span>
              <span id="sys-disk-pct" class="stat-sub">-</span>
            </div>
            <span id="sys-disk" class="stat-val" style="font-size:13px">-</span>
            <div class="progress-bar-bg"><div id="sys-disk-bar" class="progress-bar-fill" style="width:0%"></div></div>
          </div>
        </div>
        <div style="margin-top:12px;display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap">
          <button class="btn-sm" onclick="sysReboot()">🔄 Перезавантажити</button>
          <button class="btn-sm btn-danger" onclick="sysShutdown()">⚡ Вимкнути Pi</button>
        </div>
      </div>

      <div class="card" id="alerts-wrap">
        <h3>Повітряна тривога</h3>
        <iframe src="https://alerts.in.ua/?embed"
                title="Мапа повітряних тривог" frameborder="0"
                loading="lazy"></iframe>
      </div>

      <div class="card">
        <h3>Авіапогода — Windy (Славутич)</h3>
        <div id="weather-wrap">
          <iframe src="https://embed.windy.com/embed2.html?lat=51.520&lon=30.744&detailLat=51.520&detailLon=30.744&width=800&height=500&zoom=8&level=surface&overlay=wind&product=ecmwf&menu=&message=true&marker=true&calendar=now&pressure=true&type=map&location=coordinates&detail=true&metricWind=default&metricTemp=default&radarRange=-1"
                  loading="lazy" title="Авіапогода Windy"></iframe>
        </div>
      </div>
    </div>

  </div>
<script>
let recording = false;
let cameraEnabled = true;
let audioMuted = false;
let audioCtx = null;
let healthRequestInFlight = false;

function playAlertSound(){
  if(audioMuted) return;
  try{
    if(!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    if(audioCtx.state === 'suspended') audioCtx.resume();
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.type = 'sawtooth';
    osc.frequency.setValueAtTime(880, audioCtx.currentTime);
    gain.gain.setValueAtTime(0.1, audioCtx.currentTime);
    osc.connect(gain);
    gain.connect(audioCtx.destination);
    osc.start();
    osc.stop(audioCtx.currentTime + 0.2);
  }catch(e){}
}
function muteAudioAlert(){ audioMuted = true; }

async function toggleCamera(){
  const endpoint = cameraEnabled ? '/camera/off' : '/camera/on';
  try{
    const r = await fetch(endpoint);
    const j = await r.json();
    cameraEnabled = j.camera_enabled;
    updateCamBtn();
    const img = document.getElementById('stream');
    if(cameraEnabled){
      img.src = '/stream?_=' + Date.now();
      img.style.opacity = '1';
    }else{
      img.style.opacity = '0.3';
    }
  }catch(e){}
}
function updateCamBtn(){
  const b = document.getElementById('camBtn');
  if(!b) return;
  if(cameraEnabled){
    b.className = 'cam-on';
    b.textContent = '⏸ Stop Camera';
  }else{
    b.className = 'cam-off';
    b.textContent = '▶ Start Camera';
  }
}

function snapshot(){
  const a=document.createElement('a');
  a.href='/snapshot?_=' + Date.now();
  a.download='thermal_' + Date.now() + '.jpg';
  document.body.appendChild(a); a.click(); a.remove();
}
function toggleFullscreen(){
  const el=document.getElementById('stream');
  if(!document.fullscreenElement){el.requestFullscreen();}
  else{document.exitFullscreen();}
}
function markActive(mode){
  document.querySelectorAll('#modes button').forEach(b=>{
    b.classList.toggle('active', b.dataset.mode === mode);
  });
}
async function setMode(mode){
  try{
    const r = await fetch('/mode?name=' + mode);
    const j = await r.json();
    markActive(j.mode);
    const img = document.getElementById('stream');
    img.src = '/stream?_=' + Date.now();
  }catch(e){}
}
async function toggleRecord(){
  const endpoint = recording ? '/record/stop' : '/record/start';
  try{
    const r = await fetch(endpoint);
    const j = await r.json();
    recording = j.active;
    updateRecBtn();
    loadRecordings();
  }catch(e){}
}
function updateRecBtn(){
  const b = document.getElementById('recBtn');
  b.classList.toggle('rec', recording);
  b.textContent = recording ? '⏹ Stop recording' : '⏺ Record';
}
function pad(n){return n.toString().padStart(2,'0');}
function tickClock(){
  const d = new Date();
  const s = `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  document.getElementById('clock').textContent = s;
}
setInterval(tickClock, 1000);
tickClock();

async function loadSettings(){
  try{
    const r = await fetch('/settings');
    const c = await r.json();
    document.getElementById('cfg-scale').value = c.temp_scale || '';
    document.getElementById('cfg-offset').value = c.temp_offset ?? 0;
    document.getElementById('cfg-alert-max').value = c.alert_max_temp ?? 70;
    document.getElementById('cfg-cleanup-pct').value = c.auto_cleanup_disk_pct ?? 85;
  }catch(e){}
}
async function saveSettings(){
  const scale = document.getElementById('cfg-scale').value;
  const offset = document.getElementById('cfg-offset').value;
  const alertMax = document.getElementById('cfg-alert-max').value;
  const cleanupPct = document.getElementById('cfg-cleanup-pct').value;
  try{
    const url = `/settings/update?scale=${encodeURIComponent(scale)}&offset=${encodeURIComponent(offset)}&alert_max=${encodeURIComponent(alertMax)}&cleanup_pct=${encodeURIComponent(cleanupPct)}`;
    const r = await fetch(url);
    const j = await r.json();
    if(j.ok) alert('Налаштування збережено!');
  }catch(e){ alert('Помилка збереження'); }
}

async function loadRecordings(){
  try{
    const r = await fetch('/recordings');
    const list = await r.json();
    const tbody = document.getElementById('recTableBody');
    if(!list || list.length === 0){
      tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:#666">Немає записів</td></tr>';
      return;
    }
    tbody.innerHTML = list.map(item => `
      <tr>
        <td style="font-family:monospace">${item.name}</td>
        <td>${item.size_mb} MB</td>
        <td style="color:#aaa">${item.mtime}</td>
        <td>
          <a class="btn btn-sm" href="/recordings/download?name=${encodeURIComponent(item.name)}">⬇</a>
          <button class="btn-danger btn-sm" onclick="deleteRec('${item.name}')">🗑</button>
        </td>
      </tr>
    `).join('');
  }catch(e){}
}
async function deleteRec(name){
  if(!confirm(`Видалити ${name}?`)) return;
  try{
    await fetch(`/recordings/delete?name=${encodeURIComponent(name)}`);
    loadRecordings();
  }catch(e){}
}

async function sysReboot(){
  if(!confirm("Перезавантажити Raspberry Pi?")) return;
  try{
    await fetch('/sys/reboot');
    alert("Raspberry Pi перезавантажується...");
  }catch(e){}
}
async function sysShutdown(){
  if(!confirm("Вимкнути Raspberry Pi?\\n\\nУвага: для наступного увімкнення знадобиться фізично перепідключити живлення.")) return;  try{
    await fetch('/sys/shutdown');
    alert("Raspberry Pi вимикається...");
  }catch(e){}
}

async function pollHealth(){
  if(healthRequestInFlight) return;
  healthRequestInFlight = true;
  try{
    const r = await fetch('/health');
    if(!r.ok) throw new Error('HTTP ' + r.status);
    const h = await r.json();
    if(h.mode) markActive(h.mode);
    recording = h.recording ? h.recording.active : false;
    updateRecBtn();
    if(h.camera_enabled !== undefined){
      cameraEnabled = h.camera_enabled;
      updateCamBtn();
    }
    const badge = document.getElementById('status-badge');
    if(badge){
      if(!h.camera_enabled){
        badge.className = 'status-badge warn';
        badge.textContent = '⏸ PAUSED';
      }else if(h.stalled){
        badge.className = 'status-badge bad';
        badge.textContent = '⚠ STALLED';
      }else{
        badge.className = 'status-badge ok';
        badge.textContent = '● LIVE';
      }
    }

    if(document.getElementById('cam-fps')) document.getElementById('cam-fps').textContent = h.camera_enabled ? (h.fps ?? '0') : '0';
    if(document.getElementById('cam-stream-fps')) document.getElementById('cam-stream-fps').textContent = h.camera_enabled ? (h.stream_fps ?? '0') : '0';
    if(document.getElementById('cam-frames')) document.getElementById('cam-frames').textContent = h.frame_count ?? '0';

    let extraTxt = `Restarts: ${h.restarts ?? 0}`;
    if(h.age_sec != null && h.camera_enabled) extraTxt += ` • Latency: ${h.age_sec}s`;
    if(h.recording && h.recording.active) extraTxt += ` • <span class="warn-text">⏺ REC ${h.recording.frames}f</span>`;
    if(document.getElementById('cam-extra')) document.getElementById('cam-extra').innerHTML = extraTxt;

    const t = h.temp || {};
    const unit = t.calibrated ? '°C' : 'Y';
    if(document.getElementById('temp-min')) document.getElementById('temp-min').textContent = t.min != null ? `${t.min}${unit}` : '-';
    if(document.getElementById('temp-avg')) document.getElementById('temp-avg').textContent = t.avg != null ? `${t.avg}${unit}` : '-';
    if(document.getElementById('temp-max')) document.getElementById('temp-max').textContent = t.max != null ? `${t.max}${unit}` : '-';

    // Thermal alert trigger
    const alertBanner = document.getElementById('alertBanner');
    if(alertBanner){
      if(h.alert){
        alertBanner.style.display = 'flex';
        playAlertSound();
      }else{
        alertBanner.style.display = 'none';
      }
    }

    if (h.sys_stats) {
      const s = h.sys_stats;
      const cpuEl = document.getElementById('sys-cpu-temp');
      if(cpuEl){
        if(s.cpu_temp != null){
          cpuEl.textContent = `${s.cpu_temp} °C`;
          cpuEl.style.color = s.cpu_temp > 70 ? '#f44336' : (s.cpu_temp > 60 ? '#ffb300' : '#4caf50');
        } else {
          cpuEl.textContent = 'N/A';
        }
      }

      if(document.getElementById('sys-load')) document.getElementById('sys-load').textContent = s.load ? s.load.join(', ') : 'N/A';

      if(s.memory){
        if(document.getElementById('sys-ram')) document.getElementById('sys-ram').textContent = `${s.memory.used_mb} / ${s.memory.total_mb} MB`;
        if(document.getElementById('sys-ram-pct')) document.getElementById('sys-ram-pct').textContent = `${s.memory.percent}%`;
        const ramBar = document.getElementById('sys-ram-bar');
        if(ramBar){
          ramBar.style.width = `${s.memory.percent}%`;
          ramBar.style.background = s.memory.percent > 85 ? '#f44336' : '#4caf50';
        }
      }

      if(s.disk){
        if(document.getElementById('sys-disk')) document.getElementById('sys-disk').textContent = `${s.disk.used_gb} / ${s.disk.total_gb} GB`;
        if(document.getElementById('sys-disk-pct')) document.getElementById('sys-disk-pct').textContent = `${s.disk.percent}%`;
        const diskBar = document.getElementById('sys-disk-bar');
        if(diskBar){
          diskBar.style.width = `${s.disk.percent}%`;
          diskBar.style.background = s.disk.percent > 85 ? '#f44336' : '#4caf50';
        }
      }

      if(document.getElementById('sys-uptime-badge')) document.getElementById('sys-uptime-badge').textContent = `up: ${s.uptime || '-'}`;
    }
  }catch(e){
    const badge = document.getElementById('status-badge');
    if(badge){
      badge.className = 'status-badge bad';
      badge.textContent = 'NO CONNECTION';
    }
  } finally {
    healthRequestInFlight = false;
  }
}
setInterval(pollHealth, 1000);
pollHealth();
loadSettings();
loadRecordings();
</script>
</body></html>"""


class FrameBus:
    def __init__(self):
        self.frame = None
        self.cond = threading.Condition()
        self.frame_count = 0
        self.sequence = 0
        self.last_ts = 0.0
        self._fps_window = []

    def set(self, jpg):
        with self.cond:
            now = time.time()
            self.frame = jpg
            self.frame_count += 1
            self.sequence += 1
            self.last_ts = now
            self._fps_window.append(now)
            cutoff = now - 5
            self._fps_window = [t for t in self._fps_window if t >= cutoff]
            self.cond.notify_all()

    def get_next(self, last_sequence, timeout=1.0):
        """Wait for a frame newer than last_sequence, never replaying a stale one."""
        with self.cond:
            self.cond.wait_for(lambda: self.sequence != last_sequence, timeout=timeout)
            return self.frame, self.sequence

    def wake_all(self):
        with self.cond:
            self.cond.notify_all()

    def latest(self):
        with self.cond:
            return self.frame

    def stats(self, stream_fps=0.0):
        with self.cond:
            now = time.time()
            age = now - self.last_ts if self.last_ts else None
            fps = round(len(self._fps_window) / 5, 1) if self._fps_window else 0.0
            return {
                "frame_count": self.frame_count,
                "fps": fps if is_camera_enabled() else 0.0,
                "stream_fps": round(stream_fps, 1) if is_camera_enabled() else 0.0,
                "age_sec": round(age, 1) if age is not None else None,
                "stalled": (age is None or age > STALE_AFTER) if is_camera_enabled() else False,
                "mode": color_mode,
                "camera_enabled": is_camera_enabled(),
            }


bus = FrameBus()
last_stream_fps = 0.0

temp_lock = threading.Lock()
temp_data = {"y_min": None, "y_max": None, "y_avg": None, "updated": 0.0}

_re_min = re.compile(r"lavfi\.signalstats\.YMIN=([\d.]+)")
_re_max = re.compile(r"lavfi\.signalstats\.YMAX=([\d.]+)")
_re_avg = re.compile(r"lavfi\.signalstats\.YAVG=([\d.]+)")


def stats_fifo_reader():
    if os.path.exists(STATS_FIFO):
        try:
            os.remove(STATS_FIFO)
        except OSError:
            pass
    try:
        os.mkfifo(STATS_FIFO)
    except FileExistsError:
        pass
    except OSError as e:
        print(f"[Stats] Cannot create FIFO: {e}")
        return
    while True:
        try:
            with open(STATS_FIFO, "r") as f:
                for line in f:
                    m = _re_min.search(line)
                    if m:
                        with temp_lock:
                            temp_data["y_min"] = float(m.group(1))
                            temp_data["updated"] = time.time()
                        continue
                    m = _re_max.search(line)
                    if m:
                        with temp_lock:
                            temp_data["y_max"] = float(m.group(1))
                            temp_data["updated"] = time.time()
                        continue
                    m = _re_avg.search(line)
                    if m:
                        with temp_lock:
                            temp_data["y_avg"] = float(m.group(1))
                            temp_data["updated"] = time.time()
        except Exception:
            time.sleep(0.5)


def get_temp_stats():
    with temp_lock:
        y_min, y_max, y_avg = temp_data["y_min"], temp_data["y_max"], temp_data["y_avg"]
    with config_lock:
        scale_str = config.get("temp_scale", "")
        try:
            offset = float(config.get("temp_offset", 0.0))
        except (TypeError, ValueError):
            offset = 0.0
    if scale_str:
        try:
            scale = float(scale_str)
            conv = lambda y: round(y * scale + offset, 1) if y is not None else None
            return {"calibrated": True, "min": conv(y_min), "avg": conv(y_avg), "max": conv(y_max)}
        except ValueError:
            pass
    r = lambda y: round(y, 1) if y is not None else None
    return {"calibrated": False, "min": r(y_min), "avg": r(y_avg), "max": r(y_max)}


def ffmpeg_reader():
    global current_proc, restart_count, first_start
    while True:
        camera_event.wait()
        with state_lock:
            if not camera_enabled:
                continue
            mode = color_mode
            cmd = build_ffmpeg_cmd(mode)
            if not first_start:
                restart_count += 1
            first_start = False
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
        except OSError as e:
            print(f"[Camera] Cannot start ffmpeg: {e}")
            time.sleep(1)
            continue
        with state_lock:
            if camera_enabled:
                current_proc = proc
            else:
                proc.terminate()
                continue
        buf = b""
        while True:
            with state_lock:
                if not camera_enabled:
                    break
            chunk = proc.stdout.read(4096)
            if not chunk:
                break
            buf += chunk

            while True:
                start = buf.find(b"\xff\xd8")
                if start == -1:
                    if len(buf) > 65536:
                        buf = buf[-4096:]
                    break
                end = buf.find(b"\xff\xd9", start)
                if end == -1:
                    if len(buf) > 1048576:
                        buf = buf[start:]
                    break
                jpg = buf[start:end + 2]
                buf = buf[end + 2:]
                bus.set(jpg)

        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        with state_lock:
            if current_proc is proc:
                current_proc = None
        time.sleep(0.5)


class AdaptiveRate:
    def __init__(self, max_fps, min_fps):
        self.max_fps = max_fps
        self.min_fps = min_fps
        self.cur_fps = max_fps
        self.good_streak = 0

    def interval(self):
        return 1.0 / self.cur_fps

    def report(self, write_time):
        target = self.interval()
        if write_time > target * 1.5:
            self.cur_fps = max(self.min_fps, self.cur_fps / 1.5)
            self.good_streak = 0
        else:
            self.good_streak += 1
            if self.good_streak >= 10:
                self.cur_fps = min(self.max_fps, self.cur_fps * 1.2)
                self.good_streak = 0


record_lock = threading.Lock()
record_state = {"active": False, "proc": None, "path": None, "frames": 0, "started": None}


def recording_status():
    with record_lock:
        return recording_status_unlocked()


def recording_status_unlocked():
    return {k: v for k, v in record_state.items() if k != "proc"}


def record_feeder():
    sequence = 0
    while True:
        with record_lock:
            if not record_state["active"]:
                return
            proc = record_state["proc"]
        jpg, sequence = bus.get_next(sequence, timeout=1.0)
        if jpg is None:
            continue
        # Never hold record_lock while a slow/broken ffmpeg pipe is written.
        try:
            proc.stdin.write(jpg)
        except (BrokenPipeError, OSError, ValueError):
            with record_lock:
                if record_state["proc"] is proc:
                    record_state["active"] = False
            return
        with record_lock:
            if not record_state["active"] or record_state["proc"] is not proc:
                return
            record_state["frames"] += 1


def start_recording():
    cleanup_old_recordings()
    with record_lock:
        if record_state["active"]:
            return recording_status_unlocked()
        try:
            os.makedirs(REC_DIR, exist_ok=True)
            fname = datetime.now().strftime("thermal_%Y%m%d_%H%M%S.avi")
            path = os.path.join(REC_DIR, fname)
            proc = subprocess.Popen(
                ["ffmpeg", "-y", "-loglevel", "error",
                 "-f", "mjpeg", "-r", str(CAPTURE_FPS), "-i", "pipe:0",
                 "-c", "copy", path],
                stdin=subprocess.PIPE, stderr=subprocess.DEVNULL,
            )
        except OSError as e:
            return {"active": False, "path": None, "frames": 0, "started": None, "error": str(e)}
        record_state.update(active=True, proc=proc, path=path, frames=0, started=time.time())
    threading.Thread(target=record_feeder, daemon=True).start()
    return recording_status()


def stop_recording():
    with record_lock:
        if not record_state["active"]:
            return recording_status_unlocked()
        record_state["active"] = False
        proc = record_state["proc"]
    if proc is not None:
        try:
            proc.stdin.close()
        except OSError:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
    with record_lock:
        result = recording_status_unlocked()
        record_state["proc"] = None
    return result


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        global last_stream_fps, color_mode, current_proc
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/":
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/mode":
            name = qs.get("name", [""])[0]
            if name not in COLORMAPS:
                self._json({"error": "unknown mode"}, 400)
                return
            with state_lock:
                color_mode = name
                proc = current_proc
            with config_lock:
                config["color_mode"] = name
            saved = save_config()
            if proc is not None:
                proc.terminate()
            self._json({"ok": saved, "mode": name, "saved": saved}, 200 if saved else 500)
            return

        if path == "/settings":
            with config_lock:
                settings = config.copy()
            self._json(settings)
            return

        if path == "/settings/update":
            with config_lock:
                if "scale" in qs:
                    config["temp_scale"] = qs["scale"][0]
                if "offset" in qs:
                    try:
                        value = float(qs["offset"][0])
                        if math.isfinite(value):
                            config["temp_offset"] = value
                    except ValueError:
                        pass
                if "alert_max" in qs:
                    try:
                        value = float(qs["alert_max"][0])
                        if math.isfinite(value):
                            config["alert_max_temp"] = value
                    except ValueError:
                        pass
                if "cleanup_pct" in qs:
                    try:
                        value = float(qs["cleanup_pct"][0])
                        if math.isfinite(value):
                            config["auto_cleanup_disk_pct"] = min(100.0, max(0.0, value))
                    except ValueError:
                        pass
                settings = config.copy()
            # Important: save_config snapshots under its own lock; never call it while held.
            saved = save_config()
            self._json({"ok": saved, "config": settings, "saved": saved}, 200 if saved else 500)
            return

        if path == "/recordings":
            items = []
            if os.path.exists(REC_DIR):
                for f in sorted(os.listdir(REC_DIR), reverse=True):
                    if f.endswith(".avi"):
                        p = os.path.join(REC_DIR, f)
                        try:
                            st = os.stat(p)
                            items.append({
                                "name": f,
                                "size_mb": round(st.st_size / (1024 * 1024), 2),
                                "mtime": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                            })
                        except OSError:
                            pass
            self._json(items)
            return

        if path == "/recordings/download":
            name = os.path.basename(qs.get("name", [""])[0])
            filepath = os.path.join(REC_DIR, name)
            if not name or not os.path.exists(filepath):
                self._json({"error": "file not found"}, 404)
                return
            try:
                size = os.path.getsize(filepath)
                self.send_response(200)
                self.send_header("Content-Type", "video/x-msvideo")
                self.send_header("Content-Disposition", f'attachment; filename="{name}"')
                self.send_header("Content-Length", str(size))
                self.end_headers()
                with open(filepath, "rb") as f:
                    shutil.copyfileobj(f, self.wfile)
            except Exception as e:
                pass
            return

        if path == "/recordings/delete":
            name = os.path.basename(qs.get("name", [""])[0])
            filepath = os.path.join(REC_DIR, name)
            if not name or not os.path.exists(filepath):
                self._json({"error": "file not found"}, 404)
                return
            with record_lock:
                is_active_file = record_state["active"] and os.path.abspath(record_state["path"] or "") == os.path.abspath(filepath)
            if is_active_file:
                self._json({"error": "cannot delete an active recording"}, 409)
                return
            try:
                os.remove(filepath)
                self._json({"ok": True})
            except Exception as e:
                self._json({"error": str(e)}, 500)
            return

        if path == "/sys/reboot":
            self._json({"ok": True, "message": "Rebooting Raspberry Pi..."})
            def _do_reboot():
                time.sleep(1)
                subprocess.run(["sudo", "shutdown", "-r", "now"])
            threading.Thread(target=_do_reboot, daemon=True).start()
            return

        if path == "/sys/shutdown":
            self._json({"ok": True, "message": "Shutting down Raspberry Pi..."})
            def _do_shutdown():
                time.sleep(1)
                subprocess.run(["sudo", "shutdown", "-h", "now"])
            threading.Thread(target=_do_shutdown, daemon=True).start()
            return

        if path == "/camera/on":
            enabled = set_camera_state(True)
            self._json({"ok": True, "camera_enabled": enabled})
            return

        if path == "/camera/off":
            enabled = set_camera_state(False)
            self._json({"ok": True, "camera_enabled": enabled})
            return

        if path == "/camera/toggle":
            enabled = toggle_camera_state()
            self._json({"ok": True, "camera_enabled": enabled})
            return

        if path == "/record/start":
            st = start_recording()
            self._json({"active": st["active"], "path": st["path"], "frames": st["frames"]})
            return

        if path == "/record/stop":
            st = stop_recording()
            self._json({"active": st["active"], "path": st["path"], "frames": st["frames"]})
            return

        if path == "/health":
            rec = recording_status()
            with state_lock:
                restarts = restart_count
            body = bus.stats(last_stream_fps)
            body["restarts"] = restarts
            body["recording"] = rec
            temp_stats = get_temp_stats()
            body["temp"] = temp_stats

            # Thermal alert check
            with config_lock:
                try:
                    alert_thresh = float(config.get("alert_max_temp", 70.0))
                except (TypeError, ValueError):
                    alert_thresh = 70.0
            max_val = temp_stats.get("max")
            body["alert"] = (max_val is not None) and (max_val >= alert_thresh)

            uptime = get_system_uptime()
            body["uptime"] = uptime
            body["sys_stats"] = {
                "cpu_temp": get_cpu_temp(),
                "memory": get_mem_usage(),
                "disk": get_disk_usage("/"),
                "load": get_load_avg(),
                "uptime": uptime,
            }
            self._json(body)
            return

        if path == "/snapshot":
            if not is_camera_enabled():
                self._json({"error": "camera disabled"}, 503)
                return
            jpg = bus.latest()
            if jpg is None:
                self.send_response(503)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(jpg)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(jpg)
            return

        if path == "/stream":
            self.send_response(200)
            self.send_header("Age", "0")
            self.send_header("Cache-Control", "no-cache, private")
            self.send_header("Pragma", "no-cache")
            self.send_header("Content-Type", f"multipart/x-mixed-replace; boundary={BOUNDARY}")
            self.end_headers()
            rate = AdaptiveRate(MAX_STREAM_FPS, MIN_STREAM_FPS)
            last_sent = 0.0
            sequence = 0
            try:
                while True:
                    if not is_camera_enabled():
                        bus.get_next(sequence, timeout=1.0)
                        continue
                    jpg, sequence = bus.get_next(sequence, timeout=1.0)
                    if jpg is None:
                        continue
                    now = time.time()
                    if now - last_sent < rate.interval():
                        continue
                    t0 = time.time()
                    self.wfile.write(f"--{BOUNDARY}\r\n".encode())
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(f"Content-Length: {len(jpg)}\r\n\r\n".encode())
                    self.wfile.write(jpg + b"\r\n")
                    write_time = time.time() - t0
                    rate.report(write_time)
                    last_sent = time.time()
                    last_stream_fps = rate.cur_fps
            except (BrokenPipeError, ConnectionResetError):
                pass
            return

        self.send_response(404)
        self.end_headers()


class ThermalHTTPServer(ThreadingHTTPServer):
    # A stalled download/stream client must not keep the process alive at shutdown.
    daemon_threads = True


def shutdown_handler(signum, frame):
    print(f"\n[Shutdown] Received signal {signum}, stopping camera & server...")
    set_camera_state(False)
    stop_recording()
    if os.path.exists(STATS_FIFO):
        try:
            os.remove(STATS_FIFO)
        except OSError:
            pass
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    threading.Thread(target=stats_fifo_reader, daemon=True).start()
    threading.Thread(target=ffmpeg_reader, daemon=True).start()
    threading.Thread(target=auto_cleanup_loop, daemon=True).start()

    srv = ThermalHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"http://0.0.0.0:{PORT}/")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        shutdown_handler(signal.SIGINT, None)
