"""``python3 -m webui [output.html]`` -- render the student-side MVP demo.

``python3 -m webui --serve [--port 8000]`` -- serve it locally instead
(issue #179; live pipeline + persistent confirmation store).
"""

from .render import main

if __name__ == "__main__":
    raise SystemExit(main())
