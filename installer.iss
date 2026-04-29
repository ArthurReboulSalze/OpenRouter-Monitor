; Inno Setup script for OpenRouter Monitor
; Creates a professional Windows installer

#define MyAppName "OpenRouter Monitor"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "Hermes"
#define MyAppURL "https://github.com/yourusername/openrouter-monitor"
#define MyAppExeName "OpenRouter Monitor.exe"

[Setup]
AppId={{GENERATE-GUID-HERE}}  ; Replace with a unique GUID
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputBaseFilename=OpenRouterMonitorSetup
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
Name: "french"; MessagesFile: "compiler:Languages\\French.isl"

[Files]
; Main executable
Source: "dist\OpenRouter Monitor.exe"; DestDir: "{app}"; Flags: ignoreversion

; Configuration files (optional, will be created if missing)
Source: "favorites.json"; DestDir: "{app}"; Flags: ignoreversion; Check: not FileExists('{app}\favorites.json')
Source: "models_cache.json"; DestDir: "{app}"; Flags: ignoreversion; Check: not FileExists('{app}\models_cache.json')

; Resources
Source: "*.png"; DestDir: "{app}"; Flags: ignoreversion

; Documentation
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion; Tasks: "readme"
Source: "LICENSE"; DestDir: "{app}"; Flags: ignoreversion; Tasks: "license"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Paramètres"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--settings"; IconFilename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\Site Web OpenRouter"; Filename: "https://openrouter.ai"; Comment: "OpenRouter AI Website"
Name: "{group}\Désinstaller {#MyAppName}"; Filename: "{uninstallexe}"

; Desktop icon (optional)
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: "desktopicon"

[Tasks]
Name: "desktopicon"; Description: "Créer une icône sur le bureau"; GroupDescription: "Icônes additionnelles:"
Name: "readme"; Description: "Créer un raccourci vers la documentation"; GroupDescription: "Tâches additionnelles:"
Name: "license"; Description: "Inclure le fichier de licence"; GroupDescription: "Tâches additionnelles:"

[Run]
; Start the application after installation
Filename: "{app}\{#MyAppExeName}"; Description: "Lancer {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Clean up configuration on uninstall (optional - comment out to preserve user data)
;Filename: "cmd.exe"; Parameters: "/C rmdir /s /q ""{userappdata}\OpenRouter Monitor"""; Flags: runhidden

[Registry]
; Add uninstall info
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppName}"; ValueType: string; ValueName: "DisplayName"; ValueData: "{#MyAppName}"; Flags: uninsdeletekey

[Code]
// Custom code for advanced operations
function InitializeSetup(): Boolean;
begin
  Result := True;
end;
