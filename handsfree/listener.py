"""Microphone -> utterances, fully on-device, using faster-whisper.

Audio is split into utterances with a simple energy detector: speech starts when the level
rises well above the room's noise floor and ends after `silence` seconds of quiet. Each
utterance is transcribed locally and the audio is dropped straight away. Anything that isn't
a command is discarded later by the Session, so overheard talk never gets typed.

Needs: pip install faster-whisper sounddevice numpy
"""

import queue
import sys
from collections import deque
from typing import Iterator

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

SAMPLE_RATE = 16000
FRAME = 480  # 30 ms
FRAMES_PER_SECOND = SAMPLE_RATE // FRAME

# Biases Whisper toward the command vocabulary and the spelling of the wake word.
PROMPT = (
    "{wake}, open Slack, type hi team and send it. Open Cursor. Open Notes. Open Firefox and "
    "open YouTube in it. Open VS Code. Open Notion. {wake}, new tab. Scratch that. Confirm."
)


class Listener:
    def __init__(
        self,
        model: str = "base.en",
        device: int | str | None = None,
        silence: float = 1.0,
        max_seconds: float = 300.0,  # Infina caps one hands-free capture at five minutes
        sensitivity: float = 3.0,
        wake_word: str = "Hi Abhishek",
    ):
        self.prompt = PROMPT.format(wake=wake_word)
        self.device = device
        self.silence_frames = int(silence * FRAMES_PER_SECOND)
        self.max_frames = int(max_seconds * FRAMES_PER_SECOND)
        self.sensitivity = sensitivity
        print(f"Loading Whisper model '{model}' (downloaded once, then cached)...", file=sys.stderr)
        self.model = WhisperModel(model, device="cpu", compute_type="int8")

    def transcribe(self, audio: np.ndarray) -> str:
        segments, _ = self.model.transcribe(
            audio,
            language="en",
            beam_size=1,
            initial_prompt=self.prompt,
            condition_on_previous_text=False,
        )
        # Whisper invents text for noise ("Thank you."); drop segments it isn't sure are speech.
        kept = [s.text for s in segments if s.no_speech_prob < 0.6 and s.avg_logprob > -1.0]
        return " ".join(t.strip() for t in kept).strip()

    def utterances(self) -> Iterator[str]:
        frames: queue.Queue[np.ndarray] = queue.Queue()

        def on_audio(data, _frames, _time, status):
            if status:
                print(f"[mic] {status}", file=sys.stderr)
            frames.put(data[:, 0].copy())

        with sd.InputStream(
            samplerate=SAMPLE_RATE, blocksize=FRAME, channels=1, dtype="float32",
            device=self.device, callback=on_audio,
        ):
            floor = self._calibrate(frames)
            print("Listening. Speak a command (Ctrl+C to stop).", file=sys.stderr)
            # Keep the 300 ms before speech starts so the first word is never clipped.
            preroll: deque[np.ndarray] = deque(maxlen=10)
            speech: list[np.ndarray] = []
            loud_run = quiet_run = 0
            while True:
                frame = frames.get()
                level = float(np.sqrt(np.mean(frame**2)))
                threshold = max(floor * self.sensitivity, 0.006)
                if not speech:
                    preroll.append(frame)
                    loud_run = loud_run + 1 if level > threshold else 0
                    if loud_run >= 3:  # 90 ms of sound, so clicks and taps don't count
                        speech = list(preroll)
                        quiet_run = 0
                    else:
                        floor = 0.98 * floor + 0.02 * level  # follow slow changes in room noise
                    continue
                speech.append(frame)
                quiet_run = quiet_run + 1 if level < threshold else 0
                if quiet_run >= self.silence_frames or len(speech) >= self.max_frames:
                    audio = np.concatenate(speech)
                    speech, loud_run = [], 0
                    preroll.clear()
                    if len(audio) < SAMPLE_RATE * 0.4:
                        continue
                    print("[transcribing...]", file=sys.stderr)
                    # Audio keeps queueing while this runs, so speech right after isn't lost.
                    text = self.transcribe(audio)
                    if text:
                        yield text

    def _calibrate(self, frames: "queue.Queue[np.ndarray]") -> float:
        print("Measuring room noise for 1 second, stay quiet...", file=sys.stderr)
        levels = [float(np.sqrt(np.mean(frames.get() ** 2))) for _ in range(FRAMES_PER_SECOND)]
        return float(np.median(levels))
