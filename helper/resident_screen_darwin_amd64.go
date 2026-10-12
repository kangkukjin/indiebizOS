//go:build darwin && amd64

package main

import _ "embed"

//go:embed desktop_native/bin/mac-x86_64
var screenNative []byte
