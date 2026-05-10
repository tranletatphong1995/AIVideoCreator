"""Subprocess worker for VieNeu TTS.

Running VieNeu in a child process keeps native llama/onnx crashes away from
the PyQt UI process and lets the main app fail early with a useful message.
"""

import argparse
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate one VieNeu TTS wav file")
    parser.add_argument("--mode", choices=["standard", "turbo"], default="standard")
    parser.add_argument("--text", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--voice-id", default="")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(os.path.abspath(args.output)) or ".", exist_ok=True)

    from vieneu import Vieneu

    tts = Vieneu(mode=args.mode)
    voice = None
    if args.voice_id:
        voice = tts.get_preset_voice(args.voice_id)

    if voice is not None:
        audio = tts.infer(text=args.text, voice=voice)
    else:
        audio = tts.infer(text=args.text)

    tts.save(audio, args.output)
    if not os.path.exists(args.output) or os.path.getsize(args.output) <= 44:
        raise RuntimeError(f"TTS did not create a valid wav file: {args.output}")

    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
