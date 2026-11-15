{ lib, stdenvNoCC, python3 }:

stdenvNoCC.mkDerivation {
  pname = "ascii-fish-tank";
  version = "0.3.0";

  src = ./ascii_fish_tank.py;
  dontUnpack = true;

  # -I runs Python in isolated mode, so PYTHONPATH and the user site
  # directory cannot swap out the modules the script imports.
  installPhase = ''
    runHook preInstall
    mkdir -p $out/bin
    echo "#!${python3.interpreter} -I" > $out/bin/ascii-fish-tank
    tail -n +2 $src >> $out/bin/ascii-fish-tank
    chmod 755 $out/bin/ascii-fish-tank
    runHook postInstall
  '';

  doInstallCheck = true;
  installCheckPhase = ''
    $out/bin/ascii-fish-tank --version
    $out/bin/ascii-fish-tank --snapshot --no-color > /dev/null
  '';

  meta = {
    description = "Fish tank for the terminal, with an optional clock";
    mainProgram = "ascii-fish-tank";
    platforms = lib.platforms.unix;
  };
}
