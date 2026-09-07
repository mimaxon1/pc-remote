#define MyAppName "PC Remote"
#define MyAppExeName "PC Remote.exe"
#ifndef AppVersion
  #define AppVersion "0.0.0-dev"
#endif

[Setup]
AppId={{8A5675B9-1F20-4E2B-8BB4-D0C42973F9E4}
AppName={#MyAppName}
AppVersion={#AppVersion}
AppVerName={#MyAppName} {#AppVersion}
AppPublisher=mimaxon1
AppPublisherURL=https://github.com/mimaxon1/pc-remote
AppSupportURL=https://github.com/mimaxon1/pc-remote/issues
AppUpdatesURL=https://github.com/mimaxon1/pc-remote/releases/latest
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\release
OutputBaseFilename=PC-Remote-{#AppVersion}-windows-x64-Setup
SetupIconFile=..\web\favicon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\PC Remote\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\PC Remote"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\PC Remote"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch PC Remote"; Flags: nowait postinstall skipifsilent
