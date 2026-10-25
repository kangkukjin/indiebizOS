package main

import (
	"strings"
	"testing"
)

func TestResidentLoginTaskMatchesEffectiveConfiguration(t *testing.T) {
	exe := `C:\Users\한글\indiebiz-helper.exe`
	raw := `<Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task"><Triggers><LogonTrigger><Enabled>true</Enabled><UserId>S-1-fixture</UserId></LogonTrigger></Triggers><Principals><Principal id="Author"><UserId>S-1-fixture</UserId><LogonType>InteractiveToken</LogonType></Principal></Principals><Settings><Enabled>true</Enabled></Settings><Actions Context="Author"><Exec><Command>"` + exe + `"</Command></Exec></Actions></Task>`
	if !residentLoginTaskMatches(raw, exe, "S-1-fixture", `PC\user`) {
		t.Fatal("identical user login task should not require schtasks /Create")
	}
	if !residentLoginTaskMatches(`<?xml version="1.0" encoding="UTF-16"?>`+raw, exe, "S-1-fixture", `PC\user`) {
		t.Fatal("schtasks declaration must not cause redundant task registration")
	}
	for _, change := range [][2]string{
		{`S-1-fixture`, `S-1-other`},
		{`InteractiveToken`, `Password`},
		{`<Settings><Enabled>true`, `<Settings><Enabled>false`},
		{`<LogonTrigger><Enabled>true`, `<LogonTrigger><Enabled>false`},
		{`</Command>`, `</Command><Arguments>--other</Arguments>`},
		{`Context="Author"`, `Context="Other"`},
		{exe, `C:\different.exe`},
		{`</Actions>`, `<Exec><Command>extra.exe</Command></Exec></Actions>`},
	} {
		if residentLoginTaskMatches(strings.ReplaceAll(raw, change[0], change[1]), exe, "S-1-fixture", `PC\user`) {
			t.Fatalf("accepted different configuration: %v", change)
		}
	}
}
