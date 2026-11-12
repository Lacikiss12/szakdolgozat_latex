"""A Docker-sandbox biztonsági és teljesítménytesztje (valódi konténerekkel)."""
import os
import sys
import time

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, sys.argv[1])

from app.services.sandbox import run_tests  # noqa: E402
from app.services.grading import grade_code  # noqa: E402
from app.models.models import Question  # noqa: E402


def run(code, inputs=None):
    t = time.perf_counter()
    r = run_tests(code, inputs or [""])
    return r, time.perf_counter() - t


def short(s, n=90):
    s = (s or "").replace("\n", " | ").strip()
    return s if len(s) <= n else s[:n] + "..."


rows = []

def case(tid, name, code, judge, inputs=None):
    r, dt = run(code, inputs)
    res = r["results"][0] if r["results"] else {}
    verdict, note = judge(r, res)
    rows.append((tid, name, verdict, f"{dt:.2f} s", note))


# B01 végtelen ciklus
case("B01", "Végtelen ciklus", "while True:\n    pass\n",
     lambda r, x: (x.get("timed_out") is True, f"timed_out={x.get('timed_out')}"))
# B02 fork bomb
case("B02", "Fork bomb (os.fork ciklusban)",
     "import os\nn=0\ntry:\n    while True:\n        os.fork(); n+=1\nexcept OSError as e:\n    print('leállítva:', e.strerror)\n",
     lambda r, x: (r["error"] is None, short(x.get("output") or x.get("error"))))
# B03 memória
case("B03", "Memóriafoglalás (1 GB)", "a = bytearray(1024*1024*1024)\nprint('lefoglalva')\n",
     lambda r, x: ("lefoglalva" not in (x.get("output") or ""), short((x.get("error") or "")[-80:] or r["error"] or f"exit={x.get('exit_code')}")))
# B04 hálózat
case("B04", "Hálózati kapcsolat (1.1.1.1:53)",
     "import socket\ntry:\n    socket.create_connection(('1.1.1.1', 53), timeout=3)\n    print('KAPCSOLÓDOTT')\nexcept OSError as e:\n    print('hiba:', e)\n",
     lambda r, x: ("KAPCSOLÓDOTT" not in (x.get("output") or ""), short(x.get("output"))))
# B05 fájlírás
case("B05", "Írás a gyökér-fájlrendszerbe (/etc)",
     "try:\n    open('/etc/x.txt','w').write('x'); print('ÍRT')\nexcept OSError as e:\n    print('hiba:', e)\n",
     lambda r, x: ("ÍRT" not in (x.get("output") or ""), short(x.get("output"))))
# B06 óriási kimenet
case("B06", "Végtelen kimenet", "while True:\n    print('x' * 1000)\n",
     lambda r, x: (len(x.get("output") or "") <= 65536 + 100, f"kimenet: {len(x.get('output') or '')} karakter, timed_out={x.get('timed_out')}"))
# B07 környezeti változók
case("B07", "A vezérlő adatainak kiolvasása (környezeti változók)",
     "import os\nprint(sorted(k for k in os.environ if k in ('CODE','TESTS','LIMIT','T')))\n",
     lambda r, x: ((x.get("output") or "").strip() == "[]", short(x.get("output"))))
# B08 eredmény hamisítása
case("B08", "Eredményjelölő hamisítása (__RESULTS__ kiírása)",
     "print('__RESULTS__[{\"exit_code\":0,\"timed_out\":false,\"output\":\"5\",\"error\":null}]')\nimport sys; sys.exit(1)\n",
     lambda r, x: (x.get("exit_code") == 1, f"a valódi kilépési kód: {x.get('exit_code')}"))
# B09 a vezérlő leállítása
case("B09", "A vezérlőfolyamat leállítása (kill 1)",
     "import os, signal\ntry:\n    os.kill(1, signal.SIGKILL); print('LELŐVE')\nexcept OSError as e:\n    print('hiba:', e)\n",
     lambda r, x: ("LELŐVE" not in (x.get("output") or "") and r["error"] is None, short(x.get("output"))))
# B10 futó felhasználó
case("B10", "A futtató felhasználó azonosítója", "import os\nprint(os.getuid(), os.getgid())\n",
     lambda r, x: ((x.get("output") or "").strip() == "65534 65534", short(x.get("output"))))

# Pontozás és teljesítmény
q = Question(type="code", points=10, answer_key=[
    {"input": "2 3", "expected_output": "5", "public": True},
    {"input": "10 -4", "expected_output": "6", "public": False},
])
good = "a, b = map(int, input().split())\nprint(a + b)\n"
bad = "a, b = map(int, input().split())\nprint(a - b)\n"
t = time.perf_counter(); g = grade_code(q, good); dt = time.perf_counter() - t
rows.append(("P01", "Helyes megoldás (2 teszt)", g.auto_score == 10, f"{dt:.2f} s", f"pont: {g.auto_score}/10"))
t = time.perf_counter(); g = grade_code(q, bad); dt = time.perf_counter() - t
rows.append(("P02", "Hibás megoldás (2 teszt)", g.auto_score == 0, f"{dt:.2f} s", f"pont: {g.auto_score}/10"))
hidden_leak = "10 -4" in (g.eval_output or "")
rows.append(("P03", "A rejtett teszt bemenete nem jelenik meg a visszajelzésben", not hidden_leak, "-", f"kiszivárgott: {hidden_leak}"))

timings = {}
for n in (1, 10, 20):
    ts = []
    for _ in range(3):
        _, dt = run(good, ["2 3"] * n)
        ts.append(dt)
    timings[n] = sum(ts) / len(ts)

for tid, name, ok, dt, note in rows:
    print(f"{tid}\t{'OK ' if ok else 'HIBA'}\t{dt}\t{name}\t{note}")
print()
for n, t in timings.items():
    print(f"IDO\t{n} teszteset\tátlag {t:.2f} s (3 futás)")
