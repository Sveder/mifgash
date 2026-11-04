# Credits: demo video sound

## Narration voice (video v3, the submitted video)
- **ElevenLabs** text-to-speech, voice Brian, at natural speed. The audio of each line is used uncut.

## Narration voice (video v2)
- **Kokoro-82M** text-to-speech model by hexgrad, licence Apache-2.0
  (https://huggingface.co/hexgrad/Kokoro-82M). Voice `am_michael`, from `voices-v1.0.bin`.
- Run through **kokoro-onnx** 0.6.1 (MIT, https://github.com/thewh1teagle/kokoro-onnx) on
  **ONNX Runtime** (MIT), CPU only, offline. The text goes to phonemes with **espeak-ng**
  (GPL-3.0, through `espeakng-loader` and `phonemizer`), used as a tool at build time only.
  No espeak-ng code is in this repo or in the video.
- The model files are not in this repo (`media/voices/`, gitignored).
- The task asked for piper with the voice en_US-ljspeech-high. That voice file is not on the
  build server, and the task allowed no download, so the narration uses the local Kokoro model.

## Music bed
- Made by `demo/make_narration.py` with ffmpeg `aevalsrc` from plain sine waves (two chords,
  C major 7 and A minor 7, peak about -28 dBFS). No third-party audio file.

## Trademarks
- OpenClaw, Meta AI, Muse Spark and Instinct are trademarks of their owners. The site and the
  video show their real logos only to say which assistants can use the Mifgash API. No owner
  endorses Mifgash. Each logo file and its source: `planner/static/planner/logos/CREDITS.txt`.
