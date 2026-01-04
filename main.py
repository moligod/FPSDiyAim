import tkinter as tk
from tkinter import ttk, colorchooser, filedialog, messagebox
import ctypes
from ctypes import wintypes
import json
import os
import sys
import base64
from PIL import Image, ImageTk
import pystray
from pystray import MenuItem as item
import threading
import winreg
import subprocess

# Windows API constants for click-through
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020

class CrosshairOverlay(tk.Toplevel):
    def __init__(self, master, config):
        super().__init__(master)
        self.config = config
        self.title("Overlay")
        
        # Remove decorations
        self.overrideredirect(True)
        self.wm_attributes("-topmost", True)
        
        # Transparency
        self.bg_color = "#000001"
        self.config_bg(self.bg_color)
        self.wm_attributes("-transparentcolor", self.bg_color)
        
        # Dimensions (fixed small area around center to minimize impact, but large enough for big crosshairs)
        self.width = 200
        self.height = 200
        
        # Canvas
        self.canvas = tk.Canvas(self, width=self.width, height=self.height, 
                                bg=self.bg_color, highlightthickness=0)
        self.canvas.pack()
        
        # Initial Draw
        self.redraw()
        
        # Apply click-through
        self.after(100, self.apply_click_through)
        
        self.image_ref = None

    def config_bg(self, color):
        self.configure(bg=color)

    def apply_click_through(self):
        try:
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            if hwnd == 0:
                hwnd = self.winfo_id()
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style = style | WS_EX_TRANSPARENT | WS_EX_LAYERED
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        except Exception as e:
            print(f"Error setting click-through: {e}")

    def redraw(self):
        self.canvas.delete("all")
        cx, cy = self.width // 2, self.height // 2
        
        size = self.config['size'].get()
        color = self.config['color'].get()
        thickness = self.config['thickness'].get()
        dot = self.config['dot'].get()
        style = self.config['style'].get()
        
        if style == "Cross" or style == "Both" or style == "十字" or style == "混合":
            # Horizontal
            self.canvas.create_line(cx - size//2, cy, cx + size//2, cy, 
                                    fill=color, width=thickness)
            # Vertical
            self.canvas.create_line(cx, cy - size//2, cx, cy + size//2, 
                                    fill=color, width=thickness)
            
        if style == "Dot" or style == "Both" or style == "圆点" or style == "混合":
            r = dot // 2
            self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, 
                                    fill=color, outline=color)
        
        if style == "Circle" or style == "圆圈":
            r = size // 2
            self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                                    outline=color, width=thickness)
                                    
        if style == "Custom" or style == "自定义":
            image_path = self.config.get('image_path', {}).get()
            if image_path and os.path.exists(image_path):
                try:
                    # Use binary read and base64 encoding to support non-ASCII paths (e.g. Chinese)
                    with open(image_path, "rb") as f:
                        img_data = f.read()
                    b64_data = base64.b64encode(img_data)
                    self.image_ref = tk.PhotoImage(data=b64_data)
                    self.canvas.create_image(cx, cy, image=self.image_ref, anchor="center")
                except Exception as e:
                    print(f"Error loading image: {e}")

    def set_position(self, x, y):
        # x, y are center coordinates
        # We need to convert to top-left for geometry
        tl_x = x - self.width // 2
        tl_y = y - self.height // 2
        self.geometry(f"{self.width}x{self.height}+{tl_x}+{tl_y}")

