import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import pyautogui
import pytesseract
import re
import interception
import keyboard
from PIL import Image, ImageOps, ImageEnhance
import json
import os

pytesseract.pytesseract.tesseract_cmd = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
MIN_KEY_DELAY = 0.05
EXTRA_DELAY = 0.01
SETTINGS_FILE = "settings.json"

# ---------------- Globals ----------------
running = False
r_running = False
skill_entries = {}
threads = []
r_combo_active = None
r_delay_entry = None
extra_region_value = ""

# ---------------- Helper ----------------
def safe_sleep(seconds):
    """Uyku sırasında makro durdurulursa hemen çıkabilsin."""
    interval = 0.05
    while seconds > 0 and running:
        time.sleep(min(interval, seconds))
        seconds -= interval

# ---------------- OCRThinker ----------------
class OCRThinker(threading.Thread):
    def __init__(self, text_vars):
        super().__init__()
        self.text_vars = text_vars
        self.regions = {"HP": None, "MP": None}
        self.hp_trigger = 30
        self.mp_trigger = 50
        self.hp_key = "1"
        self.mp_key = "2"
        self.running = True

    def set_region(self, key, region):
        self.regions[key] = region

    def preprocess_image(self, img):
        img = img.convert('L')
        img = ImageOps.invert(img)
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2.5)
        w, h = img.size
        img = img.resize((w*2, h*2), Image.Resampling.LANCZOS)
        return img

    def extract_percent(self, text):
        match = re.search(r'(\d+)\s*/\s*(\d+)', text)
        if match:
            current = int(match.group(1))
            total = int(match.group(2))
            return int((current / total) * 100) if total != 0 else 0
        match = re.search(r'(\d+)%', text)
        if match:
            return int(match.group(1))
        return None

    def run(self):
        while self.running:
            for key in ["HP", "MP"]:
                region = self.regions[key]
                if region:
                    img = pyautogui.screenshot(region=region)
                    img = self.preprocess_image(img)
                    config = r'--psm 7 -c tessedit_char_whitelist=0123456789/%'
                    text = pytesseract.image_to_string(img, config=config).strip()
                    percent = self.extract_percent(text)
                    if percent is not None:
                        self.text_vars[key].set(f"{key}: {percent}% ({text})")
                        if key == "HP" and percent <= self.hp_trigger:
                            interception.key_down(self.hp_key)
                            safe_sleep(MIN_KEY_DELAY + EXTRA_DELAY)
                            interception.key_up(self.hp_key)
                        elif key == "MP" and percent <= self.mp_trigger:
                            interception.key_down(self.mp_key)
                            safe_sleep(MIN_KEY_DELAY + EXTRA_DELAY)
                            interception.key_up(self.mp_key)
                    else:
                        self.text_vars[key].set(f"{key}: ? ({text})")
                else:
                    self.text_vars[key].set(f"{key} bölgesi seçilmedi.")
            time.sleep(0.2)

    def stop(self):
        self.running = False

