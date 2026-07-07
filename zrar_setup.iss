; Inno Setup Script for ZRar
; Developed by Boubaker Al-Warfali

[Setup]
AppId={{E6F7A965-7489-4D86-B9BC-E47C351B4F9A}}
AppName=ZRar
AppVersion=1.0.0
AppPublisher=Boubaker Al-Warfali
DefaultDirName={autopf}\ZRar
DefaultGroupName=ZRar
UninstallDisplayIcon={app}\ZRar.exe
Compression=lzma2
SolidCompression=yes
OutputDir=.
OutputBaseFilename=ZRar_Setup
PrivilegesRequired=admin
SetupIconFile=ZRar.ico
CloseApplications=yes

[Languages]
Name: "arabic"; MessagesFile: "compiler:Languages\Arabic.isl"

[InstallDelete]
Type: filesandordirs; Name: "{app}\*"

[Files]
Source: "dist\ZRar.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "ZRar.ico"; DestDir: "{app}"; Flags: ignoreversion

[Registry]
; --- Context Menu for Files (Cascading Menu) ---
Root: HKCR; Subkey: "*\shell\ZRar"; ValueType: string; ValueName: "MUIVerb"; ValueData: "ZRar"; Flags: uninsdeletekey
Root: HKCR; Subkey: "*\shell\ZRar"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\ZRar.ico"
Root: HKCR; Subkey: "*\shell\ZRar"; ValueType: string; ValueName: "SubCommands"; ValueData: ""

Root: HKCR; Subkey: "*\shell\ZRar\shell\Compress"; ValueType: string; ValueName: "MUIVerb"; ValueData: "الضغط بـ ZRar..."; Flags: uninsdeletekey
Root: HKCR; Subkey: "*\shell\ZRar\shell\Compress"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\ZRar.ico"
Root: HKCR; Subkey: "*\shell\ZRar\shell\Compress\command"; ValueType: string; ValueName: ""; ValueData: """{app}\ZRar.exe"" -c ""%1"""

Root: HKCR; Subkey: "*\shell\ZRar\shell\Extract"; ValueType: string; ValueName: "MUIVerb"; ValueData: "فك الضغط بـ ZRar..."; Flags: uninsdeletekey
Root: HKCR; Subkey: "*\shell\ZRar\shell\Extract"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\ZRar.ico"
Root: HKCR; Subkey: "*\shell\ZRar\shell\Extract\command"; ValueType: string; ValueName: ""; ValueData: """{app}\ZRar.exe"" -x ""%1"""

Root: HKCR; Subkey: "*\shell\ZRar\shell\ExtractHere"; ValueType: string; ValueName: "MUIVerb"; ValueData: "فك الضغط هنا"; Flags: uninsdeletekey
Root: HKCR; Subkey: "*\shell\ZRar\shell\ExtractHere"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\ZRar.ico"
Root: HKCR; Subkey: "*\shell\ZRar\shell\ExtractHere\command"; ValueType: string; ValueName: ""; ValueData: """{app}\ZRar.exe"" -x ""%1"" --here"

Root: HKCR; Subkey: "*\shell\ZRar\shell\ExtractToDir"; ValueType: string; ValueName: "MUIVerb"; ValueData: "فك الضغط إلى مجلد باسم الملف"; Flags: uninsdeletekey
Root: HKCR; Subkey: "*\shell\ZRar\shell\ExtractToDir"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\ZRar.ico"
Root: HKCR; Subkey: "*\shell\ZRar\shell\ExtractToDir\command"; ValueType: string; ValueName: ""; ValueData: """{app}\ZRar.exe"" -x ""%1"" --to-folder"


; --- Context Menu for Directories (Cascading Menu) ---
Root: HKCR; Subkey: "Directory\shell\ZRar"; ValueType: string; ValueName: "MUIVerb"; ValueData: "ZRar"; Flags: uninsdeletekey
Root: HKCR; Subkey: "Directory\shell\ZRar"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\ZRar.ico"
Root: HKCR; Subkey: "Directory\shell\ZRar"; ValueType: string; ValueName: "SubCommands"; ValueData: ""

Root: HKCR; Subkey: "Directory\shell\ZRar\shell\Compress"; ValueType: string; ValueName: "MUIVerb"; ValueData: "الضغط بـ ZRar..."; Flags: uninsdeletekey
Root: HKCR; Subkey: "Directory\shell\ZRar\shell\Compress"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\ZRar.ico"
Root: HKCR; Subkey: "Directory\shell\ZRar\shell\Compress\command"; ValueType: string; ValueName: ""; ValueData: """{app}\ZRar.exe"" -c ""%1"""


; --- File Association for .zrar ---
Root: HKCR; Subkey: ".zrar"; ValueType: string; ValueName: ""; ValueData: "ZRar.Archive"; Flags: uninsdeletekey
Root: HKCR; Subkey: "ZRar.Archive"; ValueType: string; ValueName: ""; ValueData: "أرشيف ZRar"; Flags: uninsdeletekey
Root: HKCR; Subkey: "ZRar.Archive"; ValueType: string; ValueName: "FriendlyTypeName"; ValueData: "أرشيف ZRar"
Root: HKCR; Subkey: "ZRar.Archive\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\ZRar.ico"
Root: HKCR; Subkey: "ZRar.Archive\shell\open"; ValueType: string; ValueName: "MUIVerb"; ValueData: "فتح الأرشيف بـ ZRar"
Root: HKCR; Subkey: "ZRar.Archive\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\ZRar.exe"" ""%1"""

[Icons]
Name: "{group}\ZRar"; Filename: "{app}\ZRar.exe"
Name: "{autodesktop}\ZRar"; Filename: "{app}\ZRar.exe"

[Run]
Description: "تشغيل ZRar"; Filename: "{app}\ZRar.exe"; Flags: nowait postinstall skipifsilent

[Code]
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  Result := True;
  // Forcibly close ZRar.exe if running to unlock files
  Exec('taskkill.exe', '/f /im ZRar.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

function InitializeUninstall(): Boolean;
var
  ResultCode: Integer;
begin
  Result := True;
  // Forcibly close ZRar.exe before uninstalling
  Exec('taskkill.exe', '/f /im ZRar.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;
