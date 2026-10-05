#!/usr/bin/env python3
"""
camsidebar.py — camera RTSP viewer for Ubuntu 24.04/26.04 Wayland

- Hardware decode via Intel VA-API (vaapih264dec)
- go2rtc substreams at 640x360, scaled to 256x144 for thumbnails
- 2-second stagger between camera startups
- Silent retry on transient startup errors
- Click tile → new Waterfox tab via go2rtc WebRTC
- CC has pan/tilt controls via SSH motors command

Dependencies:
    sudo apt install \
        python3-gi python3-gi-cairo gir1.2-gtk-4.0 \
        gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
        gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly \
        gstreamer1.0-rtsp gstreamer1.0-vaapi python3-gst-1.0
"""

import sys
import subprocess
import threading

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gst", "1.0")
from gi.repository import Gtk, Gdk, Gst, GLib, GObject


# ── Config ─────────────────────────────────────────────────────────────────────

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

THUMB_W, THUMB_H = 256, 144

RECONNECT_DELAY = 7
STARTUP_RETRY = 3
STAGGER_DELAY = 2

GO2RTC_BASE = (
    "http://192.168.254.4:1984/stream.html?mode=webrtc&src="
)


# PTZ camera SSH config — add all 4 P/T cameras here
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

PTZ_STEP = 50   # motor steps per button click


_sink_counter = 0


def _unique_sink_name():
    global _sink_counter
    _sink_counter += 1
    return f"sink{_sink_counter}"


