# Hytale Mod Launcher Python

Version Python/Tkinter del launcher de mods de Hytale.

## Requisitos

- Python 3.10+

## Instalar dependencias

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Ejecutar

```powershell
python -m hytale_launcher
```

## Crear EXE con PyInstaller

```powershell
.\build_exe.ps1
```

El ejecutable queda en:

```text
dist\HytaleModLauncher.exe
```
