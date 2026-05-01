VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
END
Attribute VB_Name = "AppConfig"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
' -----------------------------------------------------------------------------------------------
' Microservice Toolbox: AppConfig Class Module
' -----------------------------------------------------------------------------------------------
' Provides a high-level, object-oriented API for configuration management in VBA.
' -----------------------------------------------------------------------------------------------

Option Explicit

Private m_handle As LongPtr
Private m_profile As String
Private m_local As Object  ' Scripting.Dictionary
Private m_mirror As Object ' Scripting.Dictionary (In-Memory Mirror)

' Initialization
' -----------------------------------------------------------------------------------------------

' LoadConfig initializes the configuration based on the requested Profile logic.
Public Sub LoadConfig(ByVal profile As String)
    m_profile = profile
    Set m_local = CreateObject("Scripting.Dictionary")
    Set m_mirror = CreateObject("Scripting.Dictionary")
    
    m_handle = DistConf.DistConf_New(profile)
    
    If m_handle = 0 Then
        Err.Raise 513, "AppConfig", "Failed to initialize DistConf for profile: " & profile
    End If
    
    ' Phase 2: Sync from bridge (In-Memory Mirroring)
    SyncFromBridge
    
    ' Phase 3: Manual loading of 'local' section (Parity with Go Toolbox)
    LoadLocalOverrides
End Sub

' Clean up
' -----------------------------------------------------------------------------------------------

Private Sub Class_Terminate()
    If m_handle <> 0 Then
        DistConf.DistConf_Close m_handle
        m_handle = 0
    End If
    Set m_local = Nothing
    Set m_mirror = Nothing
End Sub

' API Methods
' -----------------------------------------------------------------------------------------------

' GetListenAddr returns the host:port for a capability.
Public Function GetListenAddr(ByVal capability As String) As String
    Dim ptr As LongPtr
    ptr = DistConf.DistConf_GetAddress(m_handle, capability)
    GetListenAddr = Toolbox.PtrToString(ptr)
End Function

' GetGRPCListenAddr returns the gRPC address for a capability.
Public Function GetGRPCListenAddr(ByVal capability As String) As String
    Dim ptr As LongPtr
    ptr = DistConf.DistConf_GetGRPCAddress(m_handle, capability)
    GetGRPCListenAddr = Toolbox.PtrToString(ptr)
End Function

' DecryptSecret decrypts a secret ENC(...) block.
' Matches the hardened logic of the polyglot ecosystem (100% Transparency).
Public Function DecryptSecret(ByVal ciphertext As String) As String
    If Left(ciphertext, 4) <> "ENC(" Or Right(ciphertext, 1) <> ")" Then
        DecryptSecret = ciphertext
        Exit Function
    End If
    
    Dim ptr As LongPtr
    ptr = DistConf.DistConf_Decrypt(m_handle, ciphertext)
    
    If ptr = 0 Then
        Dim errPtr As LongPtr
        Dim errMsg As String
        errPtr = DistConf.DistConf_GetLastError()
        If errPtr <> 0 Then
            errMsg = Toolbox.PtrToString(errPtr)
            Err.Raise 514, "AppConfig", "Decryption failed: " & errMsg
        Else
            Err.Raise 514, "AppConfig", "Decryption failed (bridge error)"
        End If
    End If
    
    DecryptSecret = Toolbox.PtrToString(ptr)
End Function

' GetLocal returns a value from the 'local' configuration section.
Public Function GetLocal(ByVal key As String) As String
    If m_local.Exists(key) Then
        GetLocal = m_local(key)
    Else
        GetLocal = ""
    End If
End Function

' Internal Helpers
' -----------------------------------------------------------------------------------------------

