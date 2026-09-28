# LIBRIS

LIBRIS is a local, voice-friendly book companion. It stores a personal library,
opens imported books in a desktop reader, reads the active section aloud,
remembers progress, and answers using selected-book text rather than the
internet.

## Run
```powershell
cd "C:\Users\HP\Documents\New project\AI Experiments\Projects\LIBRIS"
python -m pip install -r requirements.txt
python main.py
```

For the most reliable Windows launch, double-click `run_libris.bat`. It always
uses the project `.venv`, so the PDF and EPUB reader packages are available.
The application opens with a black, light-purple, and red desktop interface.
Use **Import book** to browse to a file anywhere on the computer. Alternatively,
put a `.txt`, `.pdf`, or `.epub` file in `books/inbox` and choose **Import from
Inbox**. An imported book opens in the reader immediately; use **Read aloud**
to follow the highlighted spoken section, enter a section number to choose
where narration starts, and use **Previous** or **Next** to move.

Voice input uses `SpeechRecognition`, `sounddevice`, and `soundfile`. It does
not need PyAudio, which is commonly difficult to install on newer Python versions.
