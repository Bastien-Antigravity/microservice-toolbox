Attribute VB_Name = "Toolbox"
' -----------------------------------------------------------------------------------------------
' ESSENTIAL PROCESS:
' Utility and helper module providing factories (LoadConfig, NewNotificationClient),
' FFI bridge declarations, and memory-safe string conversion routines for VBA.
'
' DATA FLOW:
' 1. Input: Profile strings, target addresses, or raw C-pointer strings (char*).
' 2. Logic: Instantiates AppConfig / NotificationClient or marshals C strings to BSTR.
' 3. Output: Initialized client instances, native VBA Strings, or raw C call invocations.
'
' KEY PARAMETERS:
' - profile: Name of configuration profile to load.
' - ptr: Raw memory pointer to null-terminated C string.
' - TOOLBOX_LIB_PATH: Path to the compiled libtoolbox shared library (.dylib or .dll).
' -----------------------------------------------------------------------------------------------

Option Explicit

#If Mac Then
    ' Mac implementation using libc
    Private Declare PtrSafe Function strlen Lib "/usr/lib/libc.dylib" (ByVal ptr As LongPtr) As Long
    Private Declare PtrSafe Function strlcpy Lib "/usr/lib/libc.dylib" (ByVal dest As String, ByVal src As LongPtr, ByVal size As Long) As Long
    Private Const NOTIF_LIB_PATH As String = "/usr/local/lib/libnotif.dylib"
#Else
    ' Windows implementation using kernel32
    Private Declare PtrSafe Function lstrlenA Lib "kernel32" (ByVal ptr As LongPtr) As Long
    Private Declare PtrSafe Function lstrcpynA Lib "kernel32" (ByVal dest As String, ByVal src As LongPtr, ByVal size As Long) As Long
    Private Const NOTIF_LIB_PATH As String = "libnotif.dll"
#End If

' -----------------------------------------------------------------------------------------------
' libnotif C ABI FFI Declarations
' -----------------------------------------------------------------------------------------------

Public Declare PtrSafe Function Notif_Send Lib NOTIF_LIB_PATH ( _
    ByVal targetAddr As String, _
    ByVal level As String, _
    ByVal message As String, _
    ByVal attachment As String, _
    ByVal tagsCSV As String) As Long

Public Declare PtrSafe Function Notif_SendWithTimeout Lib NOTIF_LIB_PATH ( _
    ByVal targetAddr As String, _
    ByVal level As String, _
    ByVal message As String, _
    ByVal attachment As String, _
    ByVal tagsCSV As String, _
    ByVal timeoutSec As Double) As Long

Public Declare PtrSafe Function Notif_GetLastError Lib NOTIF_LIB_PATH () As LongPtr
Public Declare PtrSafe Sub Notif_FreeString Lib NOTIF_LIB_PATH (ByVal ptr As LongPtr)
Public Declare PtrSafe Sub Notif_Close Lib NOTIF_LIB_PATH ()

' -----------------------------------------------------------------------------------------------
' Factory Methods
' -----------------------------------------------------------------------------------------------

' LoadConfig factory method.
Public Function LoadConfig(ByVal profile As String) As AppConfig
    Dim cfg As New AppConfig
    cfg.Init profile
    Set LoadConfig = cfg
End Function

' NewNotificationClient factory creating a client bound to a specific target address.
Public Function NewNotificationClient(ByVal targetAddr As String) As NotificationClient
    Dim client As New NotificationClient
    client.Init targetAddr
    Set NewNotificationClient = client
End Function

' NewNotificationClientFromConfig factory dynamically resolving notif_server from AppConfig.
' Fails fast if capability is unresolvable or missing (Zero silent fallback).
Public Function NewNotificationClientFromConfig(ByVal cfg As AppConfig, Optional ByVal capability As String = "notif_server") As NotificationClient
    Dim client As New NotificationClient
    client.InitFromConfig cfg, capability
    Set NewNotificationClientFromConfig = client
