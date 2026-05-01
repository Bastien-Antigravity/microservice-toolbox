Attribute VB_Name = "Toolbox"
' -----------------------------------------------------------------------------------------------
' Microservice Toolbox: Utility Module
' -----------------------------------------------------------------------------------------------

Option Explicit

#If Mac Then
    ' Mac implementation using libc
    Private Declare PtrSafe Function strlen Lib "/usr/lib/libc.dylib" (ByVal ptr As LongPtr) As Long
    Private Declare PtrSafe Function strlcpy Lib "/usr/lib/libc.dylib" (ByVal dest As String, ByVal src As LongPtr, ByVal size As Long) As Long
#Else
    ' Windows implementation using kernel32
    Private Declare PtrSafe Function lstrlenA Lib "kernel32" (ByVal ptr As LongPtr) As Long
    Private Declare PtrSafe Function lstrcpynA Lib "kernel32" (ByVal dest As String, ByVal src As LongPtr, ByVal size As Long) As Long
#End If

' LoadConfig factory method.
Public Function LoadConfig(ByVal profile As String) As AppConfig
    Dim cfg As New AppConfig
    cfg.Init profile
    Set LoadConfig = cfg
End Function

' Internal helper to convert a C-string pointer (char*) to a VBA String.
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
    
    ' Free the string allocated by the Go bridge to prevent memory leaks.
    ' Assuming the Go bridge used C.CString or equivalent that needs freeing.
    DistConf.DistConf_FreeString ptr
    
    PtrToString = res
End Function
