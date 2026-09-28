"""Reliable local text-to-speech for LIBRIS."""

from __future__ import annotations

from threading import Lock


_speech_lock = Lock()


def speak(text: str, rate: int = 175) -> bool:
    """Say *text* aloud and return whether Windows text-to-speech succeeded."""
    clean_text = " ".join(text.split())
    if not clean_text:
        return False

    print(f"\nLIBRIS: {clean_text}\n")
    try:
        import pyttsx3

        with _speech_lock:
            engine = pyttsx3.init()
            engine.setProperty("rate", rate)
            engine.say(clean_text)
            engine.runAndWait()
            engine.stop()
        return True
    except Exception as error:  # Windows audio drivers can raise varied errors.
        print(f"[Text-to-speech could not start: {error}]")
        return False
