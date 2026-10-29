; Zentrix installer (Inno Setup 6).
; Build with: python scripts/build.py
; Compile only: ISCC.exe /DAppVersion=1.0.3 installer\zentrix.iss
;
; Per-user install: no administrator rights, no UAC at install time.
; Engines are copied from dist\Zentrix\engines (never from the source tree).

#ifndef AppName
  #define AppName "Zentrix"
#endif
#ifndef AppVersion
  #define AppVersion "1.0.3"
#endif
#ifndef AppPublisher
  #define AppPublisher "Zentrix Project"
#endif
#ifndef AppURL
  #define AppURL "https://github.com/w1kscc/Zentrix"
#endif

[Setup]
AppId={{6F1D2A54-3C7B-4E90-B1A8-2D4F6C8E9A10}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
VersionInfoVersion={#AppVersion}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription=Zentrix installer
VersionInfoProductName={#AppName}
VersionInfoProductVersion={#AppVersion}

DefaultDirName={userpf}\Zentrix
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
UsePreviousAppDir=yes

; User-scope installation keeps engines/updates writable without elevation.
PrivilegesRequired=lowest

ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763

OutputDir=..\dist\installer
OutputBaseFilename=ZentrixSetup
SetupIconFile=..\assets\brand\zentrix.ico
UninstallDisplayIcon={app}\Zentrix.exe
UninstallDisplayName={#AppName} {#AppVersion}
LicenseFile=..\LICENSE
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
LZMAUseSeparateProcess=yes
SetupLogging=yes
CloseApplications=yes
RestartApplications=no

; The app holds this mutex while running. Setup asks to close it before
; replacing files instead of failing halfway through.
AppMutex=Local\Zentrix.SingleInstance.v1

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
russian.AutostartTask=Запускать Zentrix при входе в Windows
english.AutostartTask=Start Zentrix when Windows starts
russian.AutoGroup=Автозапуск
english.AutoGroup=Startup

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart"; Description: "{cm:AutostartTask}"; GroupDescription: "{cm:AutoGroup}"; Flags: unchecked

[Files]
Source: "..\dist\Zentrix\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; DestName: "README.md"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\Zentrix.exe"; WorkingDir: "{app}"
Name: "{group}\Удалить {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\Zentrix.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Zentrix"; ValueData: """{app}\Zentrix.exe"" --minimized"; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\Zentrix.exe"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Remove only generated cache; user settings live in %APPDATA%\Zentrix and are
; intentionally preserved so reinstalling keeps profiles, presets and history.
Type: filesandordirs; Name: "{app}\engines\.cache"
Type: filesandordirs; Name: "{app}\__pycache__"
