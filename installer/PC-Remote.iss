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

[Code]
// The application owns opt-in autostart. Do not enable it during installation.
// On uninstall, remove only entries targeting this installation, never another
// portable/source installation or a customized startup command.
procedure RemoveOwnedStartupFile(const Name: String);
var
  Filename, Expected: String;
  Content: AnsiString;
  Owned: Boolean;
begin
  Filename := ExpandConstant('{userstartup}\') + Name;
  Expected := '@echo off' + #13#10 + 'start "" /b "' +
    ExpandConstant('{app}\{#MyAppExeName}') + '"' + #13#10;
  if LoadStringFromFile(Filename, Content) then
  begin
    Owned := Content = UTF8Encode(Expected);
    // Python's Windows text writer historically doubled the carriage return.
    StringChangeEx(Expected, #13#10, #13#13#10, True);
    Owned := Owned or (Content = UTF8Encode(Expected));
    if Owned then
      if not DeleteFile(Filename) then
        Log('Could not remove owned startup file: ' + Filename);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Command, Expected: String;
begin
  if CurUninstallStep = usUninstall then
  begin
    RemoveOwnedStartupFile('PC Remote.cmd');
    RemoveOwnedStartupFile('PC-Android.cmd');
    // Compatibility with the unmerged Run-key installer experiment.
    Expected := '"' + ExpandConstant('{app}\{#MyAppExeName}') + '"';
    if RegQueryStringValue(HKCU,
      'Software\Microsoft\Windows\CurrentVersion\Run', 'PC Remote', Command) then
      if Command = Expected then
        if not RegDeleteValue(HKCU,
          'Software\Microsoft\Windows\CurrentVersion\Run', 'PC Remote') then
          Log('Could not remove owned PC Remote Run value');
  end;
end;
