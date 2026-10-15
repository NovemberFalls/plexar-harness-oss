; NSIS hooks for the Plexar Harness installer (tauri.conf.json bundle.windows.nsis.installerHooks).
; Install: create the Plexar profiles under %USERPROFILE%\.dsh from the installed runtime and put
; plexar-runtime\bin (the plexar-harness.cmd shim) on the user PATH. Uninstall: remove that PATH
; entry; profiles and sessions stay. Both run the bundled node.exe against cli\setup.mjs.

!macro NSIS_HOOK_POSTINSTALL
  DetailPrint "Setting up Plexar Harness profiles and the plexar-harness command"
  nsExec::ExecToLog '"$INSTDIR\plexar-runtime\node\node.exe" "$INSTDIR\plexar-runtime\harness\packages\bundle\plexar\cli\setup.mjs" install --path-dir "$INSTDIR\plexar-runtime\bin"'
  Pop $0
  DetailPrint "setup.mjs install exited $0"
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  nsExec::ExecToLog '"$INSTDIR\plexar-runtime\node\node.exe" "$INSTDIR\plexar-runtime\harness\packages\bundle\plexar\cli\setup.mjs" uninstall --path-dir "$INSTDIR\plexar-runtime\bin"'
  Pop $0
!macroend
