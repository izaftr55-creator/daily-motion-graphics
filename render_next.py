import datetime as dt
import json
import os
import subprocess
from pathlib import Path
from zoneinfo import ZoneInfo

APP_DIR = Path(__file__).resolve().parent
KIT_DIR = APP_DIR / "animation-kit"
OUT_DIR = APP_DIR / "output"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TOPICS = json.loads((APP_DIR / "topics.json").read_text(encoding="utf-8"))
TZ = ZoneInfo("Asia/Jakarta")


def main():
    run_num = int(os.environ.get("GITHUB_RUN_NUMBER", "1"))
    topic = TOPICS[(run_num - 1) % len(TOPICS)]
    now = dt.datetime.now(TZ)
    base = f"{now.strftime('%Y-%m-%d-%H%M')}-{topic['slug']}"

    spec_path = OUT_DIR / f"{base}.spec.json"
    mp4_path = OUT_DIR / f"{base}.mp4"
    txt_path = OUT_DIR / f"{base}.txt"

    spec = dict(topic["spec"])
    spec["out"] = str(mp4_path)
    spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")

    build_py = KIT_DIR / "skills" / topic["skill"] / "build.py"
    env = os.environ.copy()
    env.setdefault("PRODUCER_EXPERIMENTAL_FAST_CAPTURE", "false")

    print(f"Rendering {mp4_path.name} using skill '{topic['skill']}'...", flush=True)
    subprocess.run(["python3", str(build_py), str(spec_path)], env=env, check=True)

    txt_content = (
        f"Judul: {topic['title']}\n\n"
        f"Caption:\n{topic['caption']}\n\n"
        f"Hashtags:\n{topic['hashtags']}\n"
    )
    txt_path.write_text(txt_content, encoding="utf-8")
    print(f"Done: {mp4_path}", flush=True)

    gh_env = os.environ.get("GITHUB_ENV")
    if gh_env:
        with open(gh_env, "a", encoding="utf-8") as f:
            f.write(f"RELEASE_TAG=video-{base}\n")
            f.write(f"VIDEO_TITLE={topic['title']}\n")
            f.write(f"MP4_PATH={mp4_path}\n")
            f.write(f"TXT_PATH={txt_path}\n")


if __name__ == "__main__":
    main()
