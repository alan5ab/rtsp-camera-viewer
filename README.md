# rtsp-camera-viewer
desk-top vertical side bar camera viewer
Ubuntu 24.04/26.04 Wayland example
You must have go2rtc installed, and set your hardware decoder and camera urls
Using 640X360 substreams this uses very little resources.

- Hardware decode via Intel VA-API (vaapih264dec)
- go2rtc substreams at 640x360, scaled to 256x144 for thumbnails
- 2-second stagger between camera startups
- Silent retry on transient startup errors
- Click tile → new Waterfox tab via go2rtc WebRTC
- pan/tilt controls via SSH motors command

