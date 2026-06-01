# Hytale Mod Launcher 🚀

> ⚠️ **Disclaimer: Alpha / Beta Software**  
> This project is currently in early development (Alpha/Beta phase). You might encounter bugs, unexpected behaviors, or visual glitches. Please report any issues you find!

A fast, lightweight, and completely standalone Mod Launcher for Hytale. Powered by PyQt6 and perfectly integrated with the **CurseForge API** to let you explore, download, and manage your mods without breaking a sweat.


## ⚡Features

- **Internationalization (i18n):** Full support for English and Spanish out of the box.
- **Dynamic Themes:** Easily swap between stunning color palettes (*Dark, Dracula, Ocean, Light*).
- **Explore CurseForge:** Browse popular, updated, or most downloaded mods directly from the app.
- **One-Click Installs:** No more manual zip extraction. Find a mod and click "Add".
- **Smart Updates:** Click "Check for updates" and the launcher will scan CurseForge for new versions of your installed mods. Update them all with a single click.
- **Fingerprint Scanner:** Did you install mods manually in the past? Just click "Scan folder" and the app will calculate the Murmur2 hash of your `.jar` files to automatically track them with CurseForge.
- **Standalone Executable:** Everything is packaged into a single `.exe`. No Python or extra libraries required.

## 🚀 Download & Run

1. Head over to the [Releases page](https://github.com/lenase0077/HytaleModLauncher/releases) and download the latest `HytaleModLauncher.exe`.
2. Double click the executable to run it.
3. Done! The launcher will automatically find your Hytale Mods folder.

## 💻 Building from Source

If you prefer to compile it yourself or want to contribute:

```bash
# 1. Clone the repository
git clone https://github.com/lenase0077/HytaleModLauncher.git
cd HytaleModLauncher

# 2. Create a virtual environment and install dependencies
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 3. Run the launcher directly
python -m hytale_launcher

# 4. Or compile it into an executable
pyinstaller --clean HytaleModLauncher.spec
```

## 🛠️ Built With

- **Python 3**
- **PyQt6** (UI Framework)
- **Requests** (API fetching)
- **PyInstaller** (Executable bundling)
- **Lucide Icons** (SVG Graphics)

## 🤝 Contributing
Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

## 📄 License
This project is open-source and available under the MIT License.
