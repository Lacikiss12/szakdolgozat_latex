"""Funkcionális tesztek az online vizsgarendszer backendjéhez (ideiglenes SQLite adatbázissal).
Futtatás: a backend venv Pythonjával, a backend/ mappát a sys.path-ra téve."""
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

DB = os.path.join(tempfile.mkdtemp(), "teszt.db")
os.environ["DATABASE_URL"] = f"sqlite:///{DB}"
os.environ["TEACHER_INVITE_CODE"] = "oktato123"
sys.path.insert(0, sys.argv[1])  # backend mappa

from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.models.models import Attempt  # noqa: E402

c = TestClient(main.fastapi_app)
results = []


def check(tid, desc, cond, detail=""):
    results.append((tid, desc, bool(cond), detail))


def reg(email, name, invite=None):
    body = {"email": email, "full_name": name, "password": "jelszo123"}
    if invite is not None:
        body["invite_code"] = invite
    return c.post("/auth/register", json=body)


def login(email, pw="jelszo123"):
    return c.post("/auth/login", data={"username": email, "password": pw})


def hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


now = datetime.now(timezone.utc)

# --- Hitelesítés ---
r = reg("oktato@pelda.hu", "Oktató Olga", "rossz-kod")
check("T01", "Oktatói regisztráció hibás meghívókóddal", r.status_code == 400, r.status_code)
r = reg("oktato@pelda.hu", "Oktató Olga", "oktato123")
check("T02", "Oktatói regisztráció helyes meghívókóddal", r.status_code == 200 and r.json()["role"] == "teacher", r.json().get("role"))
r = reg("hallgato@pelda.hu", "Hallgató Henrik")
check("T03", "Hallgatói regisztráció (alapértelmezett szerepkör)", r.status_code == 200 and r.json()["role"] == "student", r.json().get("role"))
r = reg("hallgato@pelda.hu", "Másik")
check("T04", "Regisztráció már foglalt e-mail címmel", r.status_code == 400, r.status_code)
reg("oktato2@pelda.hu", "Oktató Ottó", "oktato123")
reg("hallgato2@pelda.hu", "Hallgató Hanna")
r = login("hallgato@pelda.hu", "rossz")
check("T05", "Bejelentkezés hibás jelszóval", r.status_code == 401, r.status_code)
T = login("oktato@pelda.hu").json()["access_token"]
T2 = login("oktato2@pelda.hu").json()["access_token"]
S = login("hallgato@pelda.hu").json()["access_token"]
S2 = login("hallgato2@pelda.hu").json()["access_token"]
r = c.get("/auth/me", headers=hdr("ervenytelen.token.ertek"))
check("T06", "Védett végpont érvénytelen tokennel", r.status_code == 401, r.status_code)

# --- Vizsga és feladatok ---
exam_body = {"title": "Tesztvizsga", "duration_minutes": 60,
             "start_time": (now - timedelta(minutes=5)).isoformat(),
             "end_time": (now + timedelta(hours=2)).isoformat()}
r = c.post("/exams/", json=exam_body, headers=hdr(S))
check("T07", "Vizsga létrehozása hallgatói fiókkal", r.status_code == 403, r.status_code)
bad = dict(exam_body, end_time=(now - timedelta(hours=1)).isoformat())
r = c.post("/exams/", json=bad, headers=hdr(T))
check("T08", "Vizsga létrehozása hibás időablakkal", r.status_code == 422, r.status_code)
exam = c.post("/exams/", json=exam_body, headers=hdr(T)).json()
eid = exam["id"]

qs = {}
def addq(key, body):
    r = c.post(f"/exams/{eid}/questions", json=body, headers=hdr(T))
    qs[key] = r.json()
    return r

addq("single", {"type": "single_choice", "title": "Főváros", "description": "?", "points": 5,
                "options": ["Pécs", "Budapest", "Győr"], "answer_key": [1]})
