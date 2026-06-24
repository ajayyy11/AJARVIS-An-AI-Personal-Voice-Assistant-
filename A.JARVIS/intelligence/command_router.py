import os
import datetime
import psutil
import pyautogui
from google import genai
from google.genai import types
import requests
from intelligence.memory import add_memory, get_recent

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

system_active = False
notes_file = os.path.join(os.path.dirname(__file__), "..", "notes.txt")
DEFAULT_CITY = os.getenv("DEFAULT_CITY", "London")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY", "")


def process_command(command, username):
    global system_active

    command = command.lower().strip()

    # ──────────────────────────────────────────────
    # WAKE WORD
    # ──────────────────────────────────────────────
    if "hey jarvis" in command:
        reply = f"Hello {username}. Awaiting system activation."
        add_memory(command, reply)
        return reply

    # ──────────────────────────────────────────────
    # ACTIVATE
    # ──────────────────────────────────────────────
    if "system activate" in command:
        system_active = True
        reply = "Activating system. All functions online."
        add_memory(command, reply)
        return reply

    # ──────────────────────────────────────────────
    # DEACTIVATE
    # ──────────────────────────────────────────────
    if "system deactivate" in command or "system shut down" in command:
        system_active = False
        reply = f"System deactivating. Until next time, {username}."
        add_memory(command, reply)
        return reply

    # ──────────────────────────────────────────────
    # SYSTEM OFFLINE GUARD
    # ──────────────────────────────────────────────
    if not system_active:
        return "System is offline. Say 'system activate' to begin."

    # ──────────────────────────────────────────────
    # ── PREDEFINED COMMANDS ──
    # ──────────────────────────────────────────────

    # TIME
    if "time" in command and "date" not in command:
        now = datetime.datetime.now().strftime("%I:%M %p")
        reply = f"The current time is {now}."
        add_memory(command, reply)
        return reply

    # DATE
    if "date" in command or "what day" in command or "today" in command:
        today = datetime.datetime.now().strftime("%A, %B %d, %Y")
        reply = f"Today is {today}."
        add_memory(command, reply)
        return reply

    # ── OPEN APPS ──
    if "open youtube" in command:
        os.system("start https://youtube.com")
        reply = "Opening YouTube."
        add_memory(command, reply)
        return reply

    if "open google" in command:
        os.system("start https://google.com")
        reply = "Opening Google."
        add_memory(command, reply)
        return reply

    if "open chrome" in command:
        os.system("start chrome")
        reply = "Opening Chrome."
        add_memory(command, reply)
        return reply

    if "open visual studio" in command or "open vs code" in command or "open visualstudio" in command:
        os.system("start code")
        reply = "Opening Visual Studio Code."
        add_memory(command, reply)
        return reply

    if "open file explorer" in command:
        os.system("start explorer")
        reply = "Opening File Explorer."
        add_memory(command, reply)
        return reply

    # ── SYSTEM CONTROLS ──
    if "shutdown system" in command:
        os.system("shutdown /s /t 5")
        reply = "System shutting down in 5 seconds."
        add_memory(command, reply)
        return reply

    if "restart system" in command:
        os.system("shutdown /r /t 5")
        reply = "Restarting system in 5 seconds."
        add_memory(command, reply)
        return reply

    if "lock system" in command:
        os.system("rundll32.exe user32.dll,LockWorkStation")
        reply = "System locked."
        add_memory(command, reply)
        return reply

    # ── SCREENSHOT ──
    if "take screenshot" in command:
        screenshot = pyautogui.screenshot()
        screenshot.save("screenshot.png")
        reply = "Screenshot captured and saved."
        add_memory(command, reply)
        return reply

    # ── SYSTEM STATS ──
    if "system status" in command:
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        reply = f"CPU usage is {cpu}%. RAM usage is {ram}%."
        add_memory(command, reply)
        return reply

    # ── BATTERY STATUS ──
    if "battery" in command:
        battery = psutil.sensors_battery()
        if battery:
            percent = int(battery.percent)
            plugged = "charging" if battery.power_plugged else "not charging"
            reply = f"Battery is at {percent}% and is currently {plugged}."
        else:
            reply = "Battery information is not available on this device."
        add_memory(command, reply)
        return reply

    # ── FILE SEARCH ──
    if "find file" in command or "search for file" in command:
        target = command.replace("find file", "").replace("search for file", "").strip()
        if not target:
            reply = "Please specify a file name to find."
        else:
            reply = f"Searching for {target}. This might take a moment."
            add_memory(command, reply)
            
            # Start search from user's home directory
            home_dir = os.path.expanduser("~")
            found_path = None
            
            # Fast walk, bail after first match
            for root, dirs, files in os.walk(home_dir):
                # case insensitive search
                for name in files:
                    if target.lower() in name.lower():
                        found_path = os.path.join(root, name)
                        break
                if found_path:
                    break
            
            if found_path:
                # Open the folder containing the file
                os.system(f'explorer /select,"{found_path}"')
                reply = f"Found {target} and opened its location."
            else:
                reply = f"Could not find {target} in your home directory."
            
            # Since we already added the 'searching' memory, we can add the result too
            add_memory("System Note", reply)
            return reply

    # ── VOLUME CONTROL ──
    if "volume up" in command:
        for _ in range(5):
            pyautogui.press("volumeup")
        reply = "Volume increased."
        add_memory(command, reply)
        return reply

    if "volume down" in command:
        for _ in range(5):
            pyautogui.press("volumedown")
        reply = "Volume decreased."
        add_memory(command, reply)
        return reply

    if "mute" in command or "unmute" in command:
        pyautogui.press("volumemute")
        reply = "Volume toggled."
        add_memory(command, reply)
        return reply

    # ── NOTES ──
    if "take a note" in command or "make a note" in command:
        note_text = (command
                     .replace("take a note", "")
                     .replace("make a note", "")
                     .strip())
        if note_text:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            with open(notes_file, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {note_text}\n")
            reply = f"Note saved: {note_text}"
        else:
            reply = "What would you like me to note? Please repeat with the note content."
        add_memory(command, reply)
        return reply

    if "read my notes" in command or "read notes" in command:
        try:
            with open(notes_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if lines:
                notes = " | ".join(l.strip() for l in lines[-5:])
                reply = f"Your recent notes: {notes}"
            else:
                reply = "You have no saved notes."
        except FileNotFoundError:
            reply = "You have no saved notes yet."
        add_memory(command, reply)
        return reply

    # ── WEATHER ──
    if "weather" in command:
        # Extract city: "weather in Chennai" or "weather" (use default)
        city = DEFAULT_CITY
        if " in " in command:
            city = command.split(" in ", 1)[-1].strip()
        elif "weather of " in command:
            city = command.replace("weather of ", "").strip()

        if not WEATHER_API_KEY:
            reply = "Weather API key is not configured. Please add WEATHER_API_KEY to your .env file."
        else:
            try:
                url = (
                    f"https://api.openweathermap.org/data/2.5/weather"
                    f"?q={city}&appid={WEATHER_API_KEY}&units=metric"
                )
                res = requests.get(url, timeout=5)
                data = res.json()

                if res.status_code == 200:
                    temp     = round(data["main"]["temp"])
                    feels    = round(data["main"]["feels_like"])
                    humidity = data["main"]["humidity"]
                    desc     = data["weather"][0]["description"].capitalize()
                    reply = (
                        f"Weather in {city.title()}: {desc}. "
                        f"Temperature is {temp}°C, feels like {feels}°C, "
                        f"humidity {humidity}%."
                    )
                else:
                    reply = f"Could not find weather for '{city}'. Please check the city name."
            except Exception as e:
                print("Weather error:", e)
                reply = "Could not fetch weather data. Check your internet connection."

        add_memory(command, reply)
        return reply

    # ──────────────────────────────────────────────
    # ── AI FALLBACK with MEMORY CONTEXT ──
    # ──────────────────────────────────────────────
    try:
        print("Using Gemini with memory context...")

        system_prompt = (
            f"You are A.JARVIS, an advanced AI assistant created for {username}. "
            "You are precise, intelligent, and slightly formal — like a next-generation Jarvis from Iron Man. "
            "Keep responses concise and natural for voice output. Avoid markdown formatting."
        )

        # Build conversation history for context
        history = get_recent(5)
        messages = []
        for entry in history:
            messages.append({"role": "user", "parts": [{"text": entry["command"]}]})
            messages.append({"role": "model", "parts": [{"text": entry["response"]}]})

        # Add current command
        messages.append({"role": "user", "parts": [{"text": command}]})

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=messages,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=512
            )
        )

        reply = response.text.strip()
        print("Gemini Response:", reply)
        add_memory(command, reply)
        return reply

    except Exception as e:
        print("Gemini Error:", e)
        return "AI module encountered an error. Please try again."