class ControlPanel:
    def __init__(self):
        self.root = tk.Tk()
        
        # Check Admin Status
        self.is_admin = ctypes.windll.shell32.IsUserAnAdmin()
        title = "moligod小工具"
        if self.is_admin:
            title += " - 管理员模式"
        else:
            title += " - 非管理员模式"
            
        self.root.title(title)
        try:
            self.root.iconbitmap(self.resource_path("tx.ico"))
        except:
            pass
        self.root.geometry("360x540")
        self.root.resizable(False, False)
        
        self.overlay = None
        
        # Configuration Variables
        self.screen_w = self.root.winfo_screenwidth()
        self.screen_h = self.root.winfo_screenheight()
        
        self.pos_x = tk.StringVar(value=str(self.screen_w // 2))
        self.pos_y = tk.StringVar(value=str(self.screen_h // 2))
        
        # Auto update on change
        self.pos_x.trace_add("write", self.update_pos)
        self.pos_y.trace_add("write", self.update_pos)
        
        self.config = {
            'size': tk.IntVar(value=20),
            'thickness': tk.IntVar(value=2),
            'color': tk.StringVar(value="#00FF00"),
            'dot': tk.IntVar(value=4),
            'style': tk.StringVar(value="十字"),
            'image_path': tk.StringVar(value=""),
            'force_admin': tk.BooleanVar(value=False)
        }
        
        self.presets = {}
        self.current_preset_name = tk.StringVar()
        
        self.load_config()
        
        self.create_widgets()
        
        self.start_overlay()
        
        # Trigger style change logic to set button state and load image if needed
        # Call this AFTER starting overlay so update_overlay works
        self.on_style_change(event="Startup") 
        self.update_preset_list()
        
        # Add keyboard bindings to the Control Panel for fine tuning
        self.root.bind("<Up>", lambda e: self.adjust_pos(0, -1))
        self.root.bind("<Down>", lambda e: self.adjust_pos(0, 1))
        self.root.bind("<Left>", lambda e: self.adjust_pos(-1, 0))
        self.root.bind("<Right>", lambda e: self.adjust_pos(1, 0))
        
        self.root.protocol("WM_DELETE_WINDOW", self.quit_application)
        
        # Start tray icon in separate thread
        self.tray_icon = None
        
        self.root.mainloop()

    def check_startup(self):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
            try:
                winreg.QueryValueEx(key, "MoliCrosshair")
                self.startup_btn.configure(text="开机自启：开")
            except FileNotFoundError:
                self.startup_btn.configure(text="开机自启：关")
            winreg.CloseKey(key)
        except Exception as e:
            print(f"Error checking startup: {e}")

    def toggle_startup(self):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_ALL_ACCESS)
            try:
                # Try to get value to see if it exists
                winreg.QueryValueEx(key, "MoliCrosshair")
                # If exists, delete it (Turn Off)
                winreg.DeleteValue(key, "MoliCrosshair")
                self.startup_btn.configure(text="开机自启：关")
            except FileNotFoundError:
                # If not exists, create it (Turn On)
                exe_path = os.path.abspath(sys.argv[0])
                winreg.SetValueEx(key, "MoliCrosshair", 0, winreg.REG_SZ, exe_path)
                self.startup_btn.configure(text="开机自启：开")
            winreg.CloseKey(key)
        except Exception as e:
            messagebox.showerror("错误", f"无法修改开机启动设置：{e}")

    def minimize_to_tray(self):
        self.root.withdraw()
        self.create_tray_icon()

    def create_tray_icon(self):
        if self.tray_icon:
            return
            
        try:
            icon_image = Image.open(self.resource_path("tx.ico"))
        except:
            # Fallback if icon load fails
            icon_image = Image.new('RGB', (64, 64), color = (73, 109, 137))
            
        def show_window(icon, item):
            icon.stop()
            self.root.after(0, self.root.deiconify)
            self.tray_icon = None

        def quit_app(icon, item):
            icon.stop()
            self.root.after(0, self.quit_application)

        menu = (item('显示设置', show_window, default=True), item('退出程序', quit_app))
        self.tray_icon = pystray.Icon("name", icon_image, "自定义准心", menu)
        
        # Run tray icon in a separate thread to avoid blocking main loop
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def restart_as_admin(self):
        try:
            # Set force_admin to True and save config
            self.config['force_admin'].set(True)
            self.save_config()
            
            # Re-run the program with admin rights
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
            sys.exit() # Directly exit without calling quit_application again which saves config
        except Exception as e:
            messagebox.showerror("错误", f"无法以管理员身份重启：{e}")

    def restart_as_normal(self):
        try:
            # Set force_admin to False and save config
            self.config['force_admin'].set(False)
            self.save_config()
            
            # Use explorer to launch the app, which typically de-elevates to user level
            # Quote the path to handle spaces
            exe_path = f'"{sys.executable}"'
            subprocess.Popen(f'explorer {exe_path}', shell=True)
            sys.exit() # Directly exit
        except Exception as e:
            messagebox.showerror("错误", f"无法重启：{e}")

    def quit_application(self):
        self.save_config()
        self.root.quit()
        sys.exit()

    def create_widgets(self):
        self.root.columnconfigure(0, weight=1)
        
        # Presets (Moved to Position Frame)
        
        # Style
        style_frame = ttk.LabelFrame(self.root, text="样式")
        style_frame.pack(fill="x", padx=10, pady=5)
        style_frame.columnconfigure(1, weight=1)
        
        ttk.Label(style_frame, text="类型:").grid(row=0, column=0, padx=5, pady=5)
        type_cb = ttk.Combobox(style_frame, textvariable=self.config['style'], 
                               values=["十字", "圆点", "混合", "圆圈", "自定义"], state="readonly")
        type_cb.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        type_cb.bind("<<ComboboxSelected>>", self.on_style_change)
        
        self.img_btn = ttk.Button(style_frame, text="选择图片", command=self.choose_image)
        self.img_btn.grid(row=0, column=2, padx=5, pady=5)
        
        ttk.Label(style_frame, text="颜色:").grid(row=1, column=0, padx=5, pady=5)
        ttk.Button(style_frame, text="选择", command=self.choose_color).grid(row=1, column=1, columnspan=2, padx=5, pady=5, sticky="ew")
        
        # Size Controls
        size_frame = ttk.LabelFrame(self.root, text="尺寸")
        size_frame.pack(fill="x", padx=10, pady=5)
        size_frame.columnconfigure(1, weight=1)
        
        self.add_slider(size_frame, "大小", self.config['size'], 5, 100, 2)
        self.add_slider(size_frame, "粗细", self.config['thickness'], 1, 10, 3)
        self.add_slider(size_frame, "圆点大小", self.config['dot'], 1, 20, 4)

        # Position Controls
        pos_frame = ttk.LabelFrame(self.root, text="位置 (使用方向键微调)")
        pos_frame.pack(fill="x", padx=10, pady=5)
        pos_frame.columnconfigure(1, weight=1)
        pos_frame.columnconfigure(3, weight=1)
        
        ttk.Label(pos_frame, text="X:").grid(row=0, column=0, padx=5)
        x_entry = tk.Entry(pos_frame, textvariable=self.pos_x, width=10)
        x_entry.grid(row=0, column=1, padx=5, sticky="ew")
        
        ttk.Label(pos_frame, text="Y:").grid(row=0, column=2, padx=5)
        y_entry = tk.Entry(pos_frame, textvariable=self.pos_y, width=10)
        y_entry.grid(row=0, column=3, padx=5, sticky="ew")
        
        # Center and Drag buttons in same row
        ctrl_btn_frame = ttk.Frame(pos_frame)
        ctrl_btn_frame.grid(row=1, column=0, columnspan=4, pady=5, sticky="ew", padx=5)
        ctrl_btn_frame.columnconfigure(0, weight=1)
        ctrl_btn_frame.columnconfigure(1, weight=1)

        ttk.Button(ctrl_btn_frame, text="居中", command=self.center_pos).grid(row=0, column=0, sticky="ew", padx=2)
        
        drag_btn = ttk.Button(ctrl_btn_frame, text="按住拖动准心")
        drag_btn.grid(row=0, column=1, sticky="ew", padx=2)
        drag_btn.bind("<ButtonPress-1>", self.drag_start)
        drag_btn.bind("<B1-Motion>", self.drag_move)
        
        # Presets (Moved here)
        preset_frame = ttk.LabelFrame(pos_frame, text="预设配置")
        preset_frame.grid(row=3, column=0, columnspan=4, sticky="ew", padx=5, pady=5)
        preset_frame.columnconfigure(1, weight=1)
        
        ttk.Label(preset_frame, text="方案:").grid(row=0, column=0, padx=5, pady=5)
        self.preset_cb = ttk.Combobox(preset_frame, textvariable=self.current_preset_name)
        self.preset_cb.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.preset_cb.bind("<<ComboboxSelected>>", self.load_preset)
        self.update_preset_list()
        
        # Set placeholder
        self.preset_cb.set("<--下拉选择预设-->")
        
        btn_frame = ttk.Frame(preset_frame)
        btn_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=5, pady=5)
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)
        btn_frame.columnconfigure(2, weight=1)
        btn_frame.columnconfigure(3, weight=1)
        
        ttk.Button(btn_frame, text="保存", command=self.save_preset).grid(row=0, column=0, sticky="ew", padx=2)
        ttk.Button(btn_frame, text="删除", command=self.delete_preset).grid(row=0, column=1, sticky="ew", padx=2)
        ttk.Button(btn_frame, text="导入", command=self.import_preset).grid(row=0, column=2, sticky="ew", padx=2)
        ttk.Button(btn_frame, text="分享", command=self.export_preset).grid(row=0, column=3, sticky="ew", padx=2)

        # System
        sys_frame = ttk.Frame(self.root)
        sys_frame.pack(fill="x", padx=10, pady=10)
        sys_frame.columnconfigure(0, weight=1)
        sys_frame.columnconfigure(1, weight=1)
        sys_frame.columnconfigure(2, weight=1)
        
        ttk.Button(sys_frame, text="隐藏到托盘", command=self.minimize_to_tray).grid(row=0, column=0, sticky="ew", padx=2)
        
        self.startup_btn = ttk.Button(sys_frame, text="开机自启：关", command=self.toggle_startup)
        self.startup_btn.grid(row=0, column=1, sticky="ew", padx=2)
        
        if not self.is_admin:
             ttk.Button(sys_frame, text="管理员启动", command=self.restart_as_admin).grid(row=0, column=2, sticky="ew", padx=2)
        else:
             ttk.Button(sys_frame, text="取消管理员", command=self.restart_as_normal).grid(row=0, column=2, sticky="ew", padx=2)
        
        # Check initial startup status
        self.check_startup()
        
        # Status
        self.status_label = ttk.Label(self.root, text="作者moligod（B站抖音快手小红书同名）炸撤离点群727712220", foreground="green")
        self.status_label.pack(side="bottom", pady=(0, 5))
        ttk.Label(self.root, text="如若出现问题优先管理员启动", foreground="red").pack(side="bottom", pady=(5, 0))

    def add_slider(self, parent, label, var, min_val, max_val, row):
        ttk.Label(parent, text=label).grid(row=row, column=0, padx=5, pady=2)
        scale = ttk.Scale(parent, from_=min_val, to=max_val, variable=var, orient="horizontal", command=self.update_overlay)
        scale.grid(row=row, column=1, sticky="ew", padx=5, pady=2)

    def choose_color(self):
        color = colorchooser.askcolor(color=self.config['color'].get())[1]
        if color:
            self.config['color'].set(color)
            self.update_overlay()
            
    def on_style_change(self, event=None):
        style = self.config['style'].get()
        # Always enable image button so user can click it directly to switch mode
        # If user switches dropdown manually, we check if image path is needed
        # Only prompt for image if it's a user interaction (event is not None) or if path is truly empty during init
        if (style == "Custom" or style == "自定义"):
            if not self.config['image_path'].get():
                # If switched to Custom but no image, prompt to choose
                # Use 'after' to avoid blocking the event loop immediately
                if event and event != "Startup": # Only prompt if user manually triggered, not on startup
                    self.root.after(100, self.choose_image)
            else:
                # If we have a path, ensure overlay updates
                self.update_overlay()
            
        self.update_overlay()

    def choose_image(self):
        file_path = filedialog.askopenfilename(
            title="选择图片",
            filetypes=[("Image Files", "*.png;*.gif;*.ppm;*.pnm")]
        )
        if file_path:
            self.config['image_path'].set(file_path)
            # Auto switch to Custom style
            self.config['style'].set("自定义")
            self.update_overlay()

    def drag_start(self, event):
        self._drag_start_x = event.x_root
        self._drag_start_y = event.y_root
        try:
            self._start_pos_x = int(float(self.pos_x.get()))
            self._start_pos_y = int(float(self.pos_y.get()))
        except:
            self._start_pos_x = self.screen_w // 2
            self._start_pos_y = self.screen_h // 2

    def drag_move(self, event):
        dx = event.x_root - self._drag_start_x
        dy = event.y_root - self._drag_start_y
        self.pos_x.set(str(self._start_pos_x + dx))
        self.pos_y.set(str(self._start_pos_y + dy))
        self.update_pos()

    def start_overlay(self):
        if self.overlay:
            self.overlay.destroy()
        self.overlay = CrosshairOverlay(self.root, self.config)
        self.update_pos()

    def update_overlay(self, _=None):
        if self.overlay:
            self.overlay.redraw()

    def update_pos(self, *args):
        if self.overlay:
            try:
                # Handle potential float strings or empty strings
                x_str = self.pos_x.get().strip()
                y_str = self.pos_y.get().strip()
                
                if not x_str: x = self.screen_w // 2
                else: x = int(float(x_str))
                
                if not y_str: y = self.screen_h // 2
                else: y = int(float(y_str))
                
                self.overlay.set_position(x, y)
            except Exception as e:
                # print(f"Invalid position input: {e}")
                pass

    def center_pos(self):
        self.pos_x.set(str(self.screen_w // 2))
        self.pos_y.set(str(self.screen_h // 2))
        self.update_pos()

    def adjust_pos(self, dx, dy):
        try:
            current_x = int(float(self.pos_x.get()))
            current_y = int(float(self.pos_y.get()))
        except:
            current_x = self.screen_w // 2
            current_y = self.screen_h // 2
            
        self.pos_x.set(str(current_x + dx))
        self.pos_y.set(str(current_y + dy))
        self.update_pos()

    def update_preset_list(self):
        preset_names = list(self.presets.keys())
        self.preset_cb['values'] = preset_names

    def save_preset(self):
        name = self.current_preset_name.get().strip()
        if not name:
            return
            
        # Capture current settings
        preset_data = {
            "size": self.config['size'].get(),
            "thickness": self.config['thickness'].get(),
            "color": self.config['color'].get(),
            "dot": self.config['dot'].get(),
            "style": self.config['style'].get(),
            "image_path": self.config['image_path'].get()
        }
        
        self.presets[name] = preset_data
        self.update_preset_list()
        
    def load_preset(self, event=None):
        name = self.current_preset_name.get()
        if name == "<--下拉选择预设-->":
            return
            
        if name in self.presets:
            data = self.presets[name]
            self.config['size'].set(data.get("size", 20))
            self.config['thickness'].set(data.get("thickness", 2))
            self.config['color'].set(data.get("color", "#00FF00"))
            self.config['dot'].set(data.get("dot", 4))
            self.config['style'].set(data.get("style", "十字"))
            self.config['image_path'].set(data.get("image_path", ""))
            
            # Refresh overlay
            self.on_style_change(event="PresetLoad")
            
    def delete_preset(self):
        name = self.current_preset_name.get()
        if name in self.presets:
            del self.presets[name]
            self.current_preset_name.set("")
            self.update_preset_list()

    def export_preset(self):
        name = self.current_preset_name.get()
        if not name or name not in self.presets:
            return
            
        data = self.presets[name]
        
        # Check if custom image
        if data.get('style') in ["Custom", "自定义"]:
            proceed = messagebox.askokcancel(
                "分享警告", 
                "该方案使用了自定义图片。\n\n分享方案仅包含配置信息，不包含图片文件。\n接收方需要手动设置同名图片才能正常显示。\n\n是否继续？"
            )
            if not proceed:
                return

        # Add name to exported data for convenience
        data['name'] = name
        
        file_path = filedialog.asksaveasfilename(
            title="分享方案",
            defaultextension=".json",
            initialfile=f"{name}.json",
            filetypes=[("JSON Files", "*.json")]
        )
        
        if file_path:
            try:
                with open(file_path, "w", encoding='utf-8') as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
            except Exception as e:
                print(f"Error exporting preset: {e}")

    def import_preset(self):
        file_path = filedialog.askopenfilename(
            title="导入方案",
            filetypes=[("JSON Files", "*.json")]
        )
        
        if file_path:
            try:
                with open(file_path, "r", encoding='utf-8') as f:
                    data = json.load(f)
                
                # Use name from file or filename
                name = data.get('name', os.path.splitext(os.path.basename(file_path))[0])
                
                # Sanitize data to ensure it has required fields
                clean_data = {
                    "size": data.get("size", 20),
                    "thickness": data.get("thickness", 2),
                    "color": data.get("color", "#00FF00"),
                    "dot": data.get("dot", 4),
                    "style": data.get("style", "十字"),
                    "image_path": data.get("image_path", "")
                }
                
                self.presets[name] = clean_data
                self.current_preset_name.set(name)
                self.update_preset_list()
                self.load_preset() # Auto apply imported preset
                
            except Exception as e:
                print(f"Error importing preset: {e}")

    def resource_path(self, relative_path):
        """ Get absolute path to resource, works for dev and for PyInstaller """
        try:
            # PyInstaller creates a temp folder and stores path in _MEIPASS
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")

        return os.path.join(base_path, relative_path)

    def get_config_path(self):
        app_data = os.getenv('LOCALAPPDATA')
        if not app_data:
            app_data = os.path.expanduser('~')
        
        app_dir = os.path.join(app_data, 'MoligodCrosshair')
        if not os.path.exists(app_dir):
            os.makedirs(app_dir)
            
        return os.path.join(app_dir, 'config.json')

    def load_config(self):
        config_path = self.get_config_path()
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding='utf-8') as f:
                    data = json.load(f)
                    self.pos_x.set(str(data.get("pos_x", self.screen_w // 2)))
                    self.pos_y.set(str(data.get("pos_y", self.screen_h // 2)))
                    
                    self.config['size'].set(data.get("size", 20))
                    self.config['thickness'].set(data.get("thickness", 2))
                    self.config['color'].set(data.get("color", "#00FF00"))
                    self.config['dot'].set(data.get("dot", 4))
                    self.config['style'].set(data.get("style", "十字"))
                    self.config['image_path'].set(data.get("image_path", ""))
                    self.config['force_admin'].set(data.get("force_admin", False))
                    
                    self.presets = data.get("presets", {})
            except Exception as e:
                print(f"Error loading config: {e}")

    def save_config(self):
        try:
            x = int(float(self.pos_x.get()))
            y = int(float(self.pos_y.get()))
        except:
            x = self.screen_w // 2
            y = self.screen_h // 2
            
        data = {
            "pos_x": x,
            "pos_y": y,
            "size": self.config['size'].get(),
            "thickness": self.config['thickness'].get(),
            "color": self.config['color'].get(),
            "dot": self.config['dot'].get(),
            "style": self.config['style'].get(),
            "image_path": self.config['image_path'].get(),
            "force_admin": self.config['force_admin'].get(),
            "presets": self.presets
        }
        try:
            with open(self.get_config_path(), "w", encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving config: {e}")

def check_force_admin():
    # Helper to check config file before initializing UI
    try:
        # Re-use logic to get config path (duplicated briefly for standalone function)
        app_data = os.getenv('LOCALAPPDATA')
        if not app_data: app_data = os.path.expanduser('~')
        config_path = os.path.join(app_data, 'MoligodCrosshair', 'config.json')
        
        if os.path.exists(config_path):
            with open(config_path, "r", encoding='utf-8') as f:
                data = json.load(f)
                return data.get("force_admin", False)
    except:
        pass
    return False

if __name__ == "__main__":
    # Check if we should force admin
    should_be_admin = check_force_admin()
    is_admin = ctypes.windll.shell32.IsUserAnAdmin()
    
    if should_be_admin and not is_admin:
        # Relaunch as admin
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
        sys.exit()
    else:
        ControlPanel()