addq("multi", {"type": "multiple_choice", "title": "Prímek", "description": "?", "points": 6,
               "options": ["2", "3", "4", "5"], "answer_key": [0, 1, 3]})
addq("tf", {"type": "true_false", "title": "Igaz-hamis", "description": "?", "points": 2, "answer_key": [0]})
addq("short", {"type": "short_text", "title": "Pi", "description": "?", "points": 3, "answer_key": ["3.14"]})
addq("essay", {"type": "essay", "title": "REST", "description": "?", "points": 10})
r = c.post(f"/exams/{eid}/questions", json={"type": "single_choice", "title": "x", "description": "?",
                                              "options": ["a", "b"], "answer_key": [5]}, headers=hdr(T))
check("T09", "Feladat nem létező helyes válasz indexszel", r.status_code == 422, r.status_code)
r = c.post(f"/exams/{eid}/questions", json={"type": "essay", "title": "x", "description": "?"}, headers=hdr(T2))
check("T10", "Feladat hozzáadása más oktató vizsgájához", r.status_code == 403, r.status_code)
r = c.get(f"/exams/{eid}", headers=hdr(S))
check("T11", "Oktatói vizsganézet (megoldókulccsal) hallgatói fiókkal", r.status_code == 403, r.status_code)

# --- Vizsgafolyamat ---
r = c.post(f"/exams/{eid}/attempt", headers=hdr(T))
check("T12", "Vizsga kitöltése oktatói fiókkal", r.status_code == 403, r.status_code)
r = c.post(f"/exams/{eid}/attempt", headers=hdr(S))
att = r.json()
text = r.text
check("T13", "A hallgatónak küldött feladatokban nincs megoldókulcs",
      r.status_code == 200 and "answer_key" not in text, "answer_key" in text)
dl = datetime.fromisoformat(att["deadline"])
st = datetime.fromisoformat(att["started_at"])
check("T14", "Határidő = min(kezdés + időtartam, vizsga vége)", abs((dl - st).total_seconds() - 3600) < 2,
      f"{(dl - st).total_seconds():.0f} mp")
r2 = c.post(f"/exams/{eid}/attempt", headers=hdr(S))
check("T15", "Ismételt indítás ugyanazt a kitöltést adja vissza", r2.json()["id"] == att["id"], r2.json()["id"])
aid = att["id"]


def save(qkey, resp, tok=S, a=None):
    return c.put(f"/attempts/{a or aid}/answers/{qs[qkey]['id']}", json={"response": resp}, headers=hdr(tok))


r = save("single", [0, 1])
check("T16", "Egyválasztós feladatnál két jelölés mentése", r.status_code == 422, r.status_code)
r = save("single", [7])
check("T17", "Nem létező válaszlehetőség mentése", r.status_code == 422, r.status_code)
r = save("single", [1], tok=S2)
check("T18", "Más hallgató kitöltésébe mentés", r.status_code == 404, r.status_code)
save("single", [1]); save("multi", [0, 1, 2]); save("tf", [0]); save("short", "  3,14 ")
save("essay", "A REST egy architekturális stílus...")
r = c.get(f"/exams/{eid}/attempt", headers=hdr(S))
check("T19", "Pontszám nem látható a beadás előtt", r.json()["total_score"] is None, r.json()["total_score"])
r = c.post(f"/attempts/{aid}/finish", headers=hdr(S))
fin = r.json()
by_q = {a["question_id"]: a for a in fin["answers"]}
check("T20", "Egyválasztós helyes válasz: teljes pont", by_q[qs["single"]["id"]]["score"] == 5, by_q[qs["single"]["id"]]["score"])
check("T21", "Több választós (2 jó + 1 rossz jelölés a 3 jóból): 6 * 1/3 = 2 pont",
      by_q[qs["multi"]["id"]]["score"] == 2, by_q[qs["multi"]["id"]]["score"])
