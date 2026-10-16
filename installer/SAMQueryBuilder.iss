; Inno Setup script for SAM Ad Hoc Query Builder
; Built by the Build GUI:  ISCC.exe /DMyAppVersion=1.0.0 installer\SAMQueryBuilder.iss
; Installs per-user by default (no admin prompt) so silent auto-updates work for every staff member.

#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif
#define MyAppName "SAM Ad Hoc Query Builder"
#define MyAppPublisher "Hancock County School District"
#define MyAppExeName "SAM Ad Hoc Query Builder.exe"
#define MyAppURL "https://github.com/Sbreland18/SAMQueryBuilder"
#define SourceDir "..\dist\SAM Ad Hoc Query Builder"

[Setup]
AppId={{6E7B2C4A-3D51-4F7E-9A1C-5B2D8E0F4A11}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist\installer
OutputBaseFilename=SAM_AdHoc_Query_Builder_Setup_{#MyAppVersion}
SetupIconFile=..\assets\app.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
ChangesAssociations=yes
VersionInfoVersion={#MyAppVersion}
VersionInfoProductName={#MyAppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "assoc"; Description: "Open .samq query files with {#MyAppName}"; GroupDescription: "File association:"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\.samq"; ValueType: string; ValueName: ""; ValueData: "SAMAdHocQuery"; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\SAMAdHocQuery"; ValueType: string; ValueName: ""; ValueData: "SAM Ad Hoc Query"; Flags: uninsdeletekey; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\SAMAdHocQuery\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\SAMAdHocQuery\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: assoc

[Run]
; normal install: offer to launch
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
; silent auto-update: relaunch automatically
Filename: "{app}\{#MyAppExeName}"; Flags: nowait runasoriginaluser; Check: WizardSilent

[Code]
// Give the running app a moment to exit after it launches the updater.
function InitializeSetup(): Boolean;
begin
  if WizardSilent then
    Sleep(1500);
  Result := True;
end;
