"""Main entry point (logging setup + GUI)."""
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
