"""homework-pilot ingestion + OCR pipeline (issues #110, #111).

This package implements the upload -> page -> sub-question pipeline,
student-ID round-trip matching with a teacher confirmation queue,
per-item OCR with reliability scores and threshold routing,
an evaluation harness, and the human-in-the-loop manual-entry fallback
that keeps the pilot moving while OCR accuracy is being measured.

All matching ambiguity goes to the teacher review queue — the system
never auto-guesses a student identity.
"""
