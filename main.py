"""
web_server.py - Main entry point
Keeps backward compatibility (direct execution)
"""
from gui import create_gui

if __name__ == "__main__":
    app = create_gui()
    app.mainloop()