End Function

' -----------------------------------------------------------------------------------------------
' String Marshaling Helpers
' -----------------------------------------------------------------------------------------------

' Internal helper to convert a libdistconf C-string pointer (char*) to a VBA String.
Public Function PtrToString(ByVal ptr As LongPtr) As String
    If ptr = 0 Then
        PtrToString = ""
        Exit Function
    End If
    
    Dim length As Long
    Dim res As String
    
    #If Mac Then
        length = strlen(ptr)
        res = Space(length)
        strlcpy res, ptr, length + 1
    #Else
        length = lstrlenA(ptr)
        res = Space(length)
        lstrcpynA res, ptr, length + 1
    #End If
    
    ' Free the string allocated by libdistconf
    DistConf.DistConf_FreeString ptr
    
    PtrToString = res
End Function

' Helper to convert a libnotif C-string pointer (char*) to a VBA String and free it.
Public Function NotifPtrToString(ByVal ptr As LongPtr) As String
    If ptr = 0 Then
        NotifPtrToString = ""
        Exit Function
    End If
    
    Dim length As Long
    Dim res As String
    
    #If Mac Then
        length = strlen(ptr)
        res = Space(length)
        strlcpy res, ptr, length + 1
    #Else
        length = lstrlenA(ptr)
        res = Space(length)
        lstrcpynA res, ptr, length + 1
    #End If
    
    ' Free the string allocated by libnotif
    Toolbox.Notif_FreeString ptr
    
    NotifPtrToString = res
End Function

' -----------------------------------------------------------------------------------------------
' Dynamic Version Resolution Helper
' -----------------------------------------------------------------------------------------------

' GetVersion returns the dynamic semantic version resolved from VERSION.txt or environment overrides.
Public Function GetVersion(Optional ByVal startPath As String = "") As String
    ' 1. Check environment variable overrides
    Dim envVer As String
    envVer = Trim$(Environ$("APP_VERSION"))
    If Len(envVer) > 0 Then
        GetVersion = envVer
        Exit Function
    End If
    
    envVer = Trim$(Environ$("SERVICE_VERSION"))
    If Len(envVer) > 0 Then
        GetVersion = envVer
        Exit Function
    End If
    
    ' 2. Determine initial search folder
    Dim currentFolder As String
    currentFolder = startPath
    If Len(currentFolder) = 0 Then
        On Error Resume Next
        currentFolder = Application.ActiveWorkbook.Path
        On Error GoTo 0
        If Len(currentFolder) = 0 Then
            currentFolder = CurDir$()
        End If
    End If
    
    ' 3. Climb parent directories searching for VERSION.txt
    Dim fso As Object
    On Error Resume Next
    Set fso = CreateObject("Scripting.FileSystemObject")
    On Error GoTo 0
    
    If Not fso Is Nothing Then
        Dim dirPath As String
        dirPath = currentFolder
        Do While Len(dirPath) > 0 And fso.FolderExists(dirPath)
            Dim candidate As String
            candidate = fso.BuildPath(dirPath, "VERSION.txt")
            If fso.FileExists(candidate) Then
                Dim ts As Object
                Set ts = fso.OpenTextFile(candidate, 1) ' 1 = ForReading
                If Not ts Is Nothing Then
                    Dim lineStr As String
                    lineStr = Trim$(ts.ReadLine)
                    ts.Close
                    Set ts = Nothing
                    If Len(lineStr) > 0 Then
                        GetVersion = lineStr
                        Exit Function
                    End If
                End If
            End If
            Dim parentFolder As Object
            Set parentFolder = fso.GetFolder(dirPath).ParentFolder
            If parentFolder Is Nothing Then Exit Do
            If parentFolder.Path = dirPath Then Exit Do
            dirPath = parentFolder.Path
        Loop
    End If
    
    ' 4. Canonical ecosystem fallback
    GetVersion = "0.0.1"
End Function