def open_in_waterfox(go2rtc_name: str):
    """Open the go2rtc WebRTC stream page as a new tab."""
    subprocess.Popen(
        ["waterfox", "--new-tab", GO2RTC_BASE + go2rtc_name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


# ── PTZ via SSH ──────────────────────────────────────────────────────────────

def _ptz_ssh(ip, user, password, cmd):
    """Run a motors command on the camera via SSH."""
    subprocess.run(
        [
            "sshpass", "-p", password,
            "ssh", "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=3",
            f"{user}@{ip}", cmd,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def ptz_move(label, x=0, y=0):
    cfg = PTZ_CAMERAS.get(label)
    if not cfg:
        return
    if x != 0:
        cmd = f"motors -d g -x {x}"
    else:
        cmd = f"motors -d g -y {y}"
    threading.Thread(
        target=_ptz_ssh,
        args=(cfg["ip"], cfg["user"], cfg["password"], cmd),
        daemon=True,
    ).start()


def ptz_stop(label):
    pass  # not needed — motors command completes on its own


class PTZButton(Gtk.Button):
    """Send motors command via SSH on each click."""

    def __init__(self, label, x=0.0, y=0.0, viewer=None):
        super().__init__(label=label)
        self.add_css_class("ptz-button")
        self._x      = x
        self._y      = y
        self._viewer = viewer
        self.connect("clicked", self._on_click)

    def _on_click(self, btn):
        target = (
            self._viewer._ptz_target
            if self._viewer
            else list(PTZ_CAMERAS.keys())[0]
        )
        ptz_move(target, self._x, self._y)


# ── GStreamer pipeline ─────────────────────────────────────────────────────────

class CameraStream(GObject.Object):

    __gsignals__ = {
        "paintable-ready": (
            GObject.SignalFlags.RUN_FIRST,
            None,
            (object,),
        ),

        "stream-error": (
            GObject.SignalFlags.RUN_FIRST,
            None,
            (str,),
        ),
    }

    def __init__(self, url: str):

        super().__init__()

        self.url = url
        self._pipe = None
        self._retry = None
        self._has_frame = False

        self._build()

    def _build(self):

        sink_name = _unique_sink_name()

        desc = (
            f"rtspsrc location={self.url} protocols=tcp "
            f"latency=100 drop-on-latency=true "
            f"do-rtsp-keep-alive=true ! "
            f"rtph264depay ! h264parse ! "
            f"vaapih264dec ! "
            f"videoconvert ! videoscale ! "
            f"video/x-raw,width={THUMB_W},height={THUMB_H} ! "
            f"gtk4paintablesink name={sink_name} sync=false"
        )

        try:

            self._pipe = Gst.parse_launch(desc)

        except GLib.Error as exc:

            print(
                f"[pipeline error] {self.url}: {exc}",
                flush=True
            )

            self._schedule_reconnect(
                str(exc),
                startup=True
            )

            return

        sink = self._pipe.get_by_name(sink_name)

        if sink:

            paintable = sink.get_property("paintable")

            GLib.idle_add(
                self._emit_paintable,
                paintable
            )

        bus = self._pipe.get_bus()

        bus.add_signal_watch()

        bus.connect(
            "message::error",
            self._on_error
        )

        bus.connect(
            "message::eos",
            self._on_eos
        )

        self._pipe.set_state(
            Gst.State.PLAYING
        )

    def _emit_paintable(self, paintable):

        self._has_frame = True

        self.emit(
            "paintable-ready",
            paintable
        )

        return GLib.SOURCE_REMOVE

    def _on_error(self, bus, msg):

        err, _ = msg.parse_error()
        err_str = str(err)

        # Suppress noisy resource errors (stream not found, not yet available)
        silent = any(x in err_str for x in (
            "Not found",
            "not found",
            "Could not open resource",
            "Internal data stream error",
        ))

        if self._has_frame:
            if not silent:
                print(
                    f"[gst error] {self.url}: {err}",
                    flush=True
                )
            self._schedule_reconnect(err_str, startup=False)
        else:
            self._schedule_reconnect(err_str, startup=True)

    def _on_eos(self, bus, msg):

        print(
            f"[eos] {self.url}",
            flush=True
        )

        self._schedule_reconnect(
            "EOS",
            startup=False
        )

    def _schedule_reconnect(self, reason: str, startup: bool):

        self.emit(
            "stream-error",
            reason
        )

        self._stop()

        if self._retry is None:

            delay = (
                STARTUP_RETRY
                if startup
                else RECONNECT_DELAY
            )

            self._retry = GLib.timeout_add_seconds(
                delay,
                self._do_reconnect
            )

    def _do_reconnect(self):

        self._retry = None
        self._has_frame = False

        self._build()

        return GLib.SOURCE_REMOVE

    def _stop(self):

        if self._pipe:

            self._pipe.set_state(
                Gst.State.NULL
            )

            self._pipe = None

    def destroy(self):

        if self._retry:

            GLib.source_remove(
                self._retry
            )

            self._retry = None

        self._stop()


# ── Thumbnail tile ─────────────────────────────────────────────────────────────

class CameraTile(Gtk.Button):

    def __init__(
        self,
        index: int,
        url: str,
        label: str
    ):

        super().__init__()

        self.index = index
        self.url = url
        self._stream = None

        self.set_size_request(
            THUMB_W,
            THUMB_H
        )

        self.add_css_class(
            "camera-tile"
        )

        self.add_css_class(
            "flat"
        )

        overlay = Gtk.Overlay()

        self._picture = Gtk.Picture()

        self._picture.set_size_request(
            THUMB_W,
            THUMB_H
        )

        self._picture.set_content_fit(
            Gtk.ContentFit.FILL
        )

        self._picture.set_can_target(
            False
        )

        overlay.set_child(
            self._picture
        )

        lbl = Gtk.Label(
            label=f"{index + 1}  {label}"
        )

        lbl.add_css_class(
            "cam-label"
        )

        lbl.set_halign(
            Gtk.Align.START
        )

        lbl.set_valign(
            Gtk.Align.END
        )

        lbl.set_can_target(
            False
        )

        overlay.add_overlay(
            lbl
        )

        self._dot = Gtk.Label(
            label="●"
        )

        self._dot.add_css_class(
            "status-dot"
        )

        self._dot.add_css_class(
            "connecting"
        )

        self._dot.set_halign(
            Gtk.Align.END
        )

        self._dot.set_valign(
            Gtk.Align.START
        )

        self._dot.set_can_target(
            False
        )

        overlay.add_overlay(
            self._dot
        )

        self._placeholder = Gtk.Label(
            label=f"Starting…\n{label}"
        )

        self._placeholder.add_css_class(
            "placeholder"
        )

        self._placeholder.set_wrap(
            True
        )

        self._placeholder.set_justify(
            Gtk.Justification.CENTER
        )

        self._placeholder.set_can_target(
            False
        )

        overlay.add_overlay(
            self._placeholder
        )

        self.set_child(
            overlay
        )

    def start_stream(self):

        self._placeholder.set_label(
            "Connecting…"
        )

        self._stream = CameraStream(
            self.url
        )

        self._stream.connect(
            "paintable-ready",
            self._on_paintable
        )

        self._stream.connect(
            "stream-error",
            self._on_stream_error
        )

    def _on_paintable(
        self,
        stream,
        paintable
    ):

        self._picture.set_paintable(
            paintable
        )

        self._placeholder.set_visible(
            False
        )

        self._set_dot(
            "ok"
        )

    def _on_stream_error(
        self,
        stream,
        msg
    ):

        self._placeholder.set_label(
            "Reconnecting…"
        )

        self._placeholder.set_visible(
            True
        )

        self._set_dot(
            "error"
        )

    def _set_dot(self, state):

        for s in (
            "ok",
            "connecting",
            "error"
        ):

            self._dot.remove_css_class(
                s
            )

        self._dot.add_css_class(
            state
        )

    def destroy_stream(self):

        if self._stream:

            self._stream.destroy()

            self._stream = None


# ── CSS ────────────────────────────────────────────────────────────────────────

CSS = b"""
window {
    background-color: #0d0d0d;
}

button.camera-tile {
    padding: 0;
    border-radius: 0;
    border: 1px solid #252525;
    background: #111;
    outline: none;
    box-shadow: none;
}

button.camera-tile:hover {
    border-color: #4af;
    background: #111;
}

button.camera-tile:active {
    background: #1a1a1a;
}

.cam-label {
    font-family: monospace;
    font-size: 11px;
    color: #ccc;
    padding: 3px 6px;
    background: rgba(0,0,0,.6);
}

.status-dot {
    font-size: 10px;
    padding: 4px 6px;
}

.status-dot.ok {
    color: #3f3;
}

.status-dot.connecting {
    color: #fa0;
}

.status-dot.error {
    color: #f44;
}

.placeholder {
    font-size: 11px;
    color: #555;
    padding: 8px;
}

.ptz-sel-btn {
    font-family: monospace;
    font-size: 10px;
    padding: 2px 6px;
    background: #222;
    color: #aaa;
    border: 1px solid #333;
    border-radius: 3px;
}
.ptz-sel-btn:checked {
    background: #1e3a5a;
    color: #4af;
    border-color: #4af;
}

.ptz-panel {
    padding: 6px;
    margin-top: 2px;
    border: 1px solid #252525;
    background: #111;
}

.ptz-button {
    min-width: 29px;
    min-height: 23px;
    padding: 0;
    font-size: 8px;
}

scrolledwindow {
    background: transparent;
}
"""


# ── Main window ────────────────────────────────────────────────────────────────

class RTSPViewer(Gtk.ApplicationWindow):

    def __init__(self, app, urls):

        super().__init__(
            application=app,
            title="Cameras"
        )

        self.set_default_size(
            THUMB_W,
            1050
        )

        self._cameras = urls
        self._tiles = []

        scroll = Gtk.ScrolledWindow()

        scroll.set_policy(
            Gtk.PolicyType.NEVER,
            Gtk.PolicyType.AUTOMATIC
        )

        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=2
        )

        box.set_margin_top(2)
        box.set_margin_bottom(2)
        box.set_margin_start(2)
        box.set_margin_end(2)

        for i, (
            sub_url,
            go2rtc_name,
            label
        ) in enumerate(urls):

            tile = CameraTile(
                i,
                sub_url,
                label
            )

            tile.connect(
                "clicked",
                lambda btn,
                       n=go2rtc_name:
                    open_in_waterfox(n)
            )

            self._tiles.append(
                tile
            )

            box.append(
                tile
            )

        # PTZ controls — camera selector + d-pad
        ptz_panel = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=4
        )
        ptz_panel.set_valign(Gtk.Align.CENTER)
        ptz_panel.add_css_class("ptz-panel")

        # Currently selected PTZ camera
        self._ptz_target = list(PTZ_CAMERAS.keys())[0]

        # Camera selector buttons
        selector = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=2
        )
        selector.set_halign(Gtk.Align.CENTER)

        for cam_name in PTZ_CAMERAS:
            btn = Gtk.ToggleButton(label=cam_name)
            btn.add_css_class("ptz-sel-btn")
            btn.set_active(cam_name == self._ptz_target)
            btn.connect("clicked", self._on_ptz_select, cam_name, selector)
            selector.append(btn)

        ptz_panel.append(selector)

        # D-pad
        controls = Gtk.Grid()
        controls.set_row_spacing(2)
        controls.set_column_spacing(2)
        controls.set_halign(Gtk.Align.CENTER)

        up    = PTZButton("▲", y=-PTZ_STEP, viewer=self)
        left  = PTZButton("◀", x=-PTZ_STEP, viewer=self)
        right = PTZButton("▶", x=PTZ_STEP,  viewer=self)
        down  = PTZButton("▼", y=PTZ_STEP,  viewer=self)

        controls.attach(up,    1, 0, 1, 1)
        controls.attach(left,  0, 1, 1, 1)
        controls.attach(right, 2, 1, 1, 1)
        controls.attach(down,  1, 2, 1, 1)

        ptz_panel.append(controls)
        box.append(ptz_panel)

        scroll.set_child(box)
        self.set_child(scroll)

        for i, tile in enumerate(self._tiles):
            delay = i * STAGGER_DELAY
            if delay == 0:
                tile.start_stream()
            else:
                GLib.timeout_add_seconds(delay, self._start_tile, i)

        key = Gtk.EventControllerKey()
        key.connect("key-pressed", self._on_key)
        self.add_controller(key
        )

    def _on_ptz_select(self, btn, cam_name, selector):
        self._ptz_target = cam_name
        child = selector.get_first_child()
        while child:
            child.set_active(child.get_label() == cam_name)
            child = child.get_next_sibling()

    def _start_tile(self, index):

        self._tiles[index].start_stream()

        return GLib.SOURCE_REMOVE

    def _on_key(
        self,
        ctrl,
        keyval,
        keycode,
        state
    ):

        if keyval == Gdk.KEY_Escape:

            self.get_application().quit()

            return True

        return False

    def cleanup(self):

        for tile in self._tiles:

            tile.destroy_stream()


# ── App ────────────────────────────────────────────────────────────────────────

class App(Gtk.Application):

    def __init__(self, urls):

        super().__init__(
            application_id="com.example.rtspviewer"
        )

        self._urls = urls
        self._win = None

    def do_activate(self):

        provider = Gtk.CssProvider()

        provider.load_from_data(
            CSS
        )

        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self._win = RTSPViewer(
            self,
            self._urls
        )

        self._win.connect(
            "close-request",
            self._on_close
        )

        self._win.present()

    def _on_close(
        self,
        win
    ):

        if self._win:

            self._win.cleanup()

        self.quit()

        return False


def main():

    Gst.init(None)

    App(
        CAMERAS
    ).run(None)


if __name__ == "__main__":
    main()
