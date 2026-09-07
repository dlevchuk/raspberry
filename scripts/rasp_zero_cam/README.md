# Thermal Camera Web Interface (Raspberry Pi Zero)

`thermal_web.py` is a Python-based web server and video streamer designed for V4L2 thermal camera devices (e.g. `/dev/video0`). It uses `ffmpeg` to capture raw video, calculate Y-channel signal statistics (min, avg, max temperature/brightness), apply color palettes, stream MJPEG video via HTTP, record videos, and serve an interactive web dashboard.

## Features

- **MJPEG Streaming**: Dynamic rate streaming via `/stream` endpoint with adaptive FPS adjustment.
- **Color Palettes**: Supports `gray`, `blackhot`, `ironbow`, and `rainbow` colormaps.
- **Video Recording**: Start/stop recording MJPEG stream to `.avi` video files (`/record/start`, `/record/stop`).
- **Temperature & Health Monitoring**: `/health` JSON endpoint providing frame counters, streaming FPS, temperature/Y-stats, and restart tracking.
- **Built-in Web Dashboard**: Served directly from `/` with interactive controls, snapshots, full-screen mode, air raid alerts map, and weather radar widget.
- **Systemd Integration**: Runs automatically as a background service via `thermal-web.service`.
- **Automated CI/CD**: Automatic deployment and service reload via GitHub Actions over Tailscale.

---

## Requirements

- **OS**: Linux (Raspberry Pi OS / Debian)
- **Python**: Python 3.8+
- **System Dependencies**:
  - `ffmpeg` (compiled with `v4l2` support)
  - V4L2 thermal camera device at `/dev/video0`

---

## HTTP Endpoints

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/` | `GET` | HTML dashboard interface |
| `/stream` | `GET` | Live MJPEG video stream (`multipart/x-mixed-replace`) |
| `/snapshot` | `GET` | Single JPEG frame snapshot download |
| `/mode?name=<colormap>` | `GET` | Change color palette (`gray`, `blackhot`, `ironbow`, `rainbow`) |
| `/record/start` | `GET` | Start recording video to `THERMAL_REC_DIR` |
| `/record/stop` | `GET` | Stop video recording |
| `/health` | `GET` | JSON status, FPS stats, Y/temp metrics, recording state |

---

## Configuration (Environment Variables)

| Variable | Default | Description |
| :--- | :--- | :--- |
| `THERMAL_PORT` | `8080` | HTTP server port |
| `THERMAL_COLORMAP` | `gray` | Default color palette (`gray`, `blackhot`, `ironbow`, `rainbow`) |
| `THERMAL_REC_DIR` | `~/thermal_recordings` | Directory path to store video recordings |
| `THERMAL_DROP_FRAMES` | `20` | Initial frames to drop on stream restart |
| `THERMAL_CAPTURE_FPS` | `30` | V4L2 hardware capture framerate |
| `THERMAL_MAX_FPS` | `30` | Maximum streaming framerate |
| `THERMAL_MIN_FPS` | `3` | Minimum adaptive streaming framerate |
| `THERMAL_QUALITY` | `3` | MJPEG encoding quality (1-31, lower is better) |
| `THERMAL_SCALE` | `""` (none) | Optional scaling (e.g. `320:256`) |
| `THERMAL_STALE_SEC` | `3` | Seconds before marking stream as stalled |
| `THERMAL_TEMP_SCALE` | `""` (none) | Linear calibration multiplier for Y->Temperature conversion |
| `THERMAL_TEMP_OFFSET` | `0` | Linear calibration offset for Y->Temperature conversion |

---

## Running Manually

```bash
python3 thermal_web.py
```

Or with custom settings:

```bash
THERMAL_PORT=8080 THERMAL_COLORMAP=ironbow python3 thermal_web.py
```

---

## Systemd Service (`thermal-web.service`)

The script is managed via systemd at `/etc/systemd/system/thermal-web.service`.

### Service Commands:

```bash
# Enable and start service
sudo systemctl enable --now thermal-web.service

# Check status
sudo systemctl status thermal-web.service

# Restart service
sudo systemctl restart thermal-web.service

# View live logs
sudo journalctl -u thermal-web.service -f
```

---

## Deployment (GitHub Actions)

The workflow defined in `.github/workflows/thermal_web.yml` automatically deploys changes to the Raspberry Pi over Tailscale whenever `scripts/rasp_zero_cam/` files are pushed.

### Required GitHub Secrets:

- `THERMAL_REMOTE_HOST`: Hostname or Tailscale IP (e.g. `zero.tail72e9f.ts.net`)
- `REMOTE_USER`: SSH username (e.g. `pi`)
- `THERMAL_REMOTE_PORT`: SSH port (default: `22`)
- `SSH_PRIVATE_KEY`: Private SSH key for host authentication
- `TAILSCALE_AUTHKEY`: Tailscale authentication key
