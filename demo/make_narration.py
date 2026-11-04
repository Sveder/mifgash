"""Make the narration and the music bed for the Mifgash demo video v2.

Run with the TTS venv (local only, no cloud, no network):

    .venv-tts/bin/python demo/make_narration.py            # wavs + demo/narration.json + bed
    .venv-tts/bin/python demo/make_narration.py --check    # ffprobe every wav, check the sum

Input:  demo/narration.md (one '## <id> | <on screen>' block per shot).
Voice:  Kokoro-82M through kokoro-onnx, CPU. The model files are NOT in git:
        media/voices/kokoro-v1.0.onnx and media/voices/voices-v1.0.bin
        (or the folder in MIFGASH_TTS_MODELS).
Output: media/mifgash-demo/narration/<id>.wav (gitignored), demo/narration.json (in git),
        media/mifgash-demo/bed.wav (gitignored): a quiet pad of two chords made by ffmpeg
        from sine waves, peak about -28 dBFS. No third-party audio.

Each wav holds LEAD seconds of silence before the speech and TAIL seconds after it, so the
shot length = the wav length. The cut (manage.py public_cut) holds each shot that long.
"""
import argparse
import json
import os
import re
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NARRATION_MD = ROOT / "demo" / "narration.md"
NARRATION_JSON = ROOT / "demo" / "narration.json"
OUT = ROOT / "media" / "mifgash-demo"
WAVS = OUT / "narration"
BED = OUT / "bed.wav"
MODELS = Path(os.environ.get("MIFGASH_TTS_MODELS", ROOT / "media" / "voices"))
VOICE = os.environ.get("MIFGASH_TTS_VOICE", "am_michael")
SPEED = float(os.environ.get("MIFGASH_TTS_SPEED", "0.95"))
LEAD, TAIL = 0.4, 0.9
MIN_TOTAL, MAX_TOTAL = 150.0, 180.0
BED_DB = -28.0
# Spoken form for words the voice says wrong. The caption keeps the real word (shot["text"]).
SAY = {"Meta": "Mehta", "Muse": "Mewz"}


def parse(md_text):
    """Return [{id, screen, text}] from the '## <id> | <screen>' blocks."""
    shots = []
    for block in re.split(r"^## ", md_text, flags=re.M)[1:]:
        head, _, body = block.partition("\n")
        sid, _, screen = head.partition("|")
        text = " ".join(body.split())
        if sid.strip() and text:
            shots.append({"id": sid.strip(), "screen": screen.strip(), "text": text})
    return shots


def block_network():
    """Prove the run is local: any socket connect raises."""
    for var in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
        os.environ.pop(var, None)

    def refuse(*a, **k):
        raise RuntimeError("network blocked: make_narration.py must run offline")

    socket.socket.connect = refuse
    socket.create_connection = refuse


def synth(shots):
    import numpy as np
    import soundfile as sf
    from kokoro_onnx import Kokoro

    model, voices = MODELS / "kokoro-v1.0.onnx", MODELS / "voices-v1.0.bin"
    if not model.exists() or not voices.exists():
        sys.exit(f"missing voice model in {MODELS} (kokoro-v1.0.onnx, voices-v1.0.bin)")
    kokoro = Kokoro(str(model), str(voices))
    WAVS.mkdir(parents=True, exist_ok=True)
    start = 0.0
    for shot in shots:
        spoken = shot["text"]
        for word, say in SAY.items():
            spoken = re.sub(rf"\b{word}\b", say, spoken)
        samples, sr = kokoro.create(spoken, voice=VOICE, speed=SPEED, lang="en-us")
        audio = np.concatenate([np.zeros(int(LEAD * sr)), samples, np.zeros(int(TAIL * sr))])
        path = WAVS / f"{shot['id']}.wav"
        sf.write(path, audio, sr)
        secs = round(len(audio) / sr, 2)
        shot.update(words=len(shot["text"].split()), start=round(start, 2), seconds=secs,
                    speech_start=LEAD, wav=str(path.relative_to(ROOT)))
        start += secs
        print(f"{shot['id']:<16} {secs:6.2f} s  {shot['words']:3d} words")
    return round(start, 2)


def make_bed(total):
    """Two chords (C major 7, A minor 7), 8 s each, sine pad with a slow swell."""
    amp = 10 ** (BED_DB / 20) / 4  # four sines, so the peak stays under BED_DB
    c = [130.81, 164.81, 196.00, 246.94]
    a = [110.00, 130.81, 164.81, 196.00]
    voice = lambda fs: "+".join(f"sin(2*PI*{f}*t)" for f in fs)
    swell = "(0.75+0.25*sin(2*PI*t/8))"
    expr = f"{amp}*{swell}*if(lt(mod(t\\,16)\\,8)\\,{voice(c)}\\,{voice(a)})"
    BED.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", f"aevalsrc={expr}:s=24000:d={total}",
         "-af", f"lowpass=f=900,afade=t=in:d=3,afade=t=out:st={max(total - 4, 0)}:d=4",
         "-ac", "1", str(BED)],
        check=True)
    print(f"bed {BED.relative_to(ROOT)} {total} s, peak about {BED_DB} dBFS")


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return float(out.stdout.strip() or 0)


def check():
    data = json.loads(NARRATION_JSON.read_text())
    total, bad = 0.0, []
    for shot in data["shots"]:
        d = probe(ROOT / shot["wav"])
        total += d
        if d <= 0:
            bad.append(shot["id"])
        print(f"{shot['id']:<16} {d:6.2f} s")
    print(f"sum {total:.2f} s, {len(data['shots'])} wavs, {data['words']} words")
    ok = not bad and MIN_TOTAL <= total <= MAX_TOTAL
    if BED.exists():
        print(f"bed {probe(BED):.2f} s")
    print("OK" if ok else f"FAIL (no duration: {bad}; sum must be {MIN_TOTAL}-{MAX_TOTAL})")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="ffprobe the wavs and check the sum")
    args = ap.parse_args()
    if args.check:
        return check()
    block_network()
    shots = parse(NARRATION_MD.read_text())
    total = synth(shots)
    words = sum(s["words"] for s in shots)
    NARRATION_JSON.write_text(json.dumps(
        {"voice": f"Kokoro-82M {VOICE}", "speed": SPEED, "total_seconds": total, "words": words,
         "bed": str(BED.relative_to(ROOT)), "bed_db": BED_DB, "shots": shots}, indent=1) + "\n")
    make_bed(total)
    print(f"total {total} s, {words} words, {len(shots)} shots -> {NARRATION_JSON.relative_to(ROOT)}")
    return check()


if __name__ == "__main__":
    sys.exit(main())
