; 飞飞转录 · 单机版 · Windows Installer
; Inno Setup 6.x

#define AppName      "飞飞转录"
#define AppVersion   "1.0.0"
#define AppExeName   "飞飞转录.exe"
#define AppSrcDir    "dist\飞飞转录"

[Setup]
AppId={{8F3A2C1D-4E6B-4A9C-B8D2-7F5E3A1C9B0E}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
OutputDir=dist
OutputBaseFilename=飞飞转录单机版_Setup_{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
MinVersion=10.0
PrivilegesRequired=admin

[Files]
Source: "{#AppSrcDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\卸载 {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; Flags: unchecked

[Run]
Filename: "{app}\{#AppExeName}"; Description: "启动飞飞转录"; Flags: nowait postinstall skipifsilent
