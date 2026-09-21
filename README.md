# bedROK

Safe Minecraft Bedrock **companion** (Windows x64).

## Working modules (no PvP)
| Module | How |
|--------|-----|
| Fullbright | Windows gamma ramp (restored on off) |
| Overlay watermark | Layered topmost window |
| Crosshair | Drawn on overlay |
| Clock | Local time |
| Array list | Enabled module names |

**Hotkeys:** F1 Fullbright · F2 Crosshair · F3 Clock · F4 Array list · F5 Watermark

## Not included
ESP, nametags, reach, trigger bot, velocity, or any combat module.

## Build with GitHub Actions
1. Push to `main` or run **Actions → Build bedROK → Run workflow**
2. Download **Artifacts → bedrok-windows** (`bedrok.dll` + `bedrok_loader.exe`)
3. Or tag `v1.0.0` to create a Release with the binaries

## Local build
### DLL
```bat
cd dll
cmake -B build -A x64
cmake --build build --config Release
```
### Loader EXE
```bat
cd loader
build_exe.bat
```

## Use
1. Start Minecraft Bedrock  
2. Run `bedrok_loader.exe`  
3. Select `Minecraft.Windows.exe` + `bedrok.dll` → Inject  
4. Log: `C:\Users\Public\bedrok.log`

## Website
See `website/index.html` — deploy with Vercel from this repo.
