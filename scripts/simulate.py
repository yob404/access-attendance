"""模拟门禁设备刷卡：循环上报到 /api/punch
用法：python scripts/simulate.py [次数]
"""
import json
import random
import sys
import time
import urllib.request

URL = "http://127.0.0.1:5000/api/punch"
CARDS = ["10001", "10002", "99999"]
DOORS = ["D01", "D02"]


def punch(card_no, door_id):
    body = json.dumps({"card_no": card_no, "door_id": door_id}).encode()
    req = urllib.request.Request(
        URL, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode())


def main():
    times = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    for i in range(times):
        card = random.choice(CARDS)
        door = random.choice(DOORS)
        try:
            r = punch(card, door)
            print(f"[{i+1}/{times}] {r['time']}  卡{card} -> {r['door']}  结果={r['result']}")
        except Exception as e:
            print("上报失败:", e)
        time.sleep(1)


if __name__ == "__main__":
    main()
