import sys
from gui import MuMuGUI

def main():
    try:
        app = MuMuGUI()
        app.mainloop()
    except KeyboardInterrupt:
        print("\nShutdown requested by user. Exiting...")
        sys.exit(0)
    except Exception as e:
        print(f"CRITICAL: Unhandled exception during application runtime: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
