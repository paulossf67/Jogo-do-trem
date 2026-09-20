; Instalador do Jogo do Trem (Inno Setup 6). Gere com instalador\construir.ps1.
; Instala por padrão só para o usuário atual (sem pedir administrador); o assistente oferece
; instalar para todos os usuários.

#define NomeApp "Jogo do Trem"
#define VersaoApp "1.0.0"
#define ExeApp "JogoDoTrem.exe"

[Setup]
AppId={{CEC34DAC-6C00-421F-9F8D-4E6DBD6029AD}
AppName={#NomeApp}
AppVersion={#VersaoApp}
AppVerName={#NomeApp} {#VersaoApp}
AppPublisher=Paulo
DefaultDirName={autopf}\{#NomeApp}
DefaultGroupName={#NomeApp}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#ExeApp}
SetupIconFile=icone.ico
OutputDir=..\dist
OutputBaseFilename=Instalador-JogoDoTrem-{#VersaoApp}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar um atalho na área de trabalho"; GroupDescription: "Atalhos:"; Flags: unchecked

[Files]
Source: "..\dist\JogoDoTrem\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#NomeApp}"; Filename: "{app}\{#ExeApp}"
Name: "{autodesktop}\{#NomeApp}"; Filename: "{app}\{#ExeApp}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#ExeApp}"; Description: "Jogar agora"; Flags: nowait postinstall skipifsilent

[Code]
// O save (nome, recorde, ranking) fica em %APPDATA%\Jogo do Trem e NÃO é apagado por padrão:
// assim uma reinstalação ou atualização mantém o progresso. Ao desinstalar, pergunta se apaga.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  PastaSave: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    PastaSave := ExpandConstant('{userappdata}\{#NomeApp}');
    if DirExists(PastaSave) then
      if MsgBox('Deseja apagar também o seu progresso (nome, recorde e ranking)?' + #13#10 +
                'Se você pretende reinstalar o jogo, escolha "Não".',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(PastaSave, True, True, True);
  end;
end;
