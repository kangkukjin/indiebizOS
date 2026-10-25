package main

import (
	"encoding/xml"
	"fmt"
	"io"
	"strings"
)

// A working login task need not be recreated on every installer launch.
// Compare its effective action and owner before trusting it; unrelated tasks,
// disabled tasks, extra actions and arguments must still go through setup.
func residentLoginTaskMatches(raw, exe, sid, username string) bool {
	var task struct {
		XMLName    xml.Name `xml:"Task"`
		Principals []struct {
			ID    string `xml:"id,attr"`
			User  string `xml:"UserId"`
			Logon string `xml:"LogonType"`
		} `xml:"Principals>Principal"`
		Enabled  string `xml:"Settings>Enabled"`
		Triggers []struct {
			Enabled string `xml:"Enabled"`
			User    string `xml:"UserId"`
		} `xml:"Triggers>LogonTrigger"`
		Actions struct {
			Context string `xml:"Context,attr"`
			Entries []struct {
				XMLName   xml.Name
				Command   string `xml:"Command"`
				Arguments string `xml:"Arguments"`
			} `xml:",any"`
		} `xml:"Actions"`
	}
	owner := func(value string) bool {
		return (sid != "" && strings.EqualFold(value, sid)) || (username != "" && strings.EqualFold(value, username))
	}
	decoder := xml.NewDecoder(strings.NewReader(raw))
	// residentWindowsOutput already decoded the bytes. schtasks preserves its
	// UTF-16 declaration even when a pipe has converted the document to UTF-8.
	decoder.CharsetReader = func(charset string, input io.Reader) (io.Reader, error) {
		if strings.EqualFold(charset, "UTF-16") || strings.EqualFold(charset, "UTF-16LE") {
			return input, nil
		}
		return nil, fmt.Errorf("unsupported task XML encoding: %s", charset)
	}
	if decoder.Decode(&task) != nil || len(task.Principals) != 1 || len(task.Actions.Entries) != 1 || strings.EqualFold(task.Enabled, "false") {
		return false
	}
	principal := task.Principals[0]
	if !owner(principal.User) || principal.Logon != "InteractiveToken" || task.Actions.Context != principal.ID {
		return false
	}
	action := task.Actions.Entries[0]
	if action.XMLName.Local != "Exec" || strings.TrimSpace(action.Arguments) != "" || !strings.EqualFold(strings.Trim(strings.TrimSpace(action.Command), `"`), exe) {
		return false
	}
	for _, trigger := range task.Triggers {
		if !strings.EqualFold(trigger.Enabled, "false") && (trigger.User == "" || owner(trigger.User)) {
			return true
		}
	}
	return false
}
