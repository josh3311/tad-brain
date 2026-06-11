"""voice_input.py — minimal core for raised silence threshold."""

from __future__ import annotations
import sys


def pcm_energy(frame: bytes, sample_width: int = 2) -> float:
    """Calculate average absolute amplitude of a raw PCM frame."""
    if not frame or sample_width <= 0:
        return 0.0
    count = len(frame) // sample_width
    if count == 0:
        return 0.0
    total = 0
    for i in range(0, len(frame), sample_width):
        sample = frame[i:i + sample_width]
        val = int.from_bytes(sample, "little", signed=True)
        total += abs(val)
    return total / count


def is_speech(energy: float, threshold: float = 1200.0) -> bool:
    """Return True if energy exceeds the raised silence threshold."""
    return energy > threshold


def voice_activity_detect(frames: list[bytes], threshold: float = 1200.0) -> list[bytes]:
    """Return frames that exceed the silence threshold."""
    return [f for f in frames if is_speech(pcm_energy(f), threshold)]


class SpeechAggregator:
    """Storage layer that accumulates speech frames and summarizes them."""

    def __init__(self, threshold: float = 1200.0) -> None:
        self.threshold = threshold
        self.frames: list[bytes] = []
        self.energies: list[float] = []

    def add(self, frame: bytes) -> bool:
        """Classify *frame* and store it if it is speech. Return True if stored."""
        e = pcm_energy(frame)
        if is_speech(e, self.threshold):
            self.frames.append(frame)
            self.energies.append(e)
            return True
        return False

    def summary(self) -> dict[str, float | int]:
        """Return aggregate statistics over stored speech frames."""
        if not self.frames:
            return {
                "frames": 0,
                "avg_energy": 0.0,
                "max_energy": 0.0,
                "min_energy": 0.0,
            }
        avg = sum(self.energies) / len(self.energies)
        return {
            "frames": len(self.frames),
            "avg_energy": avg,
            "max_energy": max(self.energies),
            "min_energy": min(self.energies),
        }


def _tests() -> None:
    """Quick self-checks."""
    silence = b"\x00\x00" * 10
    assert pcm_energy(silence) == 0.0

    frame = (1000).to_bytes(2, "little", signed=True) * 5
    assert pcm_energy(frame) == 1000.0

    assert is_speech(1000.0) is False
    assert is_speech(1500.0) is True

    frames = [b"\x00\x00", (2000).to_bytes(2, "little", signed=True)]
    assert len(voice_activity_detect(frames)) == 1

    agg = SpeechAggregator()
    assert agg.add(silence) is False
    assert agg.add((2000).to_bytes(2, "little", signed=True)) is True
    s = agg.summary()
    assert s["frames"] == 1
    assert s["avg_energy"] == 2000.0

    empty = SpeechAggregator()
    es = empty.summary()
    assert es["frames"] == 0
    assert es["avg_energy"] == 0.0

    print("All tests passed.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        _tests()