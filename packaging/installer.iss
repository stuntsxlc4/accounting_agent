; Instalator Windows (Inno Setup) z folderu zbudowanego przez packaging/faktury-ksef.spec:
;   iscc /DAppVersion=0.1.0 packaging\installer.iss
; Instaluje do profilu użytkownika, bez uprawnień administratora. Nowa wersja instaluje się
; na starą; ustawienia, hasło w sejfie i dane aplikacji zostają (także po odinstalowaniu).

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "Faktury KSeF"
#define AppExe "Faktury KSeF.exe"

[Setup]
; Stały identyfikator: dzięki niemu kolejne wersje aktualizują tę samą instalację
AppId={{B73F8D62-60DB-40B3-A101-AFB9435B5C27}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
DefaultDirName={localappdata}\Programs\{#AppName}
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
MinVersion=10.0
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
OutputDir=..\dist
OutputBaseFilename=Faktury-KSeF-Setup-{#AppVersion}

[Languages]
Name: "polish"; MessagesFile: "compiler:Languages\Polish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; Biblioteki poprzedniej wersji, żeby nie zostały w folderze stare pliki
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\{#AppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
