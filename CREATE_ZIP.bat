@echo off
echo Building recipesnap.zip with latest files...
cd /d "%~dp0"
if exist recipesnap.zip del recipesnap.zip
powershell -Command "Compress-Archive -Path 'app.py','requirements.txt','.replit','templates','static','supabase_setup.sql' -DestinationPath 'recipesnap.zip' -Force"
echo.
echo Done! recipesnap.zip is ready to upload to Replit.
pause
