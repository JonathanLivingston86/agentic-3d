@echo off
rem Agentic 3D: installazione su Windows. Doppio clic su questo file (dopo aver estratto tutto lo ZIP).
title Agentic 3D - installazione
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\componenti\installa.ps1"
