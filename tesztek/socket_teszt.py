"""A valós idejű felügyelet (Socket.IO) tesztje futó szerverrel, ideiglenes SQLite adatbázissal."""
import os
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone

import requests
import socketio

BACKEND = sys.argv[1]
PY = sys.argv[2]
PORT = 8765
URL = f"http://127.0.0.1:{PORT}"
env = dict(os.environ, DATABASE_URL=f"sqlite:///{os.path.join(tempfile.mkdtemp(), 'sock.db')}",
           TEACHER_INVITE_CODE="oktato123", PYTHONIOENCODING="utf-8")
srv = subprocess.Popen([PY, "-m", "uvicorn", "main:app", "--port", str(PORT), "--log-level", "warning"],
                       cwd=BACKEND, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
rows = []
try:
    for _ in range(60):
        try:
            requests.get(URL, timeout=1); break
        except requests.ConnectionError:
            time.sleep(0.5)

    def reg(email, invite=None):
        b = {"email": email, "full_name": email.split("@")[0], "password": "jelszo123"}
        if invite: b["invite_code"] = invite
        requests.post(f"{URL}/auth/register", json=b)
        return requests.post(f"{URL}/auth/login", data={"username": email, "password": "jelszo123"}).json()["access_token"]

    T, T2, S, S2 = reg("oktato@pelda.hu", "oktato123"), reg("oktato2@pelda.hu", "oktato123"), reg("hallgato@pelda.hu"), reg("hallgato2@pelda.hu")
    H = lambda t: {"Authorization": f"Bearer {t}"}
    now = datetime.now(timezone.utc)
    eid = requests.post(f"{URL}/exams/", headers=H(T), json={"title": "Socket", "duration_minutes": 30,
        "start_time": (now - timedelta(minutes=1)).isoformat(), "end_time": (now + timedelta(hours=1)).isoformat()}).json()["id"]
    requests.post(f"{URL}/exams/{eid}/questions", headers=H(T), json={"type": "essay", "title": "x", "description": "?"})
    att = requests.post(f"{URL}/exams/{eid}/attempt", headers=H(S)).json()

    def client(token):
        c = socketio.Client(reconnection=False)
        c.connect(URL, socketio_path="/socket.io", auth={"token": token} if token else None, wait_timeout=10)
        return c

    def check(tid, desc, ok, note=""):
        rows.append((tid, desc, bool(ok), note))

    # S01 token nélkül
    try:
        client(None); refused = False
    except socketio.exceptions.ConnectionError:
        refused = True
    check("S01", "Csatlakozás token nélkül", refused, "elutasítva" if refused else "csatlakozott")
    try:
        client("hamis.token.ertek"); refused = False
    except socketio.exceptions.ConnectionError:
        refused = True
    check("S02", "Csatlakozás érvénytelen tokennel", refused, "elutasítva" if refused else "csatlakozott")

    c_t2 = client(T2)
    ack = c_t2.call("join_exam", {"exam_id": eid}, timeout=5)
    check("S03", "Más oktató belépése a vizsga szobájába", not ack["ok"], ack.get("error"))
    c_s2 = client(S2)
    ack = c_s2.call("join_exam", {"exam_id": eid}, timeout=5)
    check("S04", "Hallgató belépése folyamatban lévő kitöltés nélkül", not ack["ok"], ack.get("error"))

    events = []
    got = threading.Event()
    c_t = client(T)
    for name in ("monitor_snapshot", "student_joined", "violation_alert", "student_finished", "student_left"):
        c_t.on(name, (lambda n: (lambda data: (events.append((n, data, time.perf_counter())), got.set())))(name))
    ack = c_t.call("join_exam", {"exam_id": eid}, timeout=5)
    time.sleep(0.5)
    check("S05", "Az oktató belép, és pillanatképet kap a kitöltésekről",
          ack["ok"] and any(e[0] == "monitor_snapshot" for e in events), f"{len([e for e in events if e[0]=='monitor_snapshot'])} pillanatkép")

    c_s = client(S)
    ack = c_s.call("join_exam", {"exam_id": eid}, timeout=5)
    time.sleep(0.5)
    check("S06", "A hallgató belépéséről az oktató értesítést kap", ack["ok"] and any(e[0] == "student_joined" for e in events))

    lat = []
    for i in range(10):
        got.clear()
        t0 = time.perf_counter()
        c_s.emit("report_violation", {"event_type": "WINDOW_BLUR", "timestamp": datetime.now().isoformat()})
        got.wait(5)
        alerts = [e for e in events if e[0] == "violation_alert"]
        if alerts:
            lat.append((alerts[-1][2] - t0) * 1000)
        time.sleep(0.1)
    alerts = [e for e in events if e[0] == "violation_alert"]
    check("S07", "Ablakelhagyás jelzése az oktatónak (10 esemény)",
          len(alerts) == 10 and alerts[-1][1]["violations"] == 10, f"{len(alerts)} riasztás, utolsó számláló: {alerts[-1][1]['violations'] if alerts else '-'}")
    res = requests.get(f"{URL}/exams/{eid}/results", headers=H(T)).json()
    check("S08", "A szabálysértések száma az adatbázisban is tárolódik", res[0]["violations"] == 10, res[0]["violations"])

    requests.post(f"{URL}/attempts/{att['id']}/finish", headers=H(S))
    c_s.emit("exam_finished")
    time.sleep(0.8)
    check("S09", "Beadáskor az oktató értesítést kap", any(e[0] == "student_finished" for e in events))
    n_before = len([e for e in events if e[0] == "violation_alert"])
    c_s.emit("report_violation", {"event_type": "WINDOW_BLUR"})
    time.sleep(0.8)
    n_after = len([e for e in events if e[0] == "violation_alert"])
    check("S10", "Beadás után küldött jelzés figyelmen kívül marad", n_after == n_before)
    for c in (c_s, c_t, c_t2, c_s2):
        c.disconnect()

    for tid, desc, ok, note in rows:
        print(f"{tid}\t{'OK ' if ok else 'HIBA'}\t{desc}\t[{note}]")
    if lat:
        lat.sort()
        print(f"KESLELTETES\tátlag {sum(lat)/len(lat):.1f} ms, min {lat[0]:.1f} ms, max {lat[-1]:.1f} ms (n={len(lat)}, HTTP long-polling átvitel)")
finally:
    srv.terminate()
