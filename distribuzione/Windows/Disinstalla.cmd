@echo off
rem Agentic 3D: disinstallazione su Windows. Doppio clic su questo file.
title Agentic 3D - disinstallazione
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\componenti\disinstalla.ps1"
