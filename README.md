<div align="center">
<h1>BASSLINE Recorder</h1>
<p><b>Lightweight • Simple • Low-Cost</b></p>
<p><i>The essential DMX-over-Art-Net utility for Raspberry Pi Zero (W)</i></p>
<hr>
</div>
<h2><p align="center">📌 Project Philosophy</p></h2>
<p>
The <b>BASSLINE Recorder</b> is built for small bars, summer pop-ups, and venues that need professional lighting without the daily overhead of a dedicated technician. It bridges the gap between complex programming and simple daily operation:
</p>

<ul>
<li><b>The Technician:</b> Builds the rig, programs the scenes on their professional console, and uses the BASSLINE-Recorder to capture the full Art-Net universe.</li>
<li><b>The Venue:</b> Staff can trigger high-quality light shows via a simple web interface—no DMX knowledge or expensive software training required.</li>
</ul>

<h2><p align="center">⚡ Key Features</p></h2>

<ul>
<li><b>Pi Zero Optimized:</b> Designed to run reliably on the most affordable Raspberry Pi hardware.</li>
<li><b>Capture & Play:</b> Record any Art-Net stream and store it in one of 16 slots for instant recall.</li>
<li><b>No-Tech Interface:</b> Simple "Play" buttons and speed controls accessible from any smartphone or tablet.</li>
<li><b>Smart Storage:</b> Automatically detects USB sticks for show transfers, falling back to SD card storage when needed.</li>
<li><b>Headless Reliability:</b> Integrated OLED shows the IP address and status immediately upon boot.</li>
<li><b>Emergency Blackout:</b> A dedicated "Panic" button to instantly clear the DMX universe.</li>
</ul>

<h2><p align="center">🛠 Hardware Requirements</p></h2>

<p>A complete show-controller for the cost of a few drinks:</p>
<ul>
<li><b>Controller:</b> Raspberry Pi Zero / Zero W / Zero 2W.</li>
<li><b>Connectivity:</b> Waveshare Ethernet/USB Hub HAT (provides essential stable networking and USB storage ports).</li>  
<li><b>Display:</b> Standard SSD1306 I2C OLED ($128 \times 64$).</li>
<li><b>Storage:</b> MicroSD card and/or any USB Flash Drive.</li>
</ul>
<h2><p align="center">🚀 Installation & Usage</p></h2>

<p><b>1. Prepare the Directory Structure:</b></p>
<p>The project expects the web interface to be inside a <code>templates</code> folder.</p>

    mkdir -p ~/bassline-recorder/templates
    # Move your files into place
    # app.py -> ~/bassline-recorder/
    # index.html -> ~/bassline-recorder/templates/

<p><b>2. Environment Setup:</b></p>
<p>It is recommended to use a virtual environment to manage dependencies.</p>

    cd ~/bassline-recorder
    python3 -m venv .env
    source .env/bin/activate
    pip install flask psutil luma.oled

<p><b>3. Run the Engine:</b></p>

    # Art-Net requires root to bind to port 6454
    # If using a virtual environment with sudo, provide the full path to the env python
    sudo .env/bin/python3 app.py

<h2><p align="center">📂 File Structure</p></h2>

<p>
The system is ultra-portable, consisting of only two primary functional files:
</p>
<ul>
<li><code>app.py</code>: The Python backend handling Art-Net logic, high-priority threading, and hardware I/O.</li>
<li><code>index.html</code>: The unified web interface including all CSS and Javascript logic.</li>
</ul>

<h2><p align="center">📝 Technical Notes</p></h2>

<p>
<b>OS Recommendation:</b> This project is developed and tested on <b>Raspberry Pi OS Lite (Legacy) Bookworm</b>. The Legacy Lite version is highly recommended for the Pi Zero (W) as it is significantly less resource-intensive than newer or full desktop versions, ensuring maximum CPU cycles are available for DMX timing.
<b>Performance:</b> By using raw sockets and native Python threading, the BASSLINE-Recorder maintains a steady frame rate even on original Pi Zero hardware.




