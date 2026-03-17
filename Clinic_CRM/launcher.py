import socket
import os
import sys
import subprocess
import webbrowser
import time
from contextlib import closing

def find_free_port():
    """Finds an available port on the computer to avoid conflicts."""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(('', 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]

def main():
    # 1. Get a random free port
    port = find_free_port()
    
    # 2. Define the URL
    url = f"http://localhost:{port}"
    
    print(f"🏥 Starting Clinic CRM on Port {port}...")
    
    # 3. Open the browser in "App Mode" (No address bar)
    # We try Chrome first, then Edge
    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    
    browser_cmd = None
    if os.path.exists(chrome_path):
        browser_cmd = [chrome_path, f"--app={url}"]
    elif os.path.exists(edge_path):
        browser_cmd = [edge_path, f"--app={url}"]
    else:
        # Fallback if paths fail (opens standard browser tab)
        webbrowser.open(url)

    if browser_cmd:
        subprocess.Popen(browser_cmd)

    # 4. Launch Streamlit on the specific port
    # sys.executable ensures we use the SAME python environment this script is running in
    cmd = [
        sys.executable, "-m", "streamlit", "run", "app.py",
        "--server.port", str(port),
        "--server.headless", "true",
        "--global.developmentMode", "false"
    ]
    
    subprocess.run(cmd)

if __name__ == "__main__":
    main()