"""Local text-to-speech with process-level interruption for reliable Pause."""

from __future__ import annotations

import multiprocessing
from threading import Event, Lock

_speech_lock = Lock()
_state_lock = Lock()
_process_context = multiprocessing.get_context("spawn")
_active_process: multiprocessing.Process | None = None
_active_cancel: Event | None = None
_speech_generation = 0


def _speak_in_worker(text: str, rate: int) -> None:
    """Initialize and run pyttsx3 inside a killable child process."""
    try:
        import pyttsx3

        engine = pyttsx3.init()
        engine.setProperty("rate", rate)
        engine.say(text)
        engine.runAndWait()
        engine.stop()
    except Exception as error:  # Audio drivers expose different failures.
        print(f"[Text-to-speech could not start: {error}]")
        raise SystemExit(1) from error


def _terminate(process: multiprocessing.Process) -> bool:
    """Terminate a started speech process, escalating only if it stays alive."""
    try:
        if process.pid is None:
            return False
        if process.is_alive():
            process.terminate()
            process.join(timeout=0.75)
        if process.is_alive() and hasattr(process, "kill"):
            process.kill()
            process.join(timeout=0.25)
        return True
    except (AssertionError, OSError, ValueError) as error:
        print(f"[Could not stop text-to-speech: {error}]")
        return False


def stop_speaking() -> bool:
    """Cancel active and queued speech immediately, if any has been requested."""
    global _speech_generation
    with _state_lock:
        _speech_generation += 1
        process = _active_process
        cancel = _active_cancel
    if cancel is not None:
        cancel.set()
    if process is None:
        return False
    if process.pid is None:
        # Process startup may still be in progress; speak() observes this event
        # as soon as start() returns and terminates before continuing audio.
        return True
    return _terminate(process)


def speak(text: str, rate: int = 175, stop_event: Event | None = None) -> bool:
    """Speak *text*; return False if the utterance was cancelled or failed."""
    clean_text = " ".join(text.split())
    if not clean_text or (stop_event and stop_event.is_set()):
        return False

    global _active_process, _active_cancel
    with _state_lock:
        generation = _speech_generation

    with _speech_lock:
        with _state_lock:
            if generation != _speech_generation or (stop_event and stop_event.is_set()):
                return False
            cancel = Event()
            process = _process_context.Process(
                target=_speak_in_worker,
                args=(clean_text, rate),
                daemon=True,
            )
            _active_process = process
            _active_cancel = cancel

        print(f"\nLIBRIS: {clean_text}\n")
        try:
            process.start()
            while process.is_alive():
                if cancel.is_set() or (stop_event and stop_event.is_set()):
                    _terminate(process)
                    return False
                process.join(timeout=0.05)
            return process.exitcode == 0 and not cancel.is_set() and not (stop_event and stop_event.is_set())
        except Exception as error:
            print(f"[Text-to-speech could not start: {error}]")
            return False
        finally:
            try:
                if process.pid is not None:
                    if process.is_alive():
                        _terminate(process)
                    process.join(timeout=1)
            except (AssertionError, OSError, ValueError):
                pass
            with _state_lock:
                if _active_process is process:
                    _active_process = None
                    _active_cancel = None
