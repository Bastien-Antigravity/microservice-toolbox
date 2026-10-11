VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
END
Attribute VB_Name = "NotificationClient"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = True
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = True
' -----------------------------------------------------------------------------------------------
' ESSENTIAL PROCESS:
' Direct Notification Client facade enabling VBA (Excel/Access) macros to dispatch
' direct, multi-channel alerts to notif-server via the libtoolbox C ABI bridge.
'
' DATA FLOW:
' 1. Input: Alert message, level (TRADE, CRITICAL, WARNING), tags, or AppConfig instance.
' 2. Logic: Validates configuration and target address (Fail-Fast), marshals parameters across
'    the C ABI boundary into libtoolbox, and handles errors with zero silent fallbacks.
' 3. Output: Boolean success status and detailed last-error diagnostics.
'
' KEY PARAMETERS:
' - m_targetAddr: Resolved host:port string of notif-server (gRPC port 1027).
' - m_timeoutSec: Timeout in seconds for RPC dispatch (default: 5.0).
' - m_closed: Boolean flag guarding closed client instances.
' -----------------------------------------------------------------------------------------------

Option Explicit

Private m_targetAddr As String
Private m_timeoutSec As Double
Private m_closed As Boolean
Private m_lastError As String

' -----------------------------------------------------------------------------------------------
' Initialization & Destruction
' -----------------------------------------------------------------------------------------------

Private Sub Class_Initialize()
    m_targetAddr = ""
    m_timeoutSec = 5#
    m_closed = False
    m_lastError = ""
End Sub

Private Sub Class_Terminate()
    m_closed = True
End Sub

' -----------------------------------------------------------------------------------------------
' Factory & Configuration Initializers
' -----------------------------------------------------------------------------------------------

' Init initializes the client with an explicit target gRPC address (host:port).
Public Sub Init(ByVal targetAddr As String)
    If Trim$(targetAddr) = "" Then
        m_lastError = "targetAddr cannot be empty"
        Err.Raise vbObjectError + 1001, "NotificationClient", m_lastError
    End If
    m_targetAddr = Trim$(targetAddr)
    m_closed = False
End Sub

' InitFromConfig initializes the client by dynamically resolving notif_server from AppConfig.
' Enforces strict Fail-Fast: raises runtime error if capability is unresolvable or missing.
Public Sub InitFromConfig(ByVal cfg As AppConfig, Optional ByVal capability As String = "notif_server")
    If cfg Is Nothing Then
        m_lastError = "cfg cannot be Nothing"
        Err.Raise vbObjectError + 1002, "NotificationClient", m_lastError
    End If

    Dim capName As String
    capName = Trim$(capability)
    If capName = "" Then capName = "notif_server"

    Dim addr As String
    addr = cfg.GetGRPCListenAddr(capName)

    If Trim$(addr) = "" Then
        m_lastError = "Failed to resolve " & capName & " gRPC address: capability not found or address empty"
        Err.Raise vbObjectError + 1003, "NotificationClient", m_lastError
    End If

    m_targetAddr = Trim$(addr)
    m_closed = False
End Sub

' -----------------------------------------------------------------------------------------------
' Properties & Settings
' -----------------------------------------------------------------------------------------------

Public Property Get TargetAddr() As String
    TargetAddr = m_targetAddr
End Property

Public Property Get LastError() As String
    LastError = m_lastError
End Property

Public Property Get IsClosed() As Boolean
    IsClosed = m_closed
End Property

Public Sub SetTimeout(ByVal seconds As Double)
    If seconds > 0# Then
        m_timeoutSec = seconds
    End If
End Sub

' -----------------------------------------------------------------------------------------------
' Notification Dispatch Methods (100% Parity with Go, Python, Rust, C++)
' -----------------------------------------------------------------------------------------------

' Send dispatches a standard alert with optional comma-separated destination tags.
Public Function Send(ByVal message As String, Optional ByVal tagsCSV As String = "") As Boolean
    Send = SendWithAttachment("", message, "", tagsCSV)
End Function

' SendAlert dispatches a categorized alert with level (e.g. TRADE, CRITICAL, WARNING, REPORT).
Public Function SendAlert(ByVal level As String, ByVal message As String, Optional ByVal tagsCSV As String = "") As Boolean
    Send = SendWithAttachment(level, message, "", tagsCSV)
End Function

' SendWithAttachment dispatches a full notification payload including attachments.
Public Function SendWithAttachment(ByVal level As String, ByVal message As String, ByVal attachment As String, Optional ByVal tagsCSV As String = "") As Boolean
    If m_closed Then
        m_lastError = "NotificationClient is closed"
        SendWithAttachment = False
        Exit Function
    End If

    If m_targetAddr = "" Then
        m_lastError = "NotificationClient is not initialized (target address is empty)"
        SendWithAttachment = False
        Exit Function
    End If

    Dim rc As Long
    rc = Toolbox.Notif_SendWithTimeout(m_targetAddr, level, message, attachment, tagsCSV, m_timeoutSec)

    If rc <> 0 Then
        Dim errPtr As LongPtr
        errPtr = Toolbox.Notif_GetLastError()
        If errPtr <> 0 Then
            m_lastError = Toolbox.NotifPtrToString(errPtr)
        Else
            m_lastError = "Unknown RPC error (rc=" & CStr(rc) & ")"
        End If
        SendWithAttachment = False
    Else
        m_lastError = ""
        SendWithAttachment = True
    End If
End Function

' -----------------------------------------------------------------------------------------------
' Lifecycle Control
' -----------------------------------------------------------------------------------------------

' CloseClient marks the client as closed, preventing subsequent dispatches.
Public Sub CloseClient()
    m_closed = True
End Sub
