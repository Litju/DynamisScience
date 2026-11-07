#ifndef AppVersion
#define AppVersion "0.1.0"
#endif

#ifndef DistDir
#error "Pass /DDistDir=<PyInstaller onedir folder>"
#endif

#ifndef OutputDir
#define OutputDir "..\dist\installer"
#endif

[Setup]
AppId={{BCEBB9D2-8B9A-4B72-A883-651C31B5CFE1}
AppName=DynamisScience
AppVersion={#AppVersion}
AppPublisher=DynamisScience
DefaultDirName={localappdata}\Programs\DynamisScience
DefaultGroupName=DynamisScience
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
OutputDir={#OutputDir}
OutputBaseFilename=DynamisScience-Setup-x64
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
Name: "{autoprograms}\DynamisScience"; Filename: "{app}\DynamisScience.exe"
Name: "{autodesktop}\DynamisScience"; Filename: "{app}\DynamisScience.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\DynamisScience.exe"; Description: "Launch DynamisScience"; Flags: postinstall nowait skipifsilent

; User research data live under DYNAMISSCIENCE_DATA_ROOT and are never removed by the installer.
