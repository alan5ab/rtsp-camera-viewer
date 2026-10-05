# rtsp-camera-viewer

Desktop-side vertical webcam viewer for Ubuntu 24.04/26.04 Wayland. This project shows a slim column of camera thumbnails, reconnects automatically, and opens a full browser view for any camera when you click its tile.

It is intended to work with go2rtc and RTSP streams, using lightweight 640x360 substreams for the desktop sidebar. The app can use Intel VA-API, NVIDIA NVDEC, AMD VCE, or a pure software decoder fallback.

## Features

- Vertical sidebar camera dashboard
- Hardware-accelerated H.264 decoding
- go2rtc-based RTSP substreams
- Automatic reconnect retries
- Click a camera tile to open a full stream in a browser
- Optional PTZ control using SSH commands
- Lightweight 256x144 thumbnail stream previews

## Requirements

- Ubuntu 24.04 LTS or 26.04 LTS
- Python 3
- GTK 4 runtime
- GStreamer 1.0
- go2rtc running locally
- A browser: Chrome, Chromium, Firefox, or Waterfox

## Hardware decoder options

The app defaults to Intel VA-API (`vaapih264dec`) in the GStreamer pipeline. You can switch to another decoder if your hardware supports it.

Supported common options:

- Intel: `vaapih264dec`
- NVIDIA: `nvh264dec`
- AMD: `amfh264dec`
- CPU fallback: `avdec_h264`

## Install dependencies

Run these commands on Ubuntu:

```bash
sudo apt update
sudo apt install -y \
  python3 python3-pip \
  python3-gi python3-gi-cairo gir1.2-gtk-4.0 \
  gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly \
  gstreamer1.0-rtsp gstreamer1.0-vaapi python3-gst-1.0 \
  sshpass
```

### Optional decoder packages

#### Intel
```bash
sudo apt install -y va-driver-all libva2
```

#### NVIDIA
```bash
sudo apt install -y gstreamer1.0-plugins-nvdec
```

#### AMD
```bash
sudo apt install -y gstreamer1.0-plugins-bad
```

Software fallback does not need extra packages; GStreamer can usually decode H.264 on CPU if the required plugins are installed.

## Install a browser

This app opens each stream in a new browser tab using a WebRTC URL. It is designed to work with Chrome, Chromium, Firefox, or Waterfox.

### Chrome
```bash
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo gpg --dearmor -o /usr/share/keyrings/googlechrome.gpg
sudo sh -c 'echo "deb [arch=amd64 signed-by=/usr/share/keyrings/googlechrome.gpg] https://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list'
sudo apt update
sudo apt install -y google-chrome-stable
```

### Chromium
```bash
sudo apt install -y chromium-browser
```

### Firefox
```bash
sudo apt install -y firefox
```

### Waterfox
```bash
sudo apt install -y waterfox
```

If Waterfox is installed, it matches the example behavior in this repo more closely because the code uses `waterfox --new-tab` when you click a tile.

## Install go2rtc

go2rtc is required because the app expects camera feeds at URLs like:

```text
rtsp://127.0.0.1:8554/RFC_sub
rtsp://127.0.0.1:8554/230_sub
rtsp://127.0.0.1:8554/BD_sub
```

### Download go2rtc

```bash
cd /tmp
curl -L -o go2rtc https://github.com/AlexxIT/go2rtc/releases/latest/download/go2rtc_linux_amd64
chmod +x go2rtc
sudo install -m 755 go2rtc /usr/local/bin/go2rtc
```

## Configure go2rtc

Create a config file at `~/.config/go2rtc/config.yaml`:

