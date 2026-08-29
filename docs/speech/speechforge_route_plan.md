# SpeechForge route truth

SpeechForge now has governed local route wiring for Whisper.cpp STT and Kokoro ONNX synthetic reading voices. Heavy runtime imports remain in the separate `elysia_speechforge` subprocess.

STT requires an approved-root local media file, explicit processing-rights and consent truth, a 30-minute/512 MiB ceiling, a preview plan, and an exact expiring one-time approval before saving TXT/JSON/SRT/VTT artifacts. Central records contain model, duration, language, segment count, artifact/hash, consent posture and IDs—never raw audio or transcript text.

Kokoro accepts only catalog voices and text, never reference audio or voice embeddings. Saved WAV generation requires a preview plan and exact approval. Audit/trace contain text hash/length, voice, sample rate, duration, artifact/hash and synthetic-audio truth—never input text or WAV bytes.

Voice cloning is deliberately unavailable by design. Kokoro/model licensing and provenance remain externally unverified, so TTS is a local lab reading-voice capability rather than production-enabled identity media.

All four bounded transcript artifact formats—TXT, JSON, SRT, and VTT—are live through the same exact-approved path. Machine output must be checked against source audio before consequential use; Elysia does not label a transcript as ground truth.
