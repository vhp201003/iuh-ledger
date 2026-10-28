@echo off
echo ========================================================
echo   IUH Ledger - Build Standalone Executable (PyInstaller)
echo ========================================================
echo.
echo [1/3] Dong cac tien trinh IUH_Ledger dang chay (neu co)...
taskkill /F /IM IUH_Ledger.exe >nul 2>&1
taskkill /F /IM IUH_Ledger_v2.exe >nul 2>&1

echo [2/3] Dong goi PyInstaller Standalone Folder (--onedir)...
python -m PyInstaller iuh_ledger.spec --distpath "iuh_sniper/dist" --workpath "iuh_sniper/build" --noconfirm --clean
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Build failed!
    exit /b %ERRORLEVEL%
)

if exist "iuh_sniper\config.json" (
    copy /Y "iuh_sniper\config.json" "iuh_sniper\dist\IUH_Ledger\config.json" >nul
) else if exist "config.example.json" (
    copy /Y "config.example.json" "iuh_sniper\dist\IUH_Ledger\config.json" >nul
)

echo [3/3] Nen thu muc thanh iuh_sniper\dist\IUH_Ledger_Portable.zip...
python -c "import shutil, os; zp='iuh_sniper/dist/IUH_Ledger_Portable'; os.remove(zp+'.zip') if os.path.exists(zp+'.zip') else None; shutil.make_archive(zp, 'zip', 'iuh_sniper/dist', 'IUH_Ledger')"

echo.
echo ========================================================
echo   BUILD THANH CONG!
echo   1. Thu muc chay ngay: iuh_sniper\dist\IUH_Ledger\IUH_Ledger.exe
echo   2. Goi ZIP phan phoi: iuh_sniper\dist\IUH_Ledger_Portable.zip
echo      (Giai nen ra bat ky dau va click IUH_Ledger.exe la chay!)
echo ========================================================
