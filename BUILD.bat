@echo off
chcp 65001 > nul
cd /d %~dp0

echo 起動中のNoble Shelfを終了中...
taskkill /f /im "Noble Shelf.exe" > nul 2>&1
timeout /t 2 /nobreak > nul

echo 古いビルドを削除中...
rd /s /q "dist\Noble Shelf" > nul 2>&1

echo ビルド開始...
pyinstaller --noconfirm --clean --noconsole --name "Noble Shelf" --icon "assets/desktop_icon.ico" --add-data "assets;assets" --hidden-import aiohttp --hidden-import bs4 launcher.py

if %errorlevel% neq 0 (
    echo PyInstallerでエラーが発生しました
    pause
    exit /b 1
)

echo バージョン取得中...
for /f "delims=" %%i in ('python -c "from version import VERSION; print(VERSION)"') do set VERSION=%%i
echo バージョン: %VERSION%

echo Zip作成中...
del /f /q "dist\Noble_Shelf_v%VERSION%.zip" > nul 2>&1
powershell -Command "Compress-Archive -Path 'dist\Noble Shelf' -DestinationPath 'dist\Noble_Shelf_v%VERSION%.zip'"

if %errorlevel% neq 0 (
    echo 失敗しました。別ウィンドウで以下を実行してください:
    echo   ^& "$env:TEMP\Handle\handle64.exe" "base_library.zip" /accepteula
    pause
    exit /b 1
)

echo 完成！ dist\Noble_Shelf_v%VERSION%.zip
pause