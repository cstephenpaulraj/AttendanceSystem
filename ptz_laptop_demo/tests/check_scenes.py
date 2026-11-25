"""Self-test: compare recognition on the simulated classroom pictures with sim\\expected.txt.

Needs app 3 running and the students enrolled.   python tests\\check_scenes.py --sim sim
"""
import argparse
import sys
from pathlib import Path

import cv2
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import config  # noqa: E402
from common.face_engine import FaceEngine  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim", default="sim")
    args = ap.parse_args()
    sim = Path(args.sim)
    expected = {}
    for line in (sim / "expected.txt").read_text().splitlines():
        if line.startswith("scene_"):
            name, people = line.split(": ", 1)
            expected[name] = [p.split("_")[0] for p in people.split(", ")]
    engine = FaceEngine()
    tot_ok = tot_miss = tot_wrong = tot_strangers_ok = tot_strangers = 0
    for name, ids in expected.items():
        img = cv2.imread(str(sim / "classroom" / name))
        faces = [f for f in engine.detect(img) if min(f[2], f[3]) >= config.MIN_FACE_PX_ATTEND]
        res = requests.post(f"{config.EDGE_URL}/api/identify",
                            json={"embeddings": [engine.embed(img, f).tolist() for f in faces]}, timeout=10).json()
        found = [r["student_id"] for r in res if r["student_id"]]
        students = [i for i in ids if i != "UNKNOWN"]
        ok = [i for i in students if i in found]
        wrong = [f for f in found if f not in students]
        strangers = ids.count("UNKNOWN")
        unknown_faces = sum(1 for r in res if not r["student_id"])
        tot_ok += len(ok); tot_miss += len(students) - len(ok); tot_wrong += len(wrong)
        tot_strangers += strangers; tot_strangers_ok += min(strangers, unknown_faces)
        print(f"{name}: faces found {len(faces)}/{len(ids)}  recognised {len(ok)}/{len(students)}"
              f"  wrong {wrong or 'none'}  strangers left unknown {min(strangers, unknown_faces)}/{strangers}")
    print(f"\nTOTAL recognised {tot_ok}/{tot_ok + tot_miss}, wrong matches {tot_wrong}, "
          f"strangers correctly unknown {tot_strangers_ok}/{tot_strangers}")
    sys.exit(0 if tot_wrong == 0 and tot_miss == 0 else 1)


if __name__ == "__main__":
    main()
