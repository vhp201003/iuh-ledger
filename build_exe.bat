@echo off
echo ========================================================
echo   IUH Ledger - Build Standalone Executable (PyInstaller)
echo ========================================================
echo.

python -m PyInstaller iuh_ledger.spec --distpath "iuh_sniper/dist" --workpath "iuh_sniper/build" --noconfirm --clean
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Build failed!
    pause
    exit /b %ERRORLEVEL%
)

if exist "iuh_sniper\config.json" (
    copy /Y "iuh_sniper\config.json" "iuh_sniper\dist\IUH_Ledger\config.json" >nul
) else if exist "config.json" (
    copy /Y "config.json" "iuh_sniper\dist\IUH_Ledger\config.json" >nul
)

echo.
echo ========================================================
echo   BUILD THANH CONG!
echo   Thu muc dau ra: iuh_sniper\dist\IUH_Ledger\
echo   File chay chinh: iuh_sniper\dist\IUH_Ledger\IUH_Ledger.exe
echo ========================================================
echo.
pause
