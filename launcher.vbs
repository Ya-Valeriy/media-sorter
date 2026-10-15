' ============================================================
' Запуск GUI-лаунчера MediaSorter без окна консоли.
'
' Используется python.exe, а не pythonw.exe, потому что
' pythonw.exe может быть заблокирован политикой
' Application Control (WDAC/AppLocker) на некоторых машинах.
' Окно консоли скрывается параметром intWindowStyle = 0.
' ============================================================
Option Explicit

Dim fso, scriptDir, shell
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = scriptDir
shell.Run """python\python.exe"" ""launcher.py""", 0, False