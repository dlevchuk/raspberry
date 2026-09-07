#!/usr/bin/env python3
import os
import re
import time
import json
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

# лінійна калібровка Y->температура: temp = Y*scale + offset. Якщо scale не задано - показуємо сирі Y.
TEMP_SCALE = os.environ.get("THERMAL_TEMP_SCALE", "")
TEMP_OFFSET = float(os.environ.get("THERMAL_TEMP_OFFSET", "0"))

REC_DIR = os.environ.get("THERMAL_REC_DIR", os.path.expanduser("~/thermal_recordings"))
STATS_FIFO = "/tmp/thermal_signalstats.fifo"

COLORMAPS = {
    "gray": None,
    "blackhot": "negate",
    "ironbow": "pseudocolor=preset=turbo",
    "rainbow": "pseudocolor=preset=spectral",
}
DEFAULT_MODE = os.environ.get("THERMAL_COLORMAP", "gray")

START_TIME = time.time()
state_lock = threading.Lock()
color_mode = DEFAULT_MODE if DEFAULT_MODE in COLORMAPS else "gray"
current_proc = None
restart_count = 0
first_start = True


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
        out = subprocess.check_output(["uptime", "-p"], text=True).strip()
        if out.startswith("up "):
            return out[3:]
        return out
    except Exception:
        return format_uptime(time.time() - START_TIME)


def build_vf_chain(mode):
    chain = [
        f"select=gte(n\\,{DROP_FRAMES})",
        "setpts=N/FRAME_RATE/TB",
        # signalstats рахує Y-статистику ДО format=gray/colormap - на сирому потоці
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
        "-video_size", "640x512", "-framerate", "30",  # capture - не чіпаємо V4L2
        "-i", DEVICE,
        "-vf", ",".join(build_vf_chain(mode)),
        "-r", str(CAPTURE_FPS),
        "-f", "mjpeg", "-q:v", QUALITY,
        "pipe:1",
    ]


PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Thermal cam</title>
<style>
  body{margin:0;background:#0d0d0d;font-family:sans-serif;color:#ccc;padding:16px}
  .grid{display:grid;grid-template-columns:1fr;gap:16px;max-width:1000px;margin:0 auto}
  @media(min-width:900px){.grid{grid-template-columns:1fr 1fr}}
  .card{background:#1a1a1a;border-radius:10px;padding:14px}
  .card h3{margin:0 0 10px 0;font-size:14px;color:#888;text-transform:uppercase;letter-spacing:.05em}
  .full{grid-column:1/-1}
  img#stream{width:100%;max-width:800px;height:auto;display:block;margin:0 auto;image-rendering:pixelated;border-radius:6px}
  .bar{display:flex;flex-wrap:wrap;gap:6px;justify-content:center;margin-bottom:10px}
  button{padding:8px 16px;font-size:14px;cursor:pointer;border-radius:4px;border:1px solid #333;background:#222;color:#ccc}
  button.active{outline:2px solid #4caf50}
  button.rec{background:#c62828;color:#fff;border-color:#c62828}
  #health, #clock, #temps{font-size:13px;line-height:1.6}
  .ok{color:#4caf50}
  .bad{color:#f44336}
  .warn{color:#ffb300}
  #weather-wrap iframe{width:100%;height:500px;border:0;border-radius:6px}
  #alerts-wrap iframe{width:100%;height:300px;border:0;border-radius:6px}
</style></head>
<body>
  <div class="grid">

    <div class="card full">
      <h3>Thermal Stream</h3>
      <div class="bar">
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
      <h3>Status</h3>
      <div id="clock">--:--:--</div>
      <div id="temps">temp: -</div>
      <div id="health">connecting...</div>
    </div>

    <div class="card" id="alerts-wrap">
      <h3>Повітряна тривога</h3>
      <iframe src="https://alerts.in.ua/?embed"
              title="Мапа повітряних тривог" frameborder="0"
              loading="lazy"></iframe>
    </div>

    <div class="card full">
      <h3>Авіапогода — Windy (Славутич)</h3>
      <div id="weather-wrap">
        <iframe src="https://embed.windy.com/embed2.html?lat=51.520&lon=30.744&detailLat=51.520&detailLon=30.744&width=800&height=500&zoom=8&level=surface&overlay=wind&product=ecmwf&menu=&message=true&marker=true&calendar=now&pressure=true&type=map&location=coordinates&detail=true&metricWind=default&metricTemp=default&radarRange=-1"
                loading="lazy" title="Авіапогода Windy"></iframe>
      </div>
    </div>

  </div>
<script>
let recording = false;

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
  const s = `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} `
          + `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  document.getElementById('clock').textContent = s;
}
setInterval(tickClock, 1000);
tickClock();

async function pollHealth(){
  try{
    const r = await fetch('/health');
    const h = await r.json();
    markActive(h.mode);
    recording = h.recording.active;
    updateRecBtn();
    const el = document.getElementById('health');
    const cls = h.stalled ? 'bad' : 'ok';
    let recTxt = h.recording.active
      ? `<span class="warn">⏺ REC ${h.recording.frames}f</span>` : '';
    el.innerHTML = `<span class="${cls}">${h.stalled ? '⚠ STALLED' : '● live'}</span><br>`
      + `uptime: ${h.uptime || '-'}<br>`
      + `frames: ${h.frame_count} | fps: ${h.fps}<br>`
      + `stream fps: ${h.stream_fps} | last: ${h.age_sec}s ago<br>`
      + `restarts: ${h.restarts} ${recTxt}`;
    const t = h.temp;
    const unit = t.calibrated ? '°C' : 'Y';
    document.getElementById('temps').textContent =
      `${unit} min: ${t.min ?? '-'} | avg: ${t.avg ?? '-'} | max: ${t.max ?? '-'}`;
  }catch(e){
    document.getElementById('health').innerHTML = '<span class="bad">no connection</span>';
  }
}
setInterval(pollHealth, 1000);
pollHealth();
</script>
</body></html>"""


class FrameBus:
    def __init__(self):
        self.frame = None
        self.cond = threading.Condition()
        self.frame_count = 0
        self.last_ts = 0.0
        self._fps_window = []

    def set(self, jpg):
        with self.cond:
            now = time.time()
            self.frame = jpg
            self.frame_count += 1
            self.last_ts = now
            self._fps_window.append(now)
            cutoff = now - 5
            self._fps_window = [t for t in self._fps_window if t >= cutoff]
            self.cond.notify_all()

    def get(self):
        with self.cond:
            self.cond.wait()
            return self.frame

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
                "fps": fps,
                "stream_fps": round(stream_fps, 1),
                "age_sec": round(age, 1) if age is not None else None,
                "stalled": (age is None) or (age > STALE_AFTER),
                "mode": color_mode,
            }


bus = FrameBus()
last_stream_fps = 0.0

# --- Y/temp статистика через FIFO (без запису на диск) ------------------
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
    os.mkfifo(STATS_FIFO)
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
        except OSError:
            time.sleep(0.5)
        # EOF (писач закрився, напр. ffmpeg рестартнув) - переоткриваємо і чекаємо наступного


def get_temp_stats():
    with temp_lock:
        y_min, y_max, y_avg = temp_data["y_min"], temp_data["y_max"], temp_data["y_avg"]
    if TEMP_SCALE:
        scale = float(TEMP_SCALE)
        conv = lambda y: round(y * scale + TEMP_OFFSET, 1) if y is not None else None
        return {"calibrated": True, "min": conv(y_min), "avg": conv(y_avg), "max": conv(y_max)}
    r = lambda y: round(y, 1) if y is not None else None
    return {"calibrated": False, "min": r(y_min), "avg": r(y_avg), "max": r(y_max)}


def ffmpeg_reader():
    global current_proc, restart_count, first_start
    while True:
        with state_lock:
            mode = color_mode
            cmd = build_ffmpeg_cmd(mode)
            if not first_start:
                restart_count += 1
            first_start = False
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=0)
        with state_lock:
            current_proc = proc
        buf = b""
        while True:
            chunk = proc.stdout.read(4096)
            if not chunk:
                break
            buf += chunk
            while True:
                start = buf.find(b"\xff\xd8")
                end = buf.find(b"\xff\xd9")
                if start == -1 or end == -1 or end < start:
                    break
                jpg = buf[start:end + 2]
                buf = buf[end + 2:]
                bus.set(jpg)
        proc.wait()
        with state_lock:
            if current_proc is proc:
                current_proc = None
        threading.Event().wait(0.5)


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


# --- Recording -----------------------------------------------------------
record_lock = threading.Lock()
record_state = {"active": False, "proc": None, "path": None, "frames": 0, "started": None}


def record_feeder():
    while True:
        with record_lock:
            if not record_state["active"]:
                return
            proc = record_state["proc"]
        jpg = bus.get()
        with record_lock:
            if not record_state["active"] or record_state["proc"] is not proc:
                return
            try:
                proc.stdin.write(jpg)
                record_state["frames"] += 1
            except (BrokenPipeError, OSError):
                record_state["active"] = False
                return


def start_recording():
    with record_lock:
        if record_state["active"]:
            return record_state.copy()
        os.makedirs(REC_DIR, exist_ok=True)
        fname = datetime.now().strftime("thermal_%Y%m%d_%H%M%S.avi")
        path = os.path.join(REC_DIR, fname)
        proc = subprocess.Popen(
            ["ffmpeg", "-y", "-loglevel", "error",
             "-f", "mjpeg", "-r", str(CAPTURE_FPS), "-i", "pipe:0",
             "-c", "copy", path],
            stdin=subprocess.PIPE,
        )
        record_state.update(active=True, proc=proc, path=path, frames=0, started=time.time())
    threading.Thread(target=record_feeder, daemon=True).start()
    return record_state.copy()


def stop_recording():
    with record_lock:
        if not record_state["active"]:
            return record_state.copy()
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
    with record_lock:
        result = record_state.copy()
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

        if path == "/":
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/mode":
            qs = parse_qs(parsed.query)
            name = qs.get("name", [""])[0]
            if name not in COLORMAPS:
                self._json({"error": "unknown mode"}, 400)
                return
            with state_lock:
                color_mode = name
                proc = current_proc
            if proc is not None:
                proc.terminate()
            self._json({"ok": True, "mode": name})
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
            with record_lock:
                rec = {
                    "active": record_state["active"],
                    "frames": record_state["frames"],
                    "path": record_state["path"],
                }
            with state_lock:
                restarts = restart_count
            body = bus.stats(last_stream_fps)
            body["restarts"] = restarts
            body["recording"] = rec
            body["temp"] = get_temp_stats()
            body["uptime"] = get_system_uptime()
            self._json(body)
            return

        if path == "/snapshot":
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
            try:
                while True:
                    jpg = bus.get()
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


if __name__ == "__main__":
    threading.Thread(target=stats_fifo_reader, daemon=True).start()
    threading.Thread(target=ffmpeg_reader, daemon=True).start()
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"http://0.0.0.0:{PORT}/")
    srv.serve_forever()
    