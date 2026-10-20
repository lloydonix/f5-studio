"""The F5-TTS engine and the background generation queue.

One model, one GPU: every synthesis (queue paragraphs, pronunciation previews) goes through
Engine.lock, one at a time. Concurrent MPS work crashes Metal (see the max_workers=1 patch in
f5_tts/infer/utils_infer.py).
"""
import io, os, subprocess, threading, time, traceback
from collections import deque

import numpy as np
import soundfile as sf

from . import store

NFE = {"best": 32, "fast": 16}
SR = 24000


class Engine:
    def __init__(self):
        self.lock = threading.Lock()
        self.tts = None
        self.status = "not loaded"     # not loaded | loading | ready | error

    def load(self):
        if self.tts:
            return
        self.status = "loading"
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        try:
            from f5_tts.api import F5TTS
            self.tts = F5TTS()
            self.status = "ready"
        except Exception:
            self.status = "error"
            raise

    def synth(self, voice, text, quality="best"):
        """-> float32 numpy array at 24 kHz."""
        with self.lock:
            self.load()
            wav, sr, _ = self.tts.infer(str(store.voice_wav(voice["id"])), voice["transcript"], text,
                                        nfe_step=NFE.get(quality, 32), seed=42,
                                        show_info=lambda *a, **k: None, progress=None)
        assert sr == SR
        return np.asarray(wav, dtype=np.float32)

    def preview_wav_bytes(self, voice, text, quality="best"):
        buf = io.BytesIO()
        sf.write(buf, self.synth(voice, text, quality), SR, format="WAV")
        return buf.getvalue()


ENGINE = Engine()


class Worker:
    """Generates the missing paragraphs of queued projects, in order, one paragraph at a time."""

    def __init__(self):
        self.queue = deque()
        self.cv = threading.Condition()
        self.paused = True
        self.current = None        # {"project", "si", "pi", "text", "started"}
        self.last_error = None
        self.ratio = 6.5           # generation seconds per audio second, measured as we go
        self._recent = deque(maxlen=12)
        self._awake = None
        threading.Thread(target=self._run, daemon=True, name="tts-worker").start()

    # control
    def start(self, pid):
        with self.cv:
            if pid in self.queue:
                self.queue.remove(pid)
            self.queue.appendleft(pid)
            self.paused = False
            self.last_error = None
            self.cv.notify()

    def enqueue(self, pid):
        with self.cv:
            if pid not in self.queue:
                self.queue.append(pid)
            self.cv.notify()

    def pause(self):
        with self.cv:
            self.paused = True     # takes effect after the paragraph in progress

    def state(self):
        cur = self.current
        return {
            "running": not self.paused and bool(self.queue),
            "paused": self.paused, "queue": list(self.queue),
            "engine": ENGINE.status, "ratio": round(self.ratio, 2),
            "current": cur and {k: cur[k] for k in ("project", "si", "pi", "text")} | {
                "elapsed": round(time.time() - cur["started"], 1)},
            "error": self.last_error,
        }

    # loop
    def _next_paragraph(self):
        """(project, voice, paragraph) for the first queued project with work left, else None."""
        while self.queue:
            pid = self.queue[0]
            try:
                p = store.Project(pid)
                todo = [x for s in p.sections() for x in s["paras"] if not x["dur"]]
            except KeyError:
                todo = []
            if todo:
                return p, store.voice(p.meta["voice"]), todo[0]
            self.queue.popleft()
        return None

    def _run(self):
        while True:
            with self.cv:
                while self.paused or not self.queue:
                    self._keep_awake(False)
                    self.current = None
                    self.cv.wait()
                job = self._next_paragraph()
                if not job:
                    continue
            self._keep_awake(True)
            p, voice, para = job
            self.current = {"project": p.id, "si": para["si"], "pi": para["pi"], "text": para["text"], "started": time.time()}
            try:
                t0 = time.time()
                audio = ENGINE.synth(voice, para["text"], p.meta.get("quality", "best"))
                gen = time.time() - t0
                p.clip_dir.mkdir(exist_ok=True)
                name = para["key"] + ".wav"
                tmp = p.clip_dir / (para["key"] + ".tmp.wav")
                sf.write(str(tmp), audio, SR)
                tmp.replace(p.clip_dir / name)
                dur = len(audio) / SR
                p.add_clip(para["key"], name, dur, gen)
                if dur > 0.5:
                    self._recent.append(gen / dur)
                    self.ratio = sum(self._recent) / len(self._recent)
            except Exception as e:
                traceback.print_exc()
                self.last_error = f"{type(e).__name__}: {e}"
                with self.cv:
                    self.paused = True

    def _keep_awake(self, on):
        if on and not (self._awake and self._awake.poll() is None):
            self._awake = subprocess.Popen(["/usr/bin/caffeinate", "-i", "-w", str(os.getpid())])
        elif not on and self._awake and self._awake.poll() is None:
            self._awake.terminate()
            self._awake = None


WORKER = Worker()


def transcribe(wav_path):
    """Whisper (via F5's helper) on a reference clip. Holds the engine lock so it never overlaps synthesis."""
    with ENGINE.lock:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        from f5_tts.infer.utils_infer import transcribe as _t
        return _t(str(wav_path)).strip()