Private Sub LoadLocalOverrides()
    On Error Resume Next
    Dim fso As Object
    Set fso = CreateObject("Scripting.FileSystemObject")
    
    Dim filename As String
    filename = m_profile & ".yaml"
    
    If Not fso.FileExists(filename) Then
        filename = "config\" & m_profile & ".yaml"
        If Not fso.FileExists(filename) Then Exit Sub
    End If
    
    Dim ts As Object
    Set ts = fso.OpenTextFile(filename, 1)
    
    Dim line As String
    Dim inLocal As Boolean
    inLocal = False
    
    Do While Not ts.AtEndOfStream
        line = ts.ReadLine
        
        ' Simple YAML-lite parser for top-level "local:"
        If Left(line, 6) = "local:" Then
            inLocal = True
        ElseIf inLocal Then
            ' Check if we exited the local section (new top-level key or non-empty line without indentation)
            If Len(Trim(line)) > 0 And Left(line, 1) <> " " And Left(line, 1) <> vbTab And Left(line, 1) <> "#" Then
                inLocal = False
            Else
                Dim colon As Long
                colon = InStr(line, ":")
                If colon > 0 Then
                    Dim k As String, v As String
                    k = Trim(Left(line, colon - 1))
                    v = Trim(Mid(line, colon + 1))
                    
                    If k <> "" Then
                        ' Remove quotes
                        If (Left(v, 1) = "'" And Right(v, 1) = "'") Or (Left(v, 1) = """" And Right(v, 1) = """") Then
                            v = Mid(v, 2, Len(v) - 2)
                        End If
                        
                        ' Basic ENV expansion: %VAR% style for VBA/Windows
                        ' (Simplified: matches VBA's Environ function)
                        v = ExpandEnv(v)
                        
                        If m_local.Exists(k) Then m_local.Remove k
                        m_local.Add k, v
                    End If
                End If
            End If
        End If
    Loop
    ts.Close
End Sub

Private Function ExpandEnv(ByVal inputStr As String) As String
    ' Expand Environment Variables: ${VAR} or ${VAR:default}
    Dim result As String
    result = inputStr
    
    Dim startPos As Long, endPos As Long
    startPos = InStr(result, "${")
    Do While startPos > 0
        endPos = InStr(startPos + 2, result, "}")
        If endPos > 0 Then
            Dim token As String
            token = Mid(result, startPos + 2, endPos - startPos - 2)
            
            Dim varName As String, defaultVal As String
            Dim colon As Long
            colon = InStr(token, ":")
            
            If colon > 0 Then
                varName = Left(token, colon - 1)
                defaultVal = Mid(token, colon + 1)
            Else
                varName = token
                defaultVal = ""
            End If
            
            Dim envVal As String
            envVal = Environ(varName)
            If envVal = "" Then envVal = defaultVal
            
            result = Left(result, startPos - 1) & envVal & Mid(result, endPos + 1)
            startPos = InStr(startPos + Len(envVal), result, "${")
        Else
            Exit Do
        End If
    Loop
    ExpandEnv = result
End Function

' In-Memory Mirroring
' -----------------------------------------------------------------------------------------------

' SyncFromBridge fetches the entire configuration from the Go core and mirrors it locally.
Public Sub SyncFromBridge()
    Dim ptr As LongPtr
    Dim jsonStr As String
    ptr = DistConf.DistConf_GetFullConfig(m_handle)
    
    If ptr <> 0 Then
        jsonStr = Toolbox.PtrToString(ptr)
        ParseJsonToMirror jsonStr
    End If
End Sub

' Simple JSON parser for the flattened DistConf structure.
' Expects: {"section": {"key": "val", ...}, ...}
Private Sub ParseJsonToMirror(ByVal json As String)
    On Error Resume Next
    m_mirror.RemoveAll
    
    ' This is a simplified parser for the specific DistConf JSON format.
    ' It handles nested dictionaries (sections).
    Dim i As Long, j As Long
    Dim section As String, key As String, val As String
    Dim sections() As String
    
    ' Split by sections (very basic approach)
    sections = Split(json, """")
    
    ' Iterating through tokens to find keys and values
    ' (More robust parsing would be better, but this fits the "no-dependency" requirement)
    For i = 1 To UBound(sections) Step 2
        ' Logic to extract sections and keys from flattened JSON
        ' (Simplified for parity demonstration)
        Dim token As String
        token = sections(i)
        
        ' If the next token is a colon and we have a value...
        If i + 2 <= UBound(sections) Then
            If InStr(sections(i + 1), ":") > 0 Then
                val = sections(i + 2)
                ' We use the raw key from JSON
                If m_mirror.Exists(token) Then m_mirror.Remove token
                m_mirror.Add token, val
            End If
        End If
    Next i
End Sub

' Properties
' -----------------------------------------------------------------------------------------------

Public Property Get profile() As String
    profile = m_profile
End Property

Public Property Get handle() As LongPtr
    handle = m_handle
End Property
