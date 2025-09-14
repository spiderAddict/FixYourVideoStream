import subprocess
from pathlib import Path

output_dir = Path("test_videos")
output_dir.mkdir(exist_ok=True)

files = [
    ("video_fr.mp4", "fra"),
    ("video_en.mkv", "eng"),
    ("video_fr.mkv", "fr"),
    ("video_es.avi", "spa"),
    ("video_unknown.mov", None),
]

for filename, lang in files:
    filepath = output_dir / filename
    if filepath.exists():
        continue
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=2",
        "-f", "lavfi", "-i", "sine=frequency=1000:duration=2",
        "-c:v", "libx264",
        "-c:a", "aac",
    ]
    if lang:
        cmd += ["-metadata:s:a:0", f"language={lang}"]
    cmd += [str(filepath)]
    subprocess.run(cmd, check=True)
print("Fichiers générés dans", output_dir)
