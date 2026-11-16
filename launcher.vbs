' ============================================================
' MS_helper - GUI launcher without console window.
'
' Looks for the interpreter in this order:
'   1. python\pythonw.exe  - portable Python (no installation needed)
'   2. python\python.exe   - portable Python (console build)
'   3. runtime\pythonw.exe - alternative portable folder
'   4. pythonw.exe from PATH - system Python, if portable is absent
'
' The console window is hidden by intWindowStyle = 0.
' This file is plain ASCII on purpose: Windows Script Host reads
' .vbs in the system ANSI codepage, and Cyrillic comments break
' the file on some machines.
' ============================================================
Option Explicit

Dim fso, shell, scriptDir, exePath, candidates, i
Dim target

Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = scriptDir

' Interpreter candidates, in priority order
candidates = Array( _
    scriptDir & "\python\pythonw.exe", _
    scriptDir & "\python\python.exe", _
    scriptDir & "\runtime\pythonw.exe", _
    scriptDir & "\runtime\python.exe" _
)

exePath = ""
For i = 0 To UBound(candidates)
    If fso.FileExists(candidates(i)) Then
        exePath = candidates(i)
        Exit For
    End If
Next

If exePath = "" Then
    ' No portable Python - fall back to the system one from PATH
    exePath = "pythonw.exe"
End If

target = scriptDir & "\launcher.py"

If Not fso.FileExists(target) Then
    MsgBox "launcher.py not found in:" & vbCrLf & scriptDir, _
           16, "MS_helper"
    WScript.Quit 1
End If

' intWindowStyle = 0 hides the console, False = do not wait
shell.Run """" & exePath & """ """ & target & """", 0, False
