//go:build darwin && arm64

package main

import _ "embed"

//go:embed desktop_native/bin/mac-arm64
var screenNative []byte
