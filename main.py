"""
web_server.py - Main entry point (Phase 3: logging)
Keeps backward compatibility (direct execution)
"""
import logging
from gui import create_gui

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] %(levelname)s %(name)s: %(message)s',
        datefmt='%H:%M:%S'
    )
    app = create_gui()
    app.mainloop()