```bash
mkdir -p ~/.config/go2rtc
cat > ~/.config/go2rtc/config.yaml <<'EOF'
listen: ":1984"

rtsp:
  listen: ":8554"

streams:
  RFC: "rtsp://192.168.1.100:554/stream1"
  "230": "rtsp://192.168.1.101:554/stream1"
  BD: "rtsp://192.168.1.102:554/stream1"
  DC: "rtsp://192.168.1.103:554/stream1"
  CC: "rtsp://192.168.1.104:554/stream1"
  SC: "rtsp://192.168.1.105:554/stream1"
  BC: "rtsp://192.168.1.106:554/stream1"
  GD: "rtsp://192.168.1.107:554/stream1"
  sd: "rtsp://192.168.1.108:554/stream1"
  SHOP: "rtsp://192.168.1.109:554/stream1"
  jc: "rtsp://192.168.1.110:554/stream1"
EOF
```

Replace the example camera IPs and stream URLs with your own.

Start go2rtc:

```bash
go2rtc
```

This should expose:

- RTSP server on `127.0.0.1:8554`
- WebRTC page on `http://127.0.0.1:1984`

## Clone the repo

```bash
git clone https://github.com/alan5ab/rtsp-camera-viewer.git
cd rtsp-camera-viewer
```

## Configure the camera list

Open `camsidebar.py` and edit the `CAMERAS` list near the top:

```python
CAMERAS = [
    ("rtsp://127.0.0.1:8554/RFC_sub", "RFC", "RFC"),
    ("rtsp://127.0.0.1:8554/230_sub", "230", "230"),
    ("rtsp://127.0.0.1:8554/BD_sub",  "BD",  "BD"),
    ("rtsp://127.0.0.1:8554/DC_sub",  "DC",  "DC"),
    ("rtsp://127.0.0.1:8554/CC_sub",  "CC",  "CC"),
    ("rtsp://127.0.0.1:8554/SC_sub",  "SC",  "SC"),
    ("rtsp://127.0.0.1:8554/BC_sub", "BC", "BC"),
    ("rtsp://127.0.0.1:8554/GD_sub", "GD", "GD"),
    ("rtsp://127.0.0.1:8554/sd_sub", "sd", "sd"),
    ("rtsp://127.0.0.1:8554/SHOP_sub", "SHOP", "SHOP"),
    ("rtsp://127.0.0.1:8554/jc_sub",  "jc",  "jc"),
]
```

The tuple format is:

```python
(rtsp_url, go2rtc_name, label)
```

Example:

```python
("rtsp://127.0.0.1:8554/RFC_sub", "RFC", "RFC")
```

This means:

- The app connects to `rtsp://127.0.0.1:8554/RFC_sub`
- The browser opens `RFC` in go2rtc
- The tile label shown is `RFC`

## Set browser URL

The app uses this base URL to open the WebRTC stream in a browser:

```python
GO2RTC_BASE = "http://192.168.254.4:1984/stream.html?mode=webrtc&src="
```

Replace `192.168.254.4` with the machine running go2rtc. For example, if go2rtc is running on the same machine:

```python
GO2RTC_BASE = "http://127.0.0.1:1984/stream.html?mode=webrtc&src="
```

This will work in Chrome, Chromium, Firefox, or Waterfox as long as the browser supports WebRTC.

## Run the viewer

```bash
python3 camsidebar.py
```

## Changing decoder type

The key GStreamer pipeline is built in `CameraStream._build()`.

Default Intel VA-API:

```python
f"rtspsrc location={self.url} protocols=tcp "
 f"latency=100 drop-on-latency=true "
 f"do-rtsp-keep-alive=true ! "
 f"rtph264depay ! h264parse ! "
 f"vaapih264dec ! "
 f"videoconvert ! videoscale ! "
 f"video/x-raw,width={THUMB_W},height={THUMB_H} ! "
 f"gtk4paintablesink name={sink_name} sync=false"
```

NVIDIA decoder example:

```python
f"rtspsrc location={self.url} protocols=tcp "
 f"latency=100 drop-on-latency=true "
 f"do-rtsp-keep-alive=true ! "
 f"rtph264depay ! h264parse ! "
 f"nvh264dec ! "
 f"videoconvert ! videoscale ! "
 f"video/x-raw,width={THUMB_W},height={THUMB_H} ! "
 f"gtk4paintablesink name={sink_name} sync=false"
```