check("T22", "Rövid válasz: \"  3,14 \" elfogadva \"3.14\"-ként", by_q[qs["short"]["id"]]["score"] == 3, by_q[qs["short"]["id"]]["score"])
check("T23", "Kifejtős válasz javításra vár", by_q[qs["essay"]["id"]]["status"] == "pending_review" and fin["pending_review"] == 1,
      by_q[qs["essay"]["id"]]["status"])
check("T24", "Összpontszám a beadás után (5+2+2+3 = 12 / 26)", fin["total_score"] == 12 and fin["max_score"] == 26,
      f'{fin["total_score"]}/{fin["max_score"]}')
r = save("single", [0])
check("T25", "Válasz módosítása beadás után", r.status_code == 409, r.status_code)

# --- Oktatói értékelés ---
res = c.get(f"/exams/{eid}/results", headers=hdr(T)).json()
essay_ans = [a for a in res[0]["answers"] if a["question_id"] == qs["essay"]["id"]][0]
r = c.patch(f"/answers/{essay_ans['id']}/grade", json={"manual_score": 11}, headers=hdr(T))
check("T26", "Kézi pontozás a maximumnál több ponttal", r.status_code == 422, r.status_code)
r = c.patch(f"/answers/{essay_ans['id']}/grade", json={"manual_score": 8, "feedback": "Jó"}, headers=hdr(T2))
check("T27", "Kézi pontozás más oktató vizsgájában", r.status_code == 403, r.status_code)
r = c.patch(f"/answers/{essay_ans['id']}/grade", json={"manual_score": 8, "feedback": "Jó"}, headers=hdr(T))
fin2 = c.get(f"/exams/{eid}/attempt", headers=hdr(S)).json()
check("T28", "Kézi pontozás után a hallgató látja a pontot és a visszajelzést",
      fin2["total_score"] == 20 and fin2["pending_review"] == 0, f'{fin2["total_score"]}, {fin2["pending_review"]}')
r = c.get(f"/exams/{eid}/results.csv", headers=hdr(T))
check("T29", "CSV export: UTF-8 BOM és pontosvessző elválasztó",
      r.content.startswith(b"\xef\xbb\xbf") and ";" in r.text.splitlines()[0], r.headers.get("content-type"))

# --- Lejárt kitöltés ---
a2 = c.post(f"/exams/{eid}/attempt", headers=hdr(S2)).json()
c.put(f"/attempts/{a2['id']}/answers/{qs['single']['id']}", json={"response": [1]}, headers=hdr(S2))
with SessionLocal() as db:
    at = db.get(Attempt, a2["id"])
    at.deadline = datetime.now(timezone.utc) - timedelta(minutes=5)
    db.commit()
r = c.put(f"/attempts/{a2['id']}/answers/{qs['tf']['id']}", json={"response": [0]}, headers=hdr(S2))
check("T30", "Mentés a határidő (és a türelmi idő) lejárta után", r.status_code == 409, r.status_code)
r = c.get(f"/exams/{eid}/attempt", headers=hdr(S2)).json()
check("T31", "Lejárt kitöltés automatikus lezárása és értékelése (mentett válasz pontot ér)",
      r["finished_at"] is not None and r["total_score"] == 5, f'{r["finished_at"] is not None}, {r["total_score"]}')

# --- Időablakon kívül ---
fut = c.post("/exams/", json=dict(exam_body, start_time=(now + timedelta(days=1)).isoformat(),
                                    end_time=(now + timedelta(days=2)).isoformat()), headers=hdr(T)).json()
c.post(f"/exams/{fut['id']}/questions", json={"type": "essay", "title": "x", "description": "?"}, headers=hdr(T))
r = c.post(f"/exams/{fut['id']}/attempt", headers=hdr(S))
check("T32", "Vizsga indítása a kezdési időpont előtt", r.status_code == 403, r.status_code)

ok = sum(1 for r in results if r[2])
for tid, desc, passed, detail in results:
    print(f"{tid}\t{'OK ' if passed else 'HIBA'}\t{desc}\t[{detail}]")
print(f"\nÖsszesen: {ok}/{len(results)} sikeres")
