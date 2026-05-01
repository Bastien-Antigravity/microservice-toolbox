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
Private m_private As Object ' Scripting.Dictionary

' Initialization
' -----------------------------------------------------------------------------------------------

Public Sub Init(ByVal profile As String)
    m_profile = profile
    Set m_private = CreateObject("Scripting.Dictionary")
    
    m_handle = DistConf.DistConf_New(profile)
    
    If m_handle = 0 Then
        Err.Raise 513, "AppConfig", "Failed to initialize DistConf for profile: " & profile
    End If
    
    ' Phase 2: Manual loading of 'private' section (Parity with Go Toolbox)
    LoadPrivateOverrides
End Sub

' Clean up
' -----------------------------------------------------------------------------------------------

Private Sub Class_Terminate()
    If m_handle <> 0 Then
        DistConf.DistConf_Close m_handle
        m_handle = 0
    End If
    Set m_private = Nothing
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
' Matches the hardened logic of the polyglot ecosystem.
Public Function DecryptSecret(ByVal ciphertext As String) As String
    If Left(ciphertext, 4) <> "ENC(" Or Right(ciphertext, 1) <> ")" Then
        DecryptSecret = ciphertext
        Exit Function
    End If
    
    Dim ptr As LongPtr
    ptr = DistConf.DistConf_Decrypt(m_handle, ciphertext)
    DecryptSecret = Toolbox.PtrToString(ptr)
End Function

' GetPrivate returns a value from the 'private' configuration section.
Public Function GetPrivate(ByVal key As String) As String
    If m_private.Exists(key) Then
        GetPrivate = m_private(key)
    Else
        GetPrivate = ""
    End If
End Function

' Internal Helpers
' -----------------------------------------------------------------------------------------------

Private Sub LoadPrivateOverrides()
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
    Dim inPrivate As Boolean
    inPrivate = False
    
    Do While Not ts.AtEndOfStream
        line = ts.ReadLine
        
        ' Simple YAML-lite parser for top-level "private:"
        If Left(line, 8) = "private:" Then
            inPrivate = True
        ElseIf inPrivate Then
            ' Check if we exited the private section (new top-level key or non-empty line without indentation)
            If Len(Trim(line)) > 0 And Left(line, 1) <> " " And Left(line, 1) <> vbTab And Left(line, 1) <> "#" Then
                inPrivate = False
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
                        
                        If m_private.Exists(k) Then m_private.Remove k
                        m_private.Add k, v
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

' Properties
' -----------------------------------------------------------------------------------------------

Public Property Get profile() As String
    profile = m_profile
End Property

Public Property Get handle() As LongPtr
    handle = m_handle
End Property
