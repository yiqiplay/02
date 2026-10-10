; MediaConv Windows 安装包脚本
; 用 Inno Setup 编译：ISCC.exe tools\installer.iss
; 注意：本文件必须保存为 UTF-8 with BOM，否则中文会乱码。

#define MyAppName "格式转换器"
#define MyAppNameEn "MediaConv"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "xiaoke"
#define MyAppExeName "MediaConv.exe"

[Setup]
AppId={{8F3A6C21-4D7E-4B92-9A15-2C7E5B8D4F31}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppNameEn}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}
OutputDir=..\dist
OutputBaseFilename=MediaConv-Setup-{#MyAppVersion}
SetupIconFile=..\assets\icon.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
MinVersion=10.0
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DisableDirPage=no
AllowNoIcons=yes
VersionInfoVersion={#MyAppVersion}
VersionInfoDescription={#MyAppName} 安装程序
VersionInfoProductName={#MyAppName}
VersionInfoCompany={#MyAppPublisher}
VersionInfoCopyright=Copyright (C) 2026 {#MyAppPublisher}

[Languages]
Name: "chinese"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："
Name: "contextmenu"; Description: "在右键菜单添加「用格式转换器打开」"; GroupDescription: "附加任务："; Flags: unchecked

[Files]
; 整个免安装目录打包进来（含 ffmpeg / ffprobe / Qt 运行库）
Source: "..\dist\MediaConv\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\使用说明"; Filename: "{app}\使用说明.txt"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; 右键菜单：对任意文件显示「用格式转换器打开」
Root: HKCU; Subkey: "Software\Classes\*\shell\MediaConv"; ValueType: string; ValueName: ""; ValueData: "用格式转换器转换"; Flags: uninsdeletekey; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\*\shell\MediaConv"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\{#MyAppExeName},0"; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\*\shell\MediaConv\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: contextmenu

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal\__pycache__"

[Code]
// 安装前检查是否已有旧版本在运行，避免文件占用导致安装失败
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  Result := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // 无操作：保留钩子便于以后扩展
  end;
end;
