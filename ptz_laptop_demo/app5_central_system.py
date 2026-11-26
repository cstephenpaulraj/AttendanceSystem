"""APP 5 - COLLEGE CENTRAL SYSTEM (simulator)

Plays the college's central system, which owns the timetable and the student records:

  students   send the college student list (ID, name, class, RF card number) to the Edge AI
  sessions   send the lecture sessions of a day: subject, lecturer, hall, time and the students
             expected in each session (there can be many sessions a day)
  list       show the sessions the Edge AI holds and their counts
  pull       get one session's attendance at any time (during or after the session), or every
             session of a day; optionally save it as CSV

The central system never receives photos or face codes, only attendance.

Examples:
  python app5_central_system.py students --csv sim\\college_students.csv
  python app5_central_system.py sessions --csv sim\\timetable.csv            (date = today)
  python app5_central_system.py list
  python app5_central_system.py pull --session SIM-20261126-ANAT101 --csv anat.csv
  python app5_central_system.py pull --date 2026-11-26
  python app5_central_system.py                                             (menu)
"""
import argparse
import csv
import datetime as dt
import json
import sys

import requests

from common import config

HEAD = {"X-College-Key": config.COLLEGE_API_KEY}


def call(method, path, **kw):
    try:
        r = requests.request(method, config.EDGE_URL + path, headers=HEAD, timeout=15, **kw)
    except requests.RequestException:
        sys.exit(f"Edge AI service not reachable at {config.EDGE_URL}. Start app 3 first.")
    if r.status_code != 200:
        sys.exit(f"Edge AI answered {r.status_code}: {r.text}")
    return r.json()


def send_students(path):
    with open(path, newline="", encoding="utf-8") as f:
        rows = [{k: (v or "").strip() for k, v in r.items()} for r in csv.DictReader(f)]
    res = call("PUT", "/api/v1/students", json=rows)
    print(f"Sent the college student list: {res['students']} students (with RF card numbers).")


def send_sessions(path, date):
    sessions = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            r = {k: (v or "").strip() for k, v in r.items()}
            sessions.append({**r, "session_id": r["session_id"].replace("{date}", date.replace("-", "")),
                             "date": date, "students": r["students"].split()})
    for res in call("POST", "/api/v1/sessions", json=sessions):
        print(f"  {res['session_id']:<28} {res['status']}" + (f", {res['students']} students" if "students" in res else ""))
    print(f"Sent {len(sessions)} session(s) for {date}.")


def show_list(date=None):
    rows = call("GET", "/api/v1/sessions", params={"date": date} if date else None)
    if not rows:
        print("No sessions on the Edge AI.")
    print(f"{'Session':<28} {'Subject':<9} {'Lect':<5} {'Date':<10} {'Time':<11} {'From':<7} {'State':<9} "
          f"{'Mode':<14} Exp Pres OD NotInList")
    for s in rows:
        print(f"{s['session_id']:<28} {s['subject_code'] or '':<9} {s['lecturer_id'] or '':<5} {s['date']:<10} "
              f"{(s['start_time'] or '') + '-' + (s['end_time'] or ''):<11} {s['origin']:<7} {s['state']:<9} "
              f"{s['mode']:<14} {s['expected']:>3} {s['present']:>4} {s['on_duty']:>2} {s['not_in_list']:>9}")


def print_report(rep):
    s = rep["session"]
    print(f"\n{s['session_id']}  {s['subject_code']} {s['subject_name'] or ''}  lecturer {s['lecturer_id']}  "
          f"{s['hall']}  {s['date']} {s['start_time']}-{s['end_time']}\n"
          f"state {s['state']}  mode {s['mode']}  from {s['origin']}  unknown faces {s['unknown_faces']}  "
          f"override open until {rep['override_open_until'] or '-'}")
    for r in rep["records"]:
        extra = "" if r["in_session_list"] else "  <- not in the central system's list"
        ov = f"  override {r['override']['reason']} by {r['override']['by']}" if r["override"] else ""
        print(f"  {r['status']:<12} {r['method']:<17} {r['student_id']:<10} {r['name']:<18}{ov}{extra}")
    print("  " + "  ".join(f"{k} {v}" for k, v in rep["counts"].items() if v))


def write_csv(reps, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["session_id", "subject_code", "date", "hall", "lecturer_id", "student_id", "name", "status",
                    "method", "in_session_list", "time", "override_reason"])
        for rep in reps:
            s = rep["session"]
            for r in rep["records"]:
                w.writerow([s["session_id"], s["subject_code"], s["date"], s["hall"], s["lecturer_id"],
                            r["student_id"], r["name"], r["status"], r["method"], r["in_session_list"],
                            r["time"] or "", (r["override"] or {}).get("reason", "")])
    print(f"Saved {path}")


def pull(session=None, date=None, csv_path=None, as_json=False):
    reps = [call("GET", f"/api/v1/sessions/{session}/attendance")] if session else \
        call("GET", "/api/v1/attendance", params={"date": date or dt.date.today().isoformat()})
    if as_json:
        print(json.dumps(reps, indent=1))
    else:
        for rep in reps:
            print_report(rep)
    if csv_path:
        write_csv(reps, csv_path)


def menu():
    today = dt.date.today().isoformat()
    while True:
        print("\n=== APP 5: COLLEGE CENTRAL SYSTEM (simulator) ===\n"
              "1 Send student list (sim\\college_students.csv)\n2 Send today's sessions (sim\\timetable.csv)\n"
              "3 List sessions\n4 Pull one session's attendance\n5 Pull all of today's attendance (and save CSV)\n"
              "0 Quit")
        c = input("Choice: ").strip()
        if c == "1":
            send_students(input("CSV [sim\\college_students.csv]: ").strip() or "sim\\college_students.csv")
        elif c == "2":
            send_sessions(input("CSV [sim\\timetable.csv]: ").strip() or "sim\\timetable.csv", today)
        elif c == "3":
            show_list()
        elif c == "4":
            pull(session=input("Session ID: ").strip())
        elif c == "5":
            pull(date=today, csv_path=f"attendance_{today}.csv")
        elif c in ("0", ""):
            return


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("students")
    p.add_argument("--csv", required=True)
    p = sub.add_parser("sessions")
    p.add_argument("--csv", required=True)
    p.add_argument("--date", default=dt.date.today().isoformat())
    p = sub.add_parser("list")
    p.add_argument("--date")
    p = sub.add_parser("pull")
    p.add_argument("--session")
    p.add_argument("--date")
    p.add_argument("--csv", dest="csv_path")
    p.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.cmd == "students":
        send_students(a.csv)
    elif a.cmd == "sessions":
        send_sessions(a.csv, a.date)
    elif a.cmd == "list":
        show_list(a.date)
    elif a.cmd == "pull":
        pull(a.session, a.date, a.csv_path, a.json)
    else:
        menu()


if __name__ == "__main__":
    main()
