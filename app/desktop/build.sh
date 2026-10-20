#!/bin/sh
# Builds "F5 Studio.app" from main.swift and installs it in ~/Applications
# (needs the Xcode command line tools). Re-run after changing main.swift.
set -e
cd "$(dirname "$0")"
APP="F5 Studio.app"
rm -rf "$APP" build
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources" build/icon.iconset
swiftc -O -o "$APP/Contents/MacOS/F5Studio" main.swift -framework Cocoa -framework WebKit

# icon: full-bleed (make_icon.py) so macOS 26 masks it itself, with no white tile around it
for s in 16 32 128 256 512; do
  sips -z $s $s icon_1024.png --out build/icon.iconset/icon_${s}x${s}.png >/dev/null
  sips -z $((s * 2)) $((s * 2)) icon_1024.png --out build/icon.iconset/icon_${s}x${s}@2x.png >/dev/null
done
iconutil -c icns build/icon.iconset -o "$APP/Contents/Resources/AppIcon.icns"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleIdentifier</key><string>local.f5-studio</string>
  <key>CFBundleName</key><string>F5 Studio</string>
  <key>CFBundleDisplayName</key><string>F5 Studio</string>
  <key>CFBundleExecutable</key><string>F5Studio</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>0.1</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSAppTransportSecurity</key><dict><key>NSAllowsLocalNetworking</key><true/></dict>
</dict>
</plist>
PLIST
codesign --force --sign - --identifier local.f5-studio "$APP"
rm -rf build

mkdir -p "$HOME/Applications"
rm -rf "$HOME/Applications/$APP"
cp -R "$APP" "$HOME/Applications/"
rm -rf "$APP"
touch "$HOME/Applications/$APP"
echo "installed $HOME/Applications/$APP"
