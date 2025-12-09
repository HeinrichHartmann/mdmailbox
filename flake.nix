{
  description = "mdmail development environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
      in
      {
        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            uv
            python313
            ruff
            pre-commit
          ];

          shellHook = ''
            export UV_PYTHON_PREFERENCE=only-system
            export UV_PYTHON_DOWNLOADS=never
          '';
        };
      });
}