# ---------------- Region Selector ----------------
class RegionSelector:
    def __init__(self, callback):
        self.callback = callback
        self.start_x = self.start_y = None
        self.rect = None
        self.root = tk.Tk()
        self.root.attributes('-fullscreen', True)
        self.root.attributes('-alpha', 0.3)
        self.root.attributes('-topmost', True)
        self.root.configure(bg='black')
        self.canvas = tk.Canvas(self.root, bg='black')
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Button-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.root.mainloop()

    def on_press(self, event):
        self.start_x, self.start_y = event.x, event.y
        self.rect = self.canvas.create_rectangle(self.start_x, self.start_y, self.start_x, self.start_y, outline='red', width=2)

    def on_drag(self, event):
        self.canvas.coords(self.rect, self.start_x, self.start_y, event.x, event.y)

    def on_release(self, event):
        x1, y1 = self.start_x, self.start_y
        x2, y2 = event.x, event.y
        region = (min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
        img = pyautogui.screenshot(region=region)
        img = img.convert('L')
        text = pytesseract.image_to_string(img, config=r'--psm 7').strip()
        self.callback(region, text)
        self.root.destroy()
# ---------------- Extra/Kordinat OCR ----------------
class ExtraOCRThinker(threading.Thread):
    def __init__(self, text_var):
        super().__init__()
        self.text_var = text_var
        self.region = None
        self.running = True

    def set_region(self, region):
        self.region = region

    def preprocess_image(self, img):
        img = img.convert('L')
        img = ImageOps.invert(img)
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(3.0)
        w, h = img.size
        img = img.resize((w*2, h*2), Image.Resampling.LANCZOS)
        return img

    def run(self):
        while self.running:
            if kordinat_active_var.get() and self.region:
                img = pyautogui.screenshot(region=self.region)
                img = self.preprocess_image(img)
                text = pytesseract.image_to_string(img, config=r'--psm 7').strip()
                self.text_var.set(f"Kordinat: {text}")
            else:
                self.text_var.set("Kordinat bölgesi seçilmedi veya pasif")
            time.sleep(0.2)

    def stop(self):
        self.running = False

# ---------------- Makro Worker ----------------
def skill_worker(key, active_var, entry_key, entry_delay):
    global running, extra_region_value, r_running
    while running:
        if active_var.get():
            if kordinat_active_var.get() and extra_thinker.region:
                img = pyautogui.screenshot(region=extra_thinker.region)
                img = extra_thinker.preprocess_image(img)
                current_value = pytesseract.image_to_string(img, config='--psm 7').strip()
                if extra_region_value and current_value != extra_region_value:
                    running = False
                    r_running = False
                    status_label.config(text="Makro: DURDU (Kordinat değişti!)")
                    set_widgets_state("normal")
                    break
            real_key = entry_key.get().strip()
            try:
                delay = float(entry_delay.get())
            except:
                delay = 1.0
            if real_key and running:
                interception.key_down(real_key)
                safe_sleep(MIN_KEY_DELAY + EXTRA_DELAY)
                interception.key_up(real_key)
            safe_sleep(delay)
        else:
            safe_sleep(0.1)

def r_worker():
    global r_running
    while r_running:
        if r_combo_active.get():
            try:
                r_delay = float(r_delay_entry.get())
            except:
                r_delay = 0.2
            interception.key_down("r")
            safe_sleep(MIN_KEY_DELAY + EXTRA_DELAY)
            interception.key_up("r")
            safe_sleep(r_delay)
        else:
            safe_sleep(0.05)

# ---------------- GUI ----------------
root = tk.Tk()
root.title("GALİP BABA Makro + HP/MP + Kordinat")
root.geometry("700x700")
root.attributes("-topmost", True)

notebook = ttk.Notebook(root)
notebook.pack(fill="both", expand=True)

# ---- Macro Tab ----
macro_tab = ttk.Frame(notebook)
notebook.add(macro_tab, text="Makro")
status_label = tk.Label(macro_tab, text="Makro: DURDU", font=("Arial", 14))
status_label.pack(pady=10)

macro_frame = tk.Frame(macro_tab)
macro_frame.pack(pady=10)
tk.Label(macro_frame, text="Aktif").grid(row=0, column=0, padx=5)
tk.Label(macro_frame, text="Skill Tuşu").grid(row=0, column=1, padx=5)
tk.Label(macro_frame, text="Bekleme (saniye)").grid(row=0, column=2, padx=5)

skill_entries = {}
for idx, key in enumerate("1234567890", start=1):
    active_var = tk.BooleanVar(value=True)
    chk = tk.Checkbutton(macro_frame, variable=active_var)
    chk.grid(row=idx, column=0, padx=5)
    entry_key = tk.Entry(macro_frame, width=10)
    entry_key.insert(0, key)
    entry_key.grid(row=idx, column=1, padx=5, pady=2)
    entry_delay = tk.Entry(macro_frame, width=10)
    entry_delay.insert(0, "1.0")
    entry_delay.grid(row=idx, column=2, padx=5, pady=2)
    skill_entries[key] = (active_var, entry_key, entry_delay)

r_frame = tk.Frame(macro_tab)
r_frame.pack(pady=5)
r_combo_active = tk.BooleanVar(value=False)
r_combo_checkbox = tk.Checkbutton(r_frame, text="R Combo Aktif", variable=r_combo_active)
r_combo_checkbox.grid(row=0, column=0, padx=5)
tk.Label(r_frame, text="R Gecikmesi (saniye):").grid(row=0, column=1, padx=5)
r_delay_entry = tk.Entry(r_frame, width=5)
r_delay_entry.insert(0, "0.2")
r_delay_entry.grid(row=0, column=2, padx=5)

# Hotkeys
keyboard.add_hotkey("-", lambda: start_macro())
keyboard.add_hotkey("*", lambda: stop_macro())

# ---- Can/Mana Tab ----
hp_mp_tab = ttk.Frame(notebook)
notebook.add(hp_mp_tab, text="Can/Mana")
text_vars = {"HP": tk.StringVar(), "MP": tk.StringVar()}
text_vars["HP"].set("HP bölgesi seçilmedi.")
text_vars["MP"].set("MP bölgesi seçilmedi.")
tk.Label(hp_mp_tab, textvariable=text_vars["HP"], font=("Arial", 14), fg="red").pack(pady=5)
tk.Label(hp_mp_tab, textvariable=text_vars["MP"], font=("Arial", 14), fg="blue").pack(pady=5)

thinker = OCRThinker(text_vars)
thinker.daemon = True
thinker.start()

def select_region(key):
    RegionSelector(callback=lambda region, text: (
        thinker.set_region(key, region),
        text_vars[key].set(f"{key} Bölgesi: {region} | Şu anki değer: {text}"),
        save_settings()
    ))

tk.Button(hp_mp_tab, text="HP Bölgesi Seç", command=lambda: select_region("HP")).pack(pady=5)
tk.Button(hp_mp_tab, text="MP Bölgesi Seç", command=lambda: select_region("MP")).pack(pady=5)

hp_trigger_var = tk.StringVar(value="30")
mp_trigger_var = tk.StringVar(value="50")
hp_key_var = tk.StringVar(value="1")
mp_key_var = tk.StringVar(value="2")

def update_triggers(*args):
    try:
        thinker.hp_trigger = int(hp_trigger_var.get())
        thinker.mp_trigger = int(mp_trigger_var.get())
        thinker.hp_key = hp_key_var.get().strip()
        thinker.mp_key = mp_key_var.get().strip()
        save_settings()
    except:
        pass

hp_trigger_var.trace_add("write", update_triggers)
mp_trigger_var.trace_add("write", update_triggers)
hp_key_var.trace_add("write", update_triggers)
mp_key_var.trace_add("write", update_triggers)

frame = tk.Frame(hp_mp_tab)
frame.pack(pady=10)
tk.Label(frame, text="HP Tetik %:").grid(row=0, column=0)
tk.Entry(frame, width=5, textvariable=hp_trigger_var).grid(row=0, column=1)
tk.Label(frame, text="HP Tuş:").grid(row=0, column=2)
tk.Entry(frame, width=5, textvariable=hp_key_var).grid(row=0, column=3)
tk.Label(frame, text="MP Tetik %:").grid(row=1, column=0)
tk.Entry(frame, width=5, textvariable=mp_trigger_var).grid(row=1, column=1)
tk.Label(frame, text="MP Tuş:").grid(row=1, column=2)
tk.Entry(frame, width=5, textvariable=mp_key_var).grid(row=1, column=3)

# ---- Kordinat Tab ----
extra_tab = ttk.Frame(notebook)
notebook.add(extra_tab, text="Kordinat")
extra_text_var = tk.StringVar()
extra_text_var.set("Kordinat bölgesi seçilmedi.")
tk.Label(extra_tab, textvariable=extra_text_var, font=("Arial", 14), fg="purple").pack(pady=10)

kordinat_active_var = tk.BooleanVar(value=True)
kordinat_checkbox = tk.Checkbutton(extra_tab, text="Kordinat Aktif (Değişirse dur)", variable=kordinat_active_var)
kordinat_checkbox.pack(pady=5)

extra_thinker = ExtraOCRThinker(extra_text_var)
extra_thinker.daemon = True
extra_thinker.start()

def select_extra_region():
    RegionSelector(callback=lambda region, text: (
        extra_thinker.set_region(region),
        extra_text_var.set(f"Kordinat: {text}"),
        save_settings()
    ))

tk.Button(extra_tab, text="Kordinat Bölgesi Seç", command=select_extra_region).pack(pady=10)

# ---------------- Kaydet / Yükle ----------------
def save_settings():
    data = {
        "skills": {},
        "r_combo": r_combo_active.get(),
        "r_delay": r_delay_entry.get(),
        "hp_trigger": thinker.hp_trigger,
        "mp_trigger": thinker.mp_trigger,
        "hp_key": thinker.hp_key,
        "mp_key": thinker.mp_key,
        "kordinat_active": kordinat_active_var.get(),
        "regions": {"HP": thinker.regions.get("HP"), "MP": thinker.regions.get("MP"), "extra": extra_thinker.region}
    }
    for key, (active_var, entry_key, entry_delay) in skill_entries.items():
        data["skills"][key] = {
            "active": active_var.get(),
            "key": entry_key.get(),
            "delay": entry_delay.get()
        }
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f)

