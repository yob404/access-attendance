"""模拟门禁控制器心跳上报
用法：python scripts/heartbeat.py [轮次] [间隔秒]
"""
import json
import sys
import time
import urllib.request

URL = "http://127.0.0.1:5000/api/heartbeat"
DEVICES = [
    {"device_id": "CTL-D01", "door_id": "D01", "ip": "192.168.20.11"},
    {"device_id": "CTL-D02", "door_id": "D02", "ip": "192.168.20.12"},
]


def beat(dev):
    body = json.dumps(dev).encode()
    req = urllib.request.Request(
        URL, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode())


def main():
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    interval = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    for i in range(rounds):
        for dev in DEVICES:
            try:
                r = beat(dev)
                print(f"[{i+1}/{rounds}] {r['time']}  {r['device_id']} 心跳成功")
            except Exception as e:
                print("上报失败:", e)
        if i < rounds - 1:
            time.sleep(interval)


if __name__ == "__main__":
    main()
