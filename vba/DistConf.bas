Attribute VB_Name = "DistConf"
' -----------------------------------------------------------------------------------------------
' ESSENTIAL PROCESS:
' Raw FFI declarations and bridge bindings connecting VBA to the libdistconf Go CGO shared library.
'
' DATA FLOW:
' 1. Input: Profile names, section/key requests, and address lookups from VBA callers.
' 2. Logic: Marshals calls across the C ABI boundary into libdistconf.
' 3. Output: Raw C pointers, string buffers, and status codes returned to AppConfig.
'
' KEY PARAMETERS:
' - LIB_PATH: Path to the compiled libdistconf shared library (.dylib or .dll).
' -----------------------------------------------------------------------------------------------

Option Explicit

#If Mac Then
    Private Const LIB_PATH As String = "/usr/local/lib/libdistconf.dylib"
#Else
    Private Const LIB_PATH As String = "libdistconf.dll"
#End If

' Core Lifecycle
' -----------------------------------------------------------------------------------------------
Public Declare PtrSafe Function DistConf_New Lib LIB_PATH (ByVal profile As String) As LongPtr
Public Declare PtrSafe Sub DistConf_Close Lib LIB_PATH (ByVal handle As LongPtr)

' Data Access
' -----------------------------------------------------------------------------------------------
Public Declare PtrSafe Function DistConf_Get Lib LIB_PATH (ByVal handle As LongPtr, ByVal section As String, ByVal key As String) As LongPtr
Public Declare PtrSafe Function DistConf_GetAddress Lib LIB_PATH (ByVal handle As LongPtr, ByVal capability As String) As LongPtr
Public Declare PtrSafe Function DistConf_GetGRPCAddress Lib LIB_PATH (ByVal handle As LongPtr, ByVal capability As String) As LongPtr
Public Declare PtrSafe Function DistConf_GetRESTAddress Lib LIB_PATH (ByVal handle As LongPtr, ByVal capability As String) As LongPtr
Public Declare PtrSafe Function DistConf_GetCapability Lib LIB_PATH (ByVal handle As LongPtr, ByVal capability As String) As LongPtr
Public Declare PtrSafe Function DistConf_GetFullConfig Lib LIB_PATH (ByVal handle As LongPtr) As LongPtr

' Data Mutation
' -----------------------------------------------------------------------------------------------
Public Declare PtrSafe Function DistConf_Set Lib LIB_PATH (ByVal handle As LongPtr, ByVal section As String, ByVal key As String, ByVal value As String) As Long
Public Declare PtrSafe Function DistConf_ShareConfig Lib LIB_PATH (ByVal handle As LongPtr, ByVal json As String) As Long

' Security & Validation
' -----------------------------------------------------------------------------------------------
Public Declare PtrSafe Function DistConf_Decrypt Lib LIB_PATH (ByVal handle As LongPtr, ByVal ciphertext As String) As LongPtr
Public Declare PtrSafe Function DistConf_ValidateMandatoryServices Lib LIB_PATH (ByVal handle As LongPtr) As Long
Public Declare PtrSafe Function DistConf_GetLastError Lib LIB_PATH () As LongPtr

' Memory Management
' -----------------------------------------------------------------------------------------------
Public Declare PtrSafe Sub DistConf_FreeString Lib LIB_PATH (ByVal ptr As LongPtr)
