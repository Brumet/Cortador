; Instalador de Cortador para Windows (Inno Setup 6)
;
;   iscc /DMiVersion=0.4.1 packaging\cortador.iss
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
; la app se empaqueta en carpeta (CORTADOR_MODO=carpeta): asi abre en un
; segundo en vez de descomprimirse entera en cada arranque
Source: "..\dist\Cortador\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md"; DestDir: "{app}"; DestName: "LEEME.md"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MiNombre}"; Filename: "{app}\{#MiEjecutable}"
Name: "{group}\Guia de uso"; Filename: "{app}\LEEME.md"
Name: "{group}\Diagnostico de {#MiNombre}"; Filename: "{app}\{#MiEjecutable}"; Parameters: "--diagnostico"; Comment: "Genera un informe si la app no abre"
Name: "{group}\Registro de arranque"; Filename: "{app}\{#MiEjecutable}"; Parameters: "--registro"; Comment: "Abre el registro del ultimo arranque"
Name: "{group}\Desinstalar {#MiNombre}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MiNombre}"; Filename: "{app}\{#MiEjecutable}"; Tasks: escritorio

[Run]
Filename: "{app}\{#MiEjecutable}"; Description: "Abrir {#MiNombre} ahora"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{app}\cortador_error.log"
Type: files; Name: "{app}\cortador_diagnostico.txt"
Type: filesandordirs; Name: "{localappdata}\Cortador"

[Code]
// La ventana de la app es WebView2 (el mismo motor de Edge). Windows 10 y 11
// lo traen de serie, pero en equipos muy limpios o con Edge quitado no esta,
// y entonces la app se abriria en el navegador. Mejor avisar durante la
// instalacion que dejar que el usuario lo descubra despues.
function HayWebView2(): Boolean;
var
  version: String;
begin
  Result := RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', version)
         or RegQueryStringValue(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', version)
         or RegQueryStringValue(HKCU, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', version);
  if Result then
    Result := (version <> '') and (version <> '0.0.0.0');
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  codigo: Integer;
begin
  if (CurStep = ssPostInstall) and (not HayWebView2()) then
  begin
    if MsgBox('A este equipo le falta WebView2, que es lo que Cortador usa para su ventana.' + #13#10#13#10 +
              'Sin el, Cortador funciona igual pero se abre en el navegador.' + #13#10#13#10 +
              'Quieres descargarlo ahora desde Microsoft? (se abre la pagina oficial)',
              mbConfirmation, MB_YESNO) = IDYES then
      ShellExec('open', 'https://developer.microsoft.com/microsoft-edge/webview2/', '', '', SW_SHOW, ewNoWait, codigo);
  end;
end;
