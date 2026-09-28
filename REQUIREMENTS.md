# LIBRIS requirements
## Version 1 features
- Import TXT, PDF, and EPUB books; select one active book.
- Read the active book aloud, automatically save paragraph progress, and resume later.
- Show reading progress.
- Answer and summarize using only extracted text from the selected book.
- Support typed input and optional microphone input.
## Quality rules
- Keep books and progress local by default.
- Do not invent an answer when no selected-book evidence is found.
- Handle unavailable microphones, files, and optional packages without crashing.
- Keep audio, AI, library, and application-flow code separated.
- Do not put API keys in source code. Version 1 needs none.
## Later improvements
- GUI, semantic embeddings, natural-language LLM answers, accounts, cloud sync, bookmarks, and annotations.
