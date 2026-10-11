; Inno Setup script for OpenRouter Monitor
; Creates a professional Windows installer

#define MyAppName "OpenRouter Monitor"
#define MyAppVersion "1.1.0"
#define MyAppPublisher "Arthur Reboul Salze"
#define MyAppURL "https://github.com/ArthurReboulSalze/OpenRouter-Monitor"
#define MyAppExeName "OpenRouter Monitor.exe"

[Setup]
AppId={{0F526AC8-59D2-49E5-9909-F24AC5D2985F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputBaseFilename=OpenRouterMonitorSetup
OutputDir=Output
SetupIconFile=MEDIAS\openrouter-monitor.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma
SolidCompression=yes
PrivilegesRequired=lowest
WizardStyle=modern
ShowLanguageDialog=no
LZMAUseFilter=1

; Windows 10+ compatibility
MinVersion=10.0,10.0.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Files]
; Main executable
Source: "dist\OpenRouter Monitor.exe"; DestDir: "{app}"; Flags: ignoreversion

; Documentation
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion; Tasks: "readme"
Source: "OpenRouter_Monitor_SC.png"; DestDir: "{app}"; Flags: ignoreversion; Tasks: "readme"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Documentation"; Filename: "{app}\README.md"; Tasks: "readme"
Name: "{group}\Site Web OpenRouter"; Filename: "https://openrouter.ai"; Comment: "OpenRouter AI Website"
Name: "{group}\Désinstaller {#MyAppName}"; Filename: "{uninstallexe}"

; Desktop icon (optional)
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: "desktopicon"

[Tasks]
Name: "desktopicon"; Description: "Créer une icône sur le bureau"; GroupDescription: "Icônes additionnelles:"
Name: "readme"; Description: "Créer un raccourci vers la documentation"; GroupDescription: "Tâches additionnelles:"

[Run]
; Start the application after installation
Filename: "{app}\{#MyAppExeName}"; Description: "Lancer {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Clean up configuration on uninstall (optional - comment out to preserve user data)
;Filename: "cmd.exe"; Parameters: "/C rmdir /s /q ""{userappdata}\OpenRouter Monitor"""; Flags: runhidden

[Code]
// Custom code for advanced operations
function InitializeSetup(): Boolean;
begin
  Result := True;
end;
