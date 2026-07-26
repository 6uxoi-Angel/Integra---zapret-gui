Option Explicit
Dim fso, shell, root, pythonw, mainFile, arguments, index, value
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("Shell.Application")
root = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = fso.BuildPath(root, ".venv\Scripts\pythonw.exe")
mainFile = fso.BuildPath(root, "main.py")

If Not fso.FileExists(pythonw) Then
    MsgBox "Сначала запустите run.bat или install.bat." & vbCrLf & "Run run.bat or install.bat first.", 48, "Integra"
    WScript.Quit 1
End If

arguments = Chr(34) & mainFile & Chr(34)
If WScript.Arguments.Count = 0 Then
    arguments = arguments & " --show"
Else
    For index = 0 To WScript.Arguments.Count - 1
        value = LCase(WScript.Arguments(index))
        If value = "--show" Or value = "--minimized" Or value = "--no-elevate" Then
            arguments = arguments & " " & value
        End If
    Next
End If

shell.ShellExecute pythonw, arguments, root, "runas", 1
