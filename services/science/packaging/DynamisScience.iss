#ifndef AppVersion
#define AppVersion "0.1.0"
#endif

#ifndef DistDir
#error "Pass /DDistDir=<PyInstaller onedir folder>"
#endif

#ifndef OutputDir
#define OutputDir "..\dist\installer"
#endif

; Production identity by default. Pass /DTestIdentity=1 to build an installer with a separate AppId, name,
; install directory and uninstall registration that cannot touch an existing DynamisScience installation.
#ifdef TestIdentity
#define AppIdValue "{{5B1E2C4A-7D3F-4E8B-9A61-0C2D4F6A8B13}"
#define AppNameValue "DynamisScience RES621 Test"
#define AppDirName "DynamisScienceRES621Test"
#define SetupName "DynamisScience-RES621Test-Setup-x64"
#else
#define AppIdValue "{{BCEBB9D2-8B9A-4B72-A883-651C31B5CFE1}"
#define AppNameValue "DynamisScience"
#define AppDirName "DynamisScience"
#define SetupName "DynamisScience-Setup-x64"
#endif

[Setup]
AppId={#AppIdValue}
AppName={#AppNameValue}
AppVersion={#AppVersion}
AppPublisher=DynamisScience
DefaultDirName={localappdata}\Programs\{#AppDirName}
DefaultGroupName={#AppNameValue}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
OutputDir={#OutputDir}
OutputBaseFilename={#SetupName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\DynamisScience.exe
CloseApplications=yes
RestartIfNeededByRun=no

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppNameValue}"; Filename: "{app}\DynamisScience.exe"
Name: "{autodesktop}\{#AppNameValue}"; Filename: "{app}\DynamisScience.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\DynamisScience.exe"; Description: "Launch DynamisScience"; Flags: postinstall nowait skipifsilent

; User research data live under DYNAMISSCIENCE_DATA_ROOT and are never removed by the installer.
