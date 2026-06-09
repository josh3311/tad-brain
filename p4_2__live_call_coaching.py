"""
Live Call Coach — P4-2

Provides real-time coaching cues during a live call by consuming
transcribed or typed utterances, detecting patterns (filler words,
negativity, long silences, interruptions), and emitting actionable
suggestions to stdout.

This module runs standalone (stdin simulation) or can be imported and
driven programmatically.
"""

import sys
import re
import threading
import queue
import time
from typing import Optional, List


class LiveCallCoach:
    """
    Real-time call coaching engine.

    Push transcribed utterances via push_utterance() and the engine emits
    coaching suggestions on a background thread.
    """

    FILLERS = re.compile(r"\b(uh+|um+|ah+|er+|like+|you know)\b", re.IGNORECASE)
    NEGATIVE = re.compile(
        r"\b(can't|cannot|won't|impossible|never|no way|terrible|awful|hate)\b",
        re.IGNORECASE,
    )
    QUESTION = re.compile(r"\?")
    INTERRUPTION = re.compile(r"^\-\-|^\.\.\.|^hold on|^wait", re.IGNORECASE)
    GRATITUDE = re.compile(r"\b(thanks|thank you|appreciate)\b", re.IGNORECASE)

    def __init__(self, silence_threshold_sec: float = 3.0) -> None:
        self._q: queue.Queue[str] = queue.Queue()
        self._running = False
        self._worker: Optional[threading.Thread] = None
        self._silence_threshold = silence_threshold_sec
        self._last_utterance_time: Optional[float] = None
        self._lock = threading.Lock()
        self._utterance_count = 0
        self._filler_count = 0
        self._question_count = 0

    def start(self) -> None:
        """Begin the background coaching loop."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._last_utterance_time = time.time()
        self._worker = threading.Thread(target=_run_worker, args=(self,), daemon=True)
        self._worker.start()

    def stop(self) -> None:
        """Signal the background loop to finish and wait for it."""
        with self._lock:
            self._running = False
        if self._worker is not None:
            self._q.put("")  # unblock queue get
            self._worker.join(timeout=2.0)

    def push_utterance(self, text: str) -> None:
        """Feed a new transcribed utterance into the coach."""
        if text is None:
            return
        self._q.put(text)

    def _tick(self) -> bool:
        """Process one coaching tick. Returns True if loop should continue."""
        with self._lock:
            running = self._running
        if not running:
            return False

        try:
            utterance = self._q.get(timeout=0.5)
        except queue.Empty:
            self._check_silence()
            return True

        if not utterance and not self._running:
            return False

        now = time.time()
        self._last_utterance_time = now
        self._utterance_count += 1

        cues: List[str] = []

        fillers = self.FILLERS.findall(utterance)
        if fillers:
            self._filler_count += len(fillers)
            if len(fillers) >= 2:
                cues.append("[COACH] Reduce filler words — stay confident.")
            else:
                cues.append("[COACH] Watch the filler.")

        negative = self.NEGATIVE.findall(utterance)
        if negative:
            cues.append("[COACH] Rephrase positively — focus on what you CAN do.")

        interruption = self.INTERRUPTION.search(utterance)
        if interruption:
            cues.append("[COACH] Pause — let the other person finish.")

        gratitude = self.GRATITUDE.findall(utterance)
        if gratitude:
            cues.append("[COACH] Great — acknowledgment builds rapport.")

        questions = self.QUESTION.findall(utterance)
        if questions:
            self._question_count += len(questions)
            if self._question_count > 5 and self._utterance_count < 10:
                cues.append("[COACH] Balance questions with value statements.")

        ratio = self._filler_count / max(self._utterance_count, 1)
        if ratio > 0.25 and self._utterance_count >= 4:
            cues.append("[COACH] Heavy filler usage detected — slow down and breathe.")

        for cue in cues:
            print(cue, flush=True)

        return True

    def _check_silence(self) -> None:
        if self._last_utterance_time is None:
            return
        elapsed = time.time() - self._last_utterance_time
        if elapsed > self._silence_threshold:
            print(
                "[COACH] Long silence — acknowledge, summarize, or ask a clarifier.",
                flush=True,
            )
            self._last_utterance_time = time.time()


def _run_worker(coach: LiveCallCoach) -> None:
    while coach._tick():
        pass


def _demo_stream(coach: LiveCallCoach) -> None:
    coach.start()
    print("[SYSTEM] Live Call Coach started. Type utterances (empty line to exit).", flush=True)
    try:
        for line in sys.stdin:
            stripped = line.strip()
            if stripped == "":
                break
            coach.push_utterance(stripped)
    except KeyboardInterrupt:
        pass
    finally:
        coach.stop()
        print("[SYSTEM] Live Call Coach stopped.", flush=True)


if __name__ == "__main__":
    coach = LiveCallCoach(silence_threshold_sec=4.0)
    _demo_stream(coach)