AMD decoder example:

```python
f"rtspsrc location={self.url} protocols=tcp "
 f"latency=100 drop-on-latency=true "
 f"do-rtsp-keep-alive=true ! "
 f"rtph264depay ! h264parse ! "
 f"amfh264dec ! "
 f"videoconvert ! videoscale ! "
 f"video/x-raw,width={THUMB_W},height={THUMB_H} ! "
 f"gtk4paintablesink name={sink_name} sync=false"
```

CPU fallback example:

```python
f"rtspsrc location={self.url} protocols=tcp "
 f"latency=100 drop-on-latency=true "
 f"do-rtsp-keep-alive=true ! "
 f"rtph264depay ! h264parse ! "
 f"avdec_h264 ! "
 f"videoconvert ! videoscale ! "
 f"video/x-raw,width={THUMB_W},height={THUMB_H} ! "
 f"gtk4paintablesink name={sink_name} sync=false"
```

## PTZ controls

The app has an optional PTZ feature for cameras that support a `motors` SSH command.

Update the section at the top of `camsidebar.py`:

```python
PTZ_CAMERAS = {
    "CC": {
        "ip":       "192.168.254.118",
        "user":     "root",
        "password": "PW",
    },
    "SHOP": {
        "ip":       "192.168.254.116",
        "user":     "root",
        "password": "PW",
    },
    "GD": {
        "ip":       "192.168.254.119",
        "user":     "root",
        "password": "PW",
    },
    "sd": {
        "ip":       "192.168.254.117",
        "user":     "root",
        "password": "PW",
    },
}
```

The app sends SSH commands similar to:

```bash
sshpass -p "PW" ssh -o StrictHostKeyChecking=no root@192.168.254.118 "motors -d g -x 50"
```

## Desktop launcher

The repo includes `camsidebar.desktop`, which looks like this:

```ini
[Desktop Entry]
Version=1.0
Type=Application
Name=Cameras Vertical
Comment=RTSP Camera Viewer - Vertical
Exec=python3 /home/al/camsidebar.py
Icon=camera-web
Terminal=false
Categories=AudioVideo;Video;
StartupNotify=true
StartupWMClass=cameras-vertical
```

Update the path to your own repo location:

```ini
Exec=python3 /home/your-user/rtsp-camera-viewer/camsidebar.py
```

Then install it:

```bash
mkdir -p ~/.local/share/applications
cp camsidebar.desktop ~/.local/share/applications/
```

## Troubleshooting

### Stream not connecting

- Check that go2rtc is running
- Confirm the camera stream URL is valid
- Confirm the camera is reachable on the network
- Check that the correct browser is installed

### Browser fails to open the stream

- Check the `GO2RTC_BASE` URL in `camsidebar.py`
- Verify go2rtc is listening on port `1984`
- Open the URL manually in the browser:

```bash
firefox http://127.0.0.1:1984/stream.html?mode=webrtc&src=RFC
```

### Decoding fails or app is slow

- Use hardware decode if available
- Reduce the number of high-resolution streams
- Lower thumbnail resolution if needed
- Keep the app to a manageable number of cameras per session

### PTZ command not working

- Confirm `sshpass` is installed
- Confirm the SSH credentials are correct
- Verify the camera accepts the `motors` command

## Performance notes

This app is intended for a modest number of cameras. The thumbnail pipeline uses low-resolution substreams and a staggered start to avoid large resource spikes. By default the app uses 256x144 thumbnail streams for responsiveness.

If you want a larger preview grid, you can adjust:

```python
THUMB_W, THUMB_H = 256, 144
```

## Human explanation: Copy script to your PC, make changes applicable to your hardware, install dependencies, run

## License

This project is licensed under the MIT License. See the `LICENSE` file in this repository for details.

## Contributing

Pull requests are welcome. If you improve the decoder support, browser support, or installation instructions, please open a PR.
