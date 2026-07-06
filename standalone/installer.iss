; 飞飞转录 · 单机版 · Windows 安装程序
; 需要 Inno Setup 6.x 编译

#define AppName      "飞飞转录"
#define AppVersion   "1.0.0"
#define AppPublisher "飞飞转录"
#define AppExeName   "飞飞转录.exe"
#define AppSrcDir    "dist\飞飞转录"

[Setup]
AppId={{8F3A2C1D-4E6B-4A9C-B8D2-7F5E3A1C9B0E}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisherURL=https://github.com
AppSupportURL=https://github.com
AppUpdatesURL=https://github.com
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
LicenseFile=
OutputDir=dist
OutputBaseFilename=飞飞转录单机版_Setup_{#AppVersion}
SetupIconFile=
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
; 需要 Windows 10 或更高版本
MinVersion=10.0
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog

; 安装程序界面语言（简体中文）
[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "在桌面创建快捷方式(&D)"; GroupDescription: "附加任务："; Flags: unchecked

[Files]
Source: "{#AppSrcDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\卸载 {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "启动飞飞转录"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Messages]
; 自定义欢迎界面文字
WelcomeLabel1=欢迎安装 [name]
WelcomeLabel2=本安装向导将把 [name] 安装到您的电脑上。%n%n飞飞转录单机版内置 Whisper small 语音识别模型，%n无需网络，无需服务端，即可在本地完成语音转文字。%n%n建议关闭其他程序后再继续安装。
FinishedLabel=飞飞转录已成功安装！%n%n首次启动约需 5-15 秒加载模型，请耐心等待。
