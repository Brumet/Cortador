; Instalador de Cortador para Windows (Inno Setup 6)
;
;   iscc /DMiVersion=0.4.0 packaging\cortador.iss
;
; Instala en la carpeta del usuario, asi que no pide permisos de
; administrador, crea accesos directos y deja su desinstalador.

#ifndef MiVersion
  #define MiVersion "0.0.0"
#endif

#define MiNombre "Cortador"
#define MiAutor "Brumet"
#define MiWeb "https://github.com/Brumet/Cortador"
#define MiEjecutable "Cortador.exe"

[Setup]
AppId={{B2C8A6F1-4E7D-4C21-9A3B-5D8F1C0E7A42}
AppName={#MiNombre}
AppVersion={#MiVersion}
AppVerName={#MiNombre} {#MiVersion}
AppPublisher={#MiAutor}
AppPublisherURL={#MiWeb}
AppSupportURL={#MiWeb}/issues
AppUpdatesURL={#MiWeb}/releases
DefaultDirName={autopf}\{#MiNombre}
DefaultGroupName={#MiNombre}
DisableProgramGroupPage=yes
DisableDirPage=no
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=Cortador-Setup
SetupIconFile=cortador.ico
UninstallDisplayIcon={app}\{#MiEjecutable}
UninstallDisplayName={#MiNombre} {#MiVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
MinVersion=10.0
LicenseFile=..\LICENSE

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "escritorio"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"

[Files]
Source: "..\dist\{#MiEjecutable}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; DestName: "LEEME.md"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MiNombre}"; Filename: "{app}\{#MiEjecutable}"
Name: "{group}\Guia de uso"; Filename: "{app}\LEEME.md"
Name: "{group}\Desinstalar {#MiNombre}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MiNombre}"; Filename: "{app}\{#MiEjecutable}"; Tasks: escritorio

[Run]
Filename: "{app}\{#MiEjecutable}"; Description: "Abrir {#MiNombre} ahora"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{app}\cortador_error.log"
Type: files; Name: "{app}\cortador_diagnostico.txt"