def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        return
    try:
        with open(SETTINGS_FILE, "r") as f:
            data = json.load(f)

        for key, vals in data.get("skills", {}).items():
            if key in skill_entries:
                active_var, entry_key, entry_delay = skill_entries[key]
                active_var.set(vals.get("active", True))
                entry_key.delete(0, tk.END)
                entry_key.insert(0, vals.get("key", key))
                entry_delay.delete(0, tk.END)
                entry_delay.insert(0, vals.get("delay", "1.0"))

        r_combo_active.set(data.get("r_combo", False))
        r_delay_entry.delete(0, tk.END)
        r_delay_entry.insert(0, data.get("r_delay", "0.2"))

        thinker.hp_trigger = data.get("hp_trigger", 30)
        thinker.mp_trigger = data.get("mp_trigger", 50)
        thinker.hp_key = data.get("hp_key", "1")
        thinker.mp_key = data.get("mp_key", "2")

        hp_trigger_var.set(str(thinker.hp_trigger))
        mp_trigger_var.set(str(thinker.mp_trigger))
        hp_key_var.set(thinker.hp_key)
        mp_key_var.set(thinker.mp_key)

        kordinat_active_var.set(data.get("kordinat_active", True))

        regions = data.get("regions", {})
        if "HP" in regions and regions["HP"]:
            thinker.set_region("HP", regions["HP"])
            text_vars["HP"].set(f"HP Bölgesi: {regions['HP']}")
        if "MP" in regions and regions["MP"]:
            thinker.set_region("MP", regions["MP"])
            text_vars["MP"].set(f"MP Bölgesi: {regions['MP']}")
        if "extra" in regions and regions["extra"]:
            extra_thinker.set_region(regions["extra"])
            extra_text_var.set(f"Kordinat: {regions['extra']}")

    except Exception as e:
        print("Ayarlar yüklenemedi:", e)

