@echo off
rem Сборка HappDecoder.exe (Windows, PyInstaller)
setlocal

python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller

python -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name HappDecoder ^
  --icon icon.ico ^
  --collect-all curl_cffi ^
  --collect-all certifi ^
  happ_gui.py

if errorlevel 1 (
  echo.
  echo [ОШИБКА] Сборка не удалась.
  exit /b 1
)

echo.
echo Готово: dist\HappDecoder.exe
