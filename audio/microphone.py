"""Microphone input for LIBRIS."""

from __future__ import annotations

import io


def listen(duration: int = 6, sample_rate: int = 16_000) -> str:
    """Record a short command and return its transcription in lowercase.

    `sounddevice` handles Windows microphone capture. SpeechRecognition sends
    only the spoken command to its transcription service; book answers remain
    based solely on the selected local book.
    """
    try:
        import sounddevice as sd
        import soundfile as sf
        import speech_recognition as sr
    except ImportError:
        print("Voice input needs SpeechRecognition, sounddevice, and soundfile.")
        return ""

    try:
        sd.check_input_settings(samplerate=sample_rate, channels=1)
        print(f"Listening for {duration} seconds. Speak now.")
        recording = sd.rec(
            int(duration * sample_rate),
            samplerate=sample_rate,
            channels=1,
            dtype="int16",
        )
        sd.wait()

        wav_file = io.BytesIO()
        sf.write(wav_file, recording, sample_rate, format="WAV", subtype="PCM_16")
        wav_file.seek(0)
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_file) as source:
            audio = recognizer.record(source)
        text = recognizer.recognize_google(audio)
        print(f"You said: {text}")
        return text.lower()
    except sr.UnknownValueError:
        print("I heard audio but could not understand the words.")
    except sr.RequestError:
        print("Voice recognition is unavailable. Check your internet connection.")
    except Exception as error:  # PortAudio errors vary by Windows device/driver.
        print(f"Microphone problem: {error}")
    return ""
