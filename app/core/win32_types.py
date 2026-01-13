"""
Windows API types and constants used via ctypes.
"""

import ctypes
from ctypes import wintypes


class OPENFILENAMEW(ctypes.Structure):
    """Structure for Windows file open/save dialogs."""

    _fields_ = [
        ("lStructSize", wintypes.DWORD),
        ("hwndOwner", wintypes.HWND),
        ("hInstance", wintypes.HINSTANCE),
        ("lpstrFilter", wintypes.LPCWSTR),
        ("lpstrCustomFilter", wintypes.LPWSTR),
        ("nMaxCustFilter", wintypes.DWORD),
        ("nFilterIndex", wintypes.DWORD),
        ("lpstrFile", wintypes.LPWSTR),
        ("nMaxFile", wintypes.DWORD),
        ("lpstrFileTitle", wintypes.LPWSTR),
        ("nMaxFileTitle", wintypes.DWORD),
        ("lpstrInitialDir", wintypes.LPCWSTR),
        ("lpstrTitle", wintypes.LPCWSTR),
        ("Flags", wintypes.DWORD),
        ("nFileOffset", wintypes.WORD),
        ("nFileExtension", wintypes.WORD),
        ("lpstrDefExt", wintypes.LPCWSTR),
        ("lCustData", wintypes.LPARAM),
        ("lpfnHook", ctypes.c_void_p),
        ("lpTemplateName", wintypes.LPCWSTR),
        ("pvReserved", ctypes.c_void_p),
        ("dwReserved", wintypes.DWORD),
        ("FlagsEx", wintypes.DWORD),
    ]


# Common dialog flags
OFN_EXPLORER = 0x00080000
OFN_OVERWRITEPROMPT = 0x00000002
OFN_FILEMUSTEXIST = 0x00001000
OFN_PATHMUSTEXIST = 0x00000800


# Window management constants
GWL_WNDPROC = -4
WM_GETMINMAXINFO = 0x0024


# Font enumeration structures
class LOGFONT(ctypes.Structure):
    """Logical font structure for font enumeration."""

    _fields_ = [
        ("lfHeight", ctypes.c_long),
        ("lfWidth", ctypes.c_long),
        ("lfEscapement", ctypes.c_long),
        ("lfOrientation", ctypes.c_long),
        ("lfWeight", ctypes.c_long),
        ("lfItalic", ctypes.c_byte),
        ("lfUnderline", ctypes.c_byte),
        ("lfStrikeOut", ctypes.c_byte),
        ("lfCharSet", ctypes.c_byte),
        ("lfOutPrecision", ctypes.c_byte),
        ("lfClipPrecision", ctypes.c_byte),
        ("lfQuality", ctypes.c_byte),
        ("lfPitchAndFamily", ctypes.c_byte),
        ("lfFaceName", ctypes.c_wchar * 32),
    ]


class ENUMLOGFONTEXW(ctypes.Structure):
    """Extended logical font structure for font enumeration."""

    _fields_ = [
        ("elfLogFont", LOGFONT),
        ("elfFullName", ctypes.c_wchar * 64),
        ("elfStyle", ctypes.c_wchar * 32),
        ("elfScript", ctypes.c_wchar * 32),
    ]


class NEWTEXTMETRICW(ctypes.Structure):
    """Text metrics structure for font properties."""

    _fields_ = [
        ("tmHeight", ctypes.c_long),
        ("tmAscent", ctypes.c_long),
        ("tmDescent", ctypes.c_long),
        ("tmInternalLeading", ctypes.c_long),
        ("tmExternalLeading", ctypes.c_long),
        ("tmAveCharWidth", ctypes.c_long),
        ("tmMaxCharWidth", ctypes.c_long),
        ("tmWeight", ctypes.c_long),
        ("tmOverhang", ctypes.c_long),
        ("tmDigitizedAspectX", ctypes.c_long),
        ("tmDigitizedAspectY", ctypes.c_long),
        ("tmFirstChar", ctypes.c_wchar),
        ("tmLastChar", ctypes.c_wchar),
        ("tmDefaultChar", ctypes.c_wchar),
        ("tmBreakChar", ctypes.c_wchar),
        ("tmItalic", ctypes.c_byte),
        ("tmUnderlined", ctypes.c_byte),
        ("tmStruckOut", ctypes.c_byte),
        ("tmPitchAndFamily", ctypes.c_byte),
        ("tmCharSet", ctypes.c_byte),
        ("ntmFlags", ctypes.c_ulong),
        ("ntmSizeEM", ctypes.c_uint),
        ("ntmCellHeight", ctypes.c_uint),
        ("ntmAvgWidth", ctypes.c_uint),
    ]


# Font enumeration callback function type
FONTENUMPROC = ctypes.WINFUNCTYPE(
    ctypes.c_int, ctypes.POINTER(ENUMLOGFONTEXW), ctypes.POINTER(NEWTEXTMETRICW), ctypes.c_uint, ctypes.c_void_p
)


# Window management structures
class POINT(ctypes.Structure):
    """Windows point structure."""

    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class MINMAXINFO(ctypes.Structure):
    """Window min/max size information."""

    _fields_ = [
        ("ptReserved", POINT),
        ("ptMaxSize", POINT),
        ("ptMaxPosition", POINT),
        ("ptMinTrackSize", POINT),
        ("ptMaxTrackSize", POINT),
    ]


# Display configuration structures
class LUID(ctypes.Structure):
    """Locally Unique Identifier."""

    _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]


class DISPLAYCONFIG_PATH_INFO(ctypes.Structure):
    """Display configuration path information."""

    _fields_ = [
        ("sourceLUID", LUID),
        ("sourceId", wintypes.UINT),
        ("sourceModeIdx", wintypes.UINT),
        ("sourceFlags", wintypes.UINT),
        ("targetLUID", LUID),
        ("targetId", wintypes.UINT),
        ("targetModeIdx", wintypes.UINT),
        ("targetTech", wintypes.UINT),
        ("targetRotation", wintypes.UINT),
        ("targetScaling", wintypes.UINT),
        ("targetRefreshNum", wintypes.UINT),
        ("targetRefreshDen", wintypes.UINT),
        ("targetScanLine", wintypes.UINT),
        ("targetAvailable", wintypes.BOOL),
        ("targetFlags", wintypes.UINT),
        ("flags", wintypes.UINT),
    ]


class DISPLAYCONFIG_TARGET_DEVICE_NAME(ctypes.Structure):
    """Monitor device name information."""

    _fields_ = [
        ("type", wintypes.UINT),
        ("size", wintypes.UINT),
        ("adapterLUID", LUID),
        ("id", wintypes.UINT),
        ("flags", wintypes.UINT),
        ("outputTech", wintypes.UINT),
        ("edidMfg", wintypes.USHORT),
        ("edidProduct", wintypes.USHORT),
        ("connectorInstance", wintypes.UINT),
        ("monitorFriendlyDeviceName", wintypes.WCHAR * 64),
        ("monitorDevicePath", wintypes.WCHAR * 128),
    ]
