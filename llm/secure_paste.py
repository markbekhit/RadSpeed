import logging
import subprocess
from cryptography.fernet import Fernet, InvalidToken
from config.config import config
from ui.utils import update_status
from pynput import keyboard
from pynput.keyboard import Controller
import time
import os
import ctypes

logger = logging.getLogger(__name__)

# Global variables
pressed_keys = set()
shortcut_active = False
last_execution_time = 0
DEBOUNCE_DELAY = 0.3  # Prevent repeated triggers within 300ms.


# Global keyboard controller
keyboard_controller = Controller()

def check_secure_paste_shortcut():
    """Checks if the currently pressed keys match the secure paste shortcut."""
    required_keys = config.secure_paste_shortcut.lower().split('+')
    return all(req in pressed_keys for req in required_keys)


def thread_safe_update_status(message):
    """Update status in a thread-safe manner."""
    config.root.after(0, update_status, message)


def initialize_secure_paste():
    """Starts the hotkey listener."""
    listener = keyboard.Listener(on_press=on_key_press, on_release=on_key_release)
    listener.start()
    logger.info("Secure paste initialized.")


def on_key_press(key):
    """Handles key press events."""
    global shortcut_active, last_execution_time

    try:
        # Add pressed key to the set
        key_name = key.char if hasattr(key, 'char') else key.name
        pressed_keys.add(key_name)
        logger.debug("Pressed: %s", pressed_keys)

        # Check if shortcut is pressed and debounce
        if check_secure_paste_shortcut() and not shortcut_active:
            current_time = time.time()
            if current_time - last_execution_time > DEBOUNCE_DELAY:
                secure_paste_report()
                shortcut_active = True
                last_execution_time = current_time

    except Exception as e:
        logger.error("Error in on_key_press: %s", e)


def on_key_release(key):
    """Handles key release events."""
    global shortcut_active

    try:
        # Remove released key from the set
        key_name = key.char if hasattr(key, 'char') else key.name
        pressed_keys.discard(key_name)
        logger.debug("Released: %s", pressed_keys)

        # Reset shortcut_active when all keys are released
        if not pressed_keys:
            shortcut_active = False

    except Exception as e:
        logger.error("Error in on_key_release: %s", e)

def secure_paste_report():
    """Securely pastes the generated report."""
    logger.debug("Secure paste report started.")
    try:
        # Decrypt report
        if config.current_encrypted_report and config.current_report_encryption_key:
            cipher_suite = Fernet(config.current_report_encryption_key.encode())
            try:
                decrypted_report = cipher_suite.decrypt(
                    config.current_encrypted_report.encode()
                ).decode()
            except InvalidToken:
                logger.error("Report decryption failed — stale report key.")
                thread_safe_update_status(
                    "Could not decrypt report. The report key is stale. Please re-record."
                )
                return

            # Inject text based on OS
            if os.name == "nt":  # Windows
                inject_text_windows(decrypted_report)
                injected = True
            else:  # macOS (or other systems)
                injected = inject_text_with_applescript(decrypted_report)

            # Only report success when injection actually happened — the
            # injector surfaces its own error status on failure.
            if injected:
                thread_safe_update_status("Report securely pasted.")
        else:
            thread_safe_update_status("No report available for secure paste.")
    except Exception as e:
        logger.error("Error during secure paste: %s", e)
        thread_safe_update_status(f"Error during secure paste: {e}")

########## FOR MACOS ##########

def classify_applescript_error(stderr: str):
    """Classify osascript stderr into the macOS permission that is missing.

    Returns "automation" (Privacy & Security → Automation, error -1743 on
    macOS 15), "accessibility" (Privacy & Security → Accessibility, error
    1002), or None for unrelated failures.
    """
    s = (stderr or "").lower()
    if "1743" in s or "not authorized" in s or "not authorised" in s:
        return "automation"
    if "1002" in s or "not allowed" in s or "assistant" in s or "accessibility" in s:
        return "accessibility"
    return None


_APPLESCRIPT_PERMISSION_MSGS = {
    "automation": (
        "Secure paste blocked by macOS. Allow RadSpeed to control System Events in "
        "System Settings → Privacy & Security → Automation."
    ),
    "accessibility": (
        "Secure paste blocked by macOS. Grant Accessibility access to RadSpeed in "
        "System Settings → Privacy & Security → Accessibility."
    ),
}


def inject_text_with_applescript(text):
    """Injects multiline text directly into the active window using AppleScript."""
    applescript_lines = []
    for line in text.splitlines():
        escaped_line = line.replace('\\', '\\\\').replace('"', '\\"')
        applescript_lines.append(f'keystroke "{escaped_line}"')
        applescript_lines.append('key code 36')  # Key code 36 is the Return key

    applescript = '''
    tell application "System Events"
        {}
    end tell
    '''.format('\n        '.join(applescript_lines))

    try:
        subprocess.run(["osascript", "-e", applescript], check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode(errors="replace") if e.stderr else ""
        permission = classify_applescript_error(stderr)
        if permission:
            logger.error("AppleScript keystroke blocked by macOS %s permission: %s", permission, stderr)
            thread_safe_update_status(_APPLESCRIPT_PERMISSION_MSGS[permission])
        else:
            logger.error("AppleScript failed: %s", stderr)
            thread_safe_update_status(f"Secure paste failed: {stderr.strip() or e}")
        return False


########## FOR WINDOWS ##########

# Define necessary constants
WM_CHAR = 0x0102
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
VK_RETURN = 0x0D

def inject_text_windows(text):
    """Injects text directly into the active window on Windows using ctypes."""
    user32 = ctypes.windll.user32
    
    # Get the handle of the active window
    hwnd = user32.GetForegroundWindow()
    
    # Send each character in the text
    for line in text.splitlines():
        for char in line:
            vk_code = ord(char)  # Virtual key code for the character
            user32.PostMessageW(hwnd, WM_CHAR, vk_code, 0)  # Send character
            time.sleep(0.01)  # Small delay to simulate human typing
        
        # Send Enter key after each line
        user32.PostMessageW(hwnd, WM_KEYDOWN, VK_RETURN, 0)  # Enter key down
        time.sleep(0.01)
        user32.PostMessageW(hwnd, WM_KEYUP, VK_RETURN, 0)  # Enter key up
