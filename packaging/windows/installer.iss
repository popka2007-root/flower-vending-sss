; Flower Vending System - Inno Setup Installer Script
; Place this file in packaging/windows/ and compile with Inno Setup.

[Setup]
AppName=Flower Vending System
AppVersion=1.0.0
AppPublisher=Flower Vending
DefaultDirName={pf}\FlowerVending
DefaultGroupName=Flower Vending
OutputDir=..\..\dist
OutputBaseFilename=FlowerVending-Setup
Compression=lzma
SolidCompression=yes
UninstallDisplayIcon={app}\FlowerVending.exe
PrivilegesRequired=admin

[Files]
Source: "..\..\dist\FlowerVending.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\config\machine.production.yaml"; DestDir: "{app}\config"; Flags: ignoreversion
Source: "..\..\scripts\start_production.bat"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Flower Vending"; Filename: "{app}\FlowerVending.exe"
Name: "{group}\Uninstall Flower Vending"; Filename: "{uninstallexe}"
Name: "{commondesktop}\Flower Vending"; Filename: "{app}\FlowerVending.exe"

[Run]
Filename: "{app}\FlowerVending.exe"; Description: "Launch Flower Vending"; Flags: postinstall nowait skipifsilent
