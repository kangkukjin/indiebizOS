package main

import "testing"

func TestMediaInstallUsesOnlyLocalPackageManager(t *testing.T) {
	for _, test := range []struct{ os, binary, want string }{
		{"darwin", "/opt/homebrew/bin/brew", "install"}, {"windows", "winget", "install"}, {"linux", "apt-get", "apt-get"},
	} {
		cmds := mediaInstallCommands(test.os, func(s string) bool { return s == test.binary || s == "pkexec" })
		if len(cmds) == 0 || cmds[0][1] != test.want {
			t.Fatalf("%s: %v", test.os, cmds)
		}
	}
	if cmds := mediaInstallCommands("linux", func(string) bool { return false }); len(cmds) != 0 {
		t.Fatal(cmds)
	}
}
