; Bộ cài OCR-Nhat (Inno Setup). Đường dẫn tương đối theo thư mục chứa file này.
; Chạy: ISCC.exe installer\OCR-Nhat.iss  (sau khi PyInstaller đã tạo dist\OCR-Nhat)

[Setup]
AppName=OCR-Nhat
AppVersion=0.1.0
AppPublisher=Nguyễn Thanh Quang
DefaultDirName={autopf}\OCR-Nhat
DefaultGroupName=OCR-Nhat
OutputDir=..\installer_out
OutputBaseFilename=OCR-Nhat-setup
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\OCR-Nhat.exe

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Tạo biểu tượng trên màn hình"; GroupDescription: "Biểu tượng:"

[Files]
Source: "..\dist\OCR-Nhat\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\OCR-Nhat"; Filename: "{app}\OCR-Nhat.exe"
Name: "{group}\Gỡ cài đặt OCR-Nhat"; Filename: "{uninstallexe}"
Name: "{autodesktop}\OCR-Nhat"; Filename: "{app}\OCR-Nhat.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\OCR-Nhat.exe"; Description: "Chạy OCR-Nhat"; Flags: nowait postinstall skipifsilent
