CLT := /Library/Developer/CommandLineTools
SWIFTC := $(CLT)/usr/bin/swiftc
SDK ?= $(CLT)/SDKs/MacOSX15.5.sdk
BUILD := $(CURDIR)/build
APP := $(BUILD)/VepolDesktop.app
BACKEND := $(abspath $(CURDIR)/..)

.PHONY: all bundle
all: bundle

ICON := $(CURDIR)/icon/Vepol.icns

bundle: VepolDesktop.swift Info.plist $(ICON)
	@mkdir -p "$(APP)/Contents/MacOS" "$(APP)/Contents/Resources" "$(BUILD)/module-cache"
	DEVELOPER_DIR="$(CLT)" "$(SWIFTC)" -parse-as-library -swift-version 5 -sdk "$(SDK)" -target arm64-apple-macosx13.0 -module-cache-path "$(BUILD)/module-cache" -framework AppKit -framework WebKit -framework Security -framework UserNotifications VepolDesktop.swift -o "$(APP)/Contents/MacOS/VepolDesktop"
	cp Info.plist "$(APP)/Contents/Info.plist"
	cp "$(ICON)" "$(APP)/Contents/Resources/Vepol.icns"
	@printf '%s\n' "$(BACKEND)" > "$(APP)/Contents/Resources/backend-path.txt"
	/usr/bin/plutil -lint "$(APP)/Contents/Info.plist"
	/usr/bin/codesign --force --sign - "$(APP)"
	/usr/bin/codesign --verify --strict "$(APP)"
	@printf 'Built %s\n' "$(APP)"
