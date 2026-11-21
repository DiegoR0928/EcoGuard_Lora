@echo off
rem Genera la documentacion de EcoGuard con Doxygen: HTML y PDF (LaTeX con pdflatex).
rem Usa el Doxygen instalado en Program Files: el que trae Strawberry Perl (1.10) suele ir antes
rem en el PATH y su LaTeX ya no compila con MiKTeX actual.
setlocal
cd /d "%~dp0"

set "DOXYGEN=%ProgramFiles%\doxygen\bin\doxygen.exe"
if not exist "%DOXYGEN%" set "DOXYGEN=doxygen"

echo Generando HTML y LaTeX con "%DOXYGEN%"...
"%DOXYGEN%" Doxyfile
if errorlevel 1 goto :error

echo Compilando el PDF (pdflatex, tarda menos de un minuto)...
call doxygen\latex\make.bat > doxygen\latex\compilacion.txt 2>&1
if not exist doxygen\latex\refman.pdf goto :error
findstr /B /C:"! " doxygen\latex\refman.log > nul && goto :error

echo.
echo Listo:
echo   HTML:          %~dp0doxygen\html\index.html
echo   PDF:           %~dp0doxygen\latex\refman.pdf
echo   Advertencias:  %~dp0doxygen\advertencias.txt
exit /b 0

:error
echo.
echo No se pudo generar la documentacion. Revisa doxygen\advertencias.txt y doxygen\latex\refman.log
exit /b 1
