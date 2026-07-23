#define MyAppName "PC Remote"
#define MyAppVersion "1.4.1"
#define MyAppPublisher "mimaxon1"
#define MyAppExeName "PC Remote.exe"
#define FirewallRuleName "PC Remote LAN"

[Setup]
AppId={{B0D5BE86-E060-4F59-AE9C-78C0E67B4A9D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
OutputDir=..\dist\installer
OutputBaseFilename=PC-Remote-Setup-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
CloseApplications=yes
RestartApplications=no

[Files]
Source: "..\dist\PC Remote\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительные ярлыки:"; Flags: unchecked

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue

[Run]
Filename: "{cmd}"; Parameters: "/C netsh advfirewall firewall delete rule name=\"{#FirewallRuleName}\" >NUL 2>&1"; Flags: runhidden waituntilterminated
Filename: "{cmd}"; Parameters: "/C netsh advfirewall firewall add rule name=\"{#FirewallRuleName}\" dir=in action=allow program=\"{app}\{#MyAppExeName}\" enable=yes profile=private,domain"; Flags: runhidden waituntilterminated
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C netsh advfirewall firewall delete rule name=\"{#FirewallRuleName}\""; Flags: runhidden waituntilterminated
