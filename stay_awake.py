import utils.net
import utils.clients
import utils.http_session
import utils.transport
import utils.session
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import ctypes
from pynput.mouse import Controller
from pynput.keyboard import Controller as KeyController, Key
import atexit

# Windows API constants
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002


class StayAwake:
    def __init__(self, root):
        self.root = root
        self.root.title("Stay Awake")
        self.root.geometry("420x480")
        self.root.resizable(False, False)

        # Handle window close event to ensure cleanup
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.running = False
        self.thread = None
        self.mouse_controller = Controller()
        self.keyboard_controller = KeyController()
        self._toggle = 1  # Direction flag: +1 or -1, flips each cycle

        # Register cleanup on exit
        atexit.register(self.cleanup)

        self.build_gui()

    def build_gui(self):
        # Title
        title = ttk.Label(self.root, text="Stay Awake", font=("Arial", 16, "bold"))
        title.pack(pady=12)

        # Main frame for settings
        main_frame = ttk.Frame(self.root)
        main_frame.pack(pady=10, padx=15, fill="both", expand=True)

        # Interval frame
        interval_frame = ttk.Frame(main_frame)
        interval_frame.pack(pady=8, fill="x")
        ttk.Label(interval_frame, text="Jiggle interval (min:sec):", width=22).pack(side="left")
        self.interval_var = tk.StringVar(value="2:00")
        interval_entry = ttk.Entry(interval_frame, textvariable=self.interval_var, width=12)
        interval_entry.pack(side="left", padx=5)
        ttk.Label(interval_frame, text="(e.g., 2:30)", foreground="gray").pack(side="left")

        # Distance frame
        distance_frame = ttk.Frame(main_frame)
        distance_frame.pack(pady=8, fill="x")
        ttk.Label(distance_frame, text="Jiggle distance (pixels):", width=22).pack(side="left")
        self.distance_var = tk.StringVar(value="2")
        distance_entry = ttk.Entry(distance_frame, textvariable=self.distance_var, width=12)
        distance_entry.pack(side="left", padx=5)
        ttk.Label(distance_frame, text="(keep small)", foreground="gray").pack(side="left")

        # Separator
        ttk.Separator(main_frame, orient="horizontal").pack(pady=10, fill="x")

        # Options frame
        options_frame = ttk.LabelFrame(main_frame, text="Options", padding=10)
        options_frame.pack(pady=5, fill="x")

        self.display_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="Also keep display on", variable=self.display_var).pack(anchor="w", pady=4)

        self.jiggle_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="Enable mouse jiggle", variable=self.jiggle_var).pack(anchor="w", pady=4)

        self.f15_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="Send F15 keypress (invisible input signal)", variable=self.f15_var).pack(anchor="w", pady=4)

        # Status label
        self.status_var = tk.StringVar(value="Status: Inactive")
        status_label = ttk.Label(self.root, textvariable=self.status_var, font=("Arial", 10, "bold"))
        status_label.pack(pady=10)

        # Start/Stop button
        button_frame = ttk.Frame(self.root)
        button_frame.pack(pady=12)
        self.button = ttk.Button(button_frame, text="Start", command=self.toggle_awake, width=20)
        self.button.pack()

    def parse_interval(self):
        """Parse min:sec format, return seconds. Returns None if invalid."""
        try:
            interval_str = self.interval_var.get().strip()
            if not interval_str:
                messagebox.showerror("Invalid Input", "Interval cannot be empty.")
                return None

            if ':' in interval_str:
                parts = interval_str.split(':')
                minutes = int(parts[0])
                seconds = int(parts[1])
                if minutes < 0 or seconds < 0 or seconds >= 60:
                    raise ValueError
                total_seconds = minutes * 60 + seconds
            else:
                # Assume it's just minutes
                total_seconds = int(interval_str) * 60

            if total_seconds <= 0:
                raise ValueError
            return total_seconds
        except (ValueError, IndexError):
            messagebox.showerror("Invalid Input", "Use format: min:sec (e.g., 2:30) or just minutes.")
            return None

    def parse_distance(self):
        """Parse distance, return pixels. Returns None if invalid."""
        try:
            distance_str = self.distance_var.get().strip()
            if not distance_str:
                distance = 2  # Fallback default
            else:
                distance = int(distance_str)

            if distance <= 0:
                raise ValueError
            return distance
        except ValueError:
            messagebox.showerror("Invalid Input", "Distance must be a positive integer (default: 2).")
            return None

    def toggle_awake(self):
        if self.running:
            self.stop_awake()
        else:
            self.start_awake()

    def start_awake(self):
        interval = self.parse_interval()
        distance = self.parse_distance()

        if interval is None or distance is None:
            return

        self.running = True
        self.button.config(text="Stop", state="normal")
        self.status_var.set("Status: Active ✓")

        # Set execution state to keep system awake
        self.set_keep_awake(True)

        # Start background thread for mouse jiggling if enabled
        if self.jiggle_var.get():
            self.thread = threading.Thread(
                target=self.jiggle_loop,
                args=(interval, distance),
                daemon=True
            )
            self.thread.start()

    def stop_awake(self):
        self.running = False
        self.button.config(text="Start", state="normal")
        self.status_var.set("Status: Inactive")

        # Release the keep-awake lock
        self.set_keep_awake(False)

        # Wait for jiggle thread to finish (if running)
        if self.thread is not None and self.thread.is_alive():
            self.thread.join(timeout=1)
            self.thread = None

    def set_keep_awake(self, awake):
        """Set or release the Windows keep-awake lock."""
        try:
            if awake:
                # Combine flags: continuous + system required + optionally display
                flags = ES_CONTINUOUS | ES_SYSTEM_REQUIRED
                if self.display_var.get():
                    flags |= ES_DISPLAY_REQUIRED
                ctypes.windll.kernel32.SetThreadExecutionState(ctypes.c_ulong(flags))
            else:
                # Release the lock by setting only ES_CONTINUOUS
                ctypes.windll.kernel32.SetThreadExecutionState(ctypes.c_ulong(ES_CONTINUOUS))
        except Exception as e:
            messagebox.showerror("Error", f"Failed to set keep-awake: {e}")

    def jiggle_loop(self, interval, distance):
        """Background loop that jiggles the mouse at regular intervals."""
        while self.running:
            # Sleep in small chunks (~0.1s) so Stop responds quickly
            remaining = interval
            chunk_size = 0.1
            while remaining > 0 and self.running:
                sleep_time = min(chunk_size, remaining)
                time.sleep(sleep_time)
                remaining -= sleep_time

            # Jiggle if still running and jiggle is enabled
            if self.running and self.jiggle_var.get():
                self.do_jiggle(distance)

    def do_jiggle(self, distance):
        """Move cursor in alternating direction (ping-pong) and optionally send F15 keypress."""
        try:
            current_pos = self.mouse_controller.position
            x, y = current_pos

            # Move cursor in current direction (toggle * distance)
            move_distance = self._toggle * distance
            self.mouse_controller.position = (x + move_distance, y)

            # Send F15 keypress if enabled
            if self.f15_var.get():
                try:
                    self.keyboard_controller.press(Key.f15)
                    self.keyboard_controller.release(Key.f15)
                except Exception:
                    pass

            # Flip toggle for next cycle (alternates between +1 and -1)
            self._toggle *= -1
        except Exception:
            # Silently handle jiggle errors (e.g., permission issues, screen locked)
            pass

    def on_closing(self):
        """Handle window close button."""
        if self.running:
            self.stop_awake()
        self.cleanup()
        self.root.destroy()

    def cleanup(self):
        """Ensure the keep-awake lock is always released before exit."""
        try:
            ctypes.windll.kernel32.SetThreadExecutionState(ctypes.c_ulong(ES_CONTINUOUS))
        except Exception:
            pass


def main():
    root = tk.Tk()
    app = StayAwake(root)
    root.mainloop()


if __name__ == "__main__":
    main()
