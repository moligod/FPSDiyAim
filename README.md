# DIY FPS Crosshair

This is a lightweight, portable, and customizable crosshair overlay for FPS games. It uses Python and Tkinter to create a transparent window that sits on top of your game.

## Features

- **Always on Top**: Stays visible over your game (Fullscreen Borderless / Windowed mode recommended).
- **Click-Through**: The overlay ignores mouse clicks so you can play your game without interference.
- **Customizable**:
  - Position (X/Y coordinates)
  - Color
  - Size and Thickness
  - Style (Cross, Dot, Circle, or combined)
- **Portable**: Single Python script.
- **Persistent**: Saves your settings to `config.json`.

## Requirements

- Python 3.x installed.
- Windows OS (uses Windows API for click-through functionality).

## How to Run

1. Open a terminal or command prompt in this folder.
2. Run the script:
   ```bash
   python main.py
   ```
3. A "Crosshair Settings" window will appear, along with the crosshair overlay (defaulted to the center of your screen).

## Usage

1. **Adjust Position**:
   - Use the **Arrow Keys** while the "Crosshair Settings" window is focused to nudge the crosshair 1 pixel at a time.
   - Enter coordinates manually in the X/Y fields and click "Apply Pos".
   - Click "Center" to reset to the middle of the screen.

2. **Customize Style**:
   - Change the Type (Cross, Dot, Circle).
   - Pick a Color.
   - Adjust sliders for Size, Thickness, and Dot Size.

3. **Playing**:
   - Once set up, you can minimize the "Crosshair Settings" window.
   - Click on your game window. The crosshair will remain visible and will not block your mouse input.

4. **Closing**:
   - Click "Close Crosshair" in the settings window or simply close the settings window.
   - Your settings will be saved automatically.

## Note on Fullscreen Games

This overlay works best with games running in **Borderless Windowed** or **Windowed** mode. Exclusive Fullscreen mode in some games might override the "Always on Top" property of the overlay.
