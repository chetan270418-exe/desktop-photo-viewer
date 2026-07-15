<div align="center">
  <h1>Memory Explorer</h1>
  <p><b>A modern, lightning-fast local photo and video library viewer built in Python and PySide6.</b></p>
</div>

<h2>✨ Features</h2>
<ul>
  <li><b>⚡ Blazing Fast:</b> Multi-threaded metadata parsing with disk caching means large photo libraries load quickly.</li>
  <li><b>🗓️ Smart Timeline:</b> Accurately extracts original dates from Google Takeout sidecar files so your timeline remains accurate.</li>
  <li><b>🖼️ Seamless Gallery:</b> Browse photos and play videos across multiple folders in one unified gallery.</li>
  <li><b>🧠 New AI Features:</b> Enjoy slideshow navigation, map-based photo location viewing, AI-powered person recognition, and camera support for retaking photos.</li>
  <li><b>🛡️ Non-Destructive:</b> Read-only design helps keep your memories safe.</li>
</ul>

<h2>📸 Supported Formats</h2>
<table>
  <tr>
    <td><b>Images</b></td>
    <td><code>.jpg</code>, <code>.jpeg</code>, <code>.png</code>, <code>.webp</code>, <code>.bmp</code>, <code>.gif</code></td>
  </tr>
  <tr>
    <td><b>Videos</b></td>
    <td><code>.mp4</code>, <code>.mov</code>, <code>.m4v</code>, <code>.avi</code>, <code>.mkv</code></td>
  </tr>
</table>

<h2>🚀 Installation & Setup</h2>
<ol>
  <li><b>Clone the repository:</b><br/>
    <pre><code>git clone https://github.com/chetan270418-exe/desktop-photo-viewer.git
cd desktop-photo-viewer</code></pre>
  </li>
  <li><b>Create a virtual environment:</b><br/>
    <pre><code>python -m venv .venv</code></pre>
  </li>
  <li><b>Activate the environment:</b><br/>
    <pre><code>.venv\Scripts\activate</code></pre>
  </li>
  <li><b>Install dependencies:</b><br/>
    <pre><code>pip install -r requirements.txt</code></pre>
  </li>
  <li><b>Run the app:</b><br/>
    <pre><code>python main.py</code></pre>
  </li>
</ol>

<h2>🧭 Keyboard Controls</h2>
<table>
  <tr><th>Key</th><th>Action</th></tr>
  <tr><td><kbd>Right</kbd></td><td>Next media item</td></tr>
  <tr><td><kbd>Left</kbd></td><td>Previous media item</td></tr>
  <tr><td><kbd>Shift</kbd> + <kbd>Right</kbd></td><td>Jump forward 10 items</td></tr>
  <tr><td><kbd>Shift</kbd> + <kbd>Left</kbd></td><td>Jump backward 10 items</td></tr>
  <tr><td><kbd>Space</kbd></td><td>Play/Pause video</td></tr>
  <tr><td><kbd>R</kbd></td><td>Rotate image clockwise</td></tr>
  <tr><td><kbd>Shift</kbd> + <kbd>R</kbd></td><td>Rotate image counter-clockwise</td></tr>
  <tr><td><kbd>Del</kbd></td><td>Send current item to trash</td></tr>
  <tr><td><kbd>F</kbd> / <kbd>F11</kbd></td><td>Toggle fullscreen</td></tr>
  <tr><td><kbd>Esc</kbd></td><td>Exit fullscreen</td></tr>
</table>

<h2>🛠 Tech Stack</h2>
<ul>
  <li>Python</li>
  <li>PySide6</li>
  <li>OpenCV and AI-based face recognition</li>
  <li>Pillow and media processing libraries</li>
</ul>

<div align="center">
  <sub>Built with ❤️ using Python, PySide6, and Pillow</sub>
</div>