load_settings()

# ---------------- Makro Start/Stop ----------------
def set_widgets_state(state):
    for key, (active_var, entry_key, entry_delay) in skill_entries.items():
        entry_key.config(state=state)
        entry_delay.config(state=state)
        chk = macro_frame.grid_slaves(row=list(skill_entries.keys()).index(key)+1, column=0)[0]
        chk.config(state=state)
    r_combo_checkbox.config(state=state)
    r_delay_entry.config(state=state)

def start_macro():
    global running, threads, r_running, extra_region_value
    if running:
        return
    has_skill = any(v[0].get() for v in skill_entries.values())
    if not has_skill and not r_combo_active.get():
        messagebox.showwarning("Uyarı", "En az bir aktif skill veya R Combo seçin!")
        return
    if kordinat_active_var.get() and extra_thinker.region:
        img = pyautogui.screenshot(region=extra_thinker.region)
        img = extra_thinker.preprocess_image(img)
        extra_region_value = pytesseract.image_to_string(img, config='--psm 7').strip()
    set_widgets_state("disabled")
    r_running = True
    threading.Thread(target=r_worker, daemon=True).start()
    running = True
    threads = []
    for idx, key in enumerate(skill_entries):
        active_var, entry_key, entry_delay = skill_entries[key]
        t = threading.Thread(target=skill_worker, args=(key, active_var, entry_key, entry_delay), daemon=True)
        t.start()
        threads.append(t)
        time.sleep(0.01)
    status_label.config(text="Makro: ÇALIŞIYOR")

def stop_macro():
    global running, r_running
    running = False
    r_running = False
    status_label.config(text="Makro: DURDU")
    set_widgets_state("normal")

# ---------------- Program Kapat ----------------
def on_close():
    thinker.stop()
    extra_thinker.stop()
    save_settings()
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_close)
root.mainloop()
