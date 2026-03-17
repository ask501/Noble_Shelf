@echo off
chcp 65001 > nul
cd /d %~dp0

echo ビルド開始...

pyinstaller --noconfirm --clean --noconsole --name "Noble Shelf" --icon "assets/desktop_icon.ico" --add-data "assets;assets" --hidden-import aiohttp --hidden-import bs4 launcher.py

if errorlevel 1 (
    echo PyInstallerでエラーが発生しました
    pause
    exit /b 1
)

echo バージョン取得中...
for /f "delims=" %%i in ('python -c "from version import VERSION; print(VERSION)"') do set VERSION=%%i

echo バージョン: %VERSION%
echo Zip作成中...
timeout /t 3 /nobreak > nul
powershell -Command "Compress-Archive -Path 'dist\Noble Shelf' -DestinationPath 'dist\Noble_Shelf_v%VERSION%.zip' -Force"

if errorlevel 1 (
    echo Zip作成でエラーが発生しました
    pause
    exit /b 1
)

echo 完成！ dist\Noble_Shelf_v%VERSION%.zip
pause