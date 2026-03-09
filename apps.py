import subprocess
import psutil

def start(path: str):
    subprocess.Popen(path)

def kill(process_name: str):
    for p in psutil.process_iter(["name"]):
        if p.info["name"] == process_name:
            p.kill()
