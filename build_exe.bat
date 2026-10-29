@echo off
echo ========================================================
echo   IUH Ledger - Build Standalone Executable (PyInstaller)
echo ========================================================
echo.
echo [1/3] Dong cac tien trinh IUH_Ledger dang chay (neu co)...
taskkill /F /IM IUH_Ledger.exe >nul 2>&1
taskkill /F /IM IUH_Ledger_v2.exe >nul 2>&1

echo [2/3] Dong goi PyInstaller Standalone Folder (--onedir)...
python -m PyInstaller iuh_ledger.spec --distpath "dist" --workpath "build" --noconfirm --clean
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Build failed!
    exit /b %ERRORLEVEL%
)

echo [3/3] Nen thu muc thanh dist\IUH_Ledger_Portable.zip (SACH, KHONG CHUA PASSWORD/COOKIE)...
if exist "config.example.json" (
    copy /Y "config.example.json" "dist\IUH_Ledger\config.json" >nul
)
if exist "dist\IUH_Ledger\session.json" (
    del /F /Q "dist\IUH_Ledger\session.json" >nul 2>&1
)

> "dist\IUH_Ledger\IUH_Ledger.exe.config" (
    echo ^<?xml version="1.0" encoding="utf-8" ?^>
    echo ^<configuration^>^<runtime^>^<loadFromRemoteSources enabled="true"/^>^</runtime^>^</configuration^>
)
for %%D in (vcruntime140.dll vcruntime140_1.dll msvcp140.dll concrt140.dll) do (
    if exist "dist\IUH_Ledger\_internal\%%D" copy /Y "dist\IUH_Ledger\_internal\%%D" "dist\IUH_Ledger\%%D" >nul
)
> "dist\IUH_Ledger\Chay_IUH_Ledger.bat" (
    echo @echo off
    echo if not exist "%%~dp0_internal" ^(
    echo   echo Thieu thu muc _internal. Hay giai nen TOAN BO file ZIP roi chay lai, dung keo rieng IUH_Ledger.exe ra ngoai.
    echo   pause
    echo   exit /b 1
    echo ^)
    echo powershell -NoProfile -Command "Get-ChildItem -LiteralPath '%%~dp0' -Recurse -File | Unblock-File" ^>nul 2^>^&1
    echo start "" "%%~dp0IUH_Ledger.exe"
)
powershell -NoProfile -Command "Get-ChildItem -LiteralPath 'dist\IUH_Ledger' -Recurse -File | Unblock-File" >nul 2>&1
python -c "import shutil, os; [os.remove(p) for p in ('dist/IUH_Ledger_Portable.zip','dist/IUH_Ledger_Portable_v2.zip') if os.path.exists(p)]; shutil.make_archive('dist/IUH_Ledger_Portable', 'zip', 'dist', 'IUH_Ledger'); shutil.copy2('dist/IUH_Ledger_Portable.zip', 'dist/IUH_Ledger_Portable_v2.zip')"
if exist "config.json" (
    copy /Y "config.json" "dist\IUH_Ledger\config.json" >nul
)
if exist "session.json" (
    copy /Y "session.json" "dist\IUH_Ledger\session.json" >nul
)

echo.
echo ========================================================
echo   BUILD THANH CONG!
echo   1. Thu muc chay ngay: dist\IUH_Ledger\IUH_Ledger.exe
echo   2. Goi ZIP phan phoi: dist\IUH_Ledger_Portable_v2.zip (va dist\IUH_Ledger_Portable.zip)
echo      (Giai nen ra bat ky dau va click IUH_Ledger.exe hoac Chay_IUH_Ledger.bat la chay!)
echo ========================================================
