package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestMemberScriptProtocolRegistrationAndSeparateStderr(t *testing.T) {
	m := testMember(t)
	path := filepath.Join(t.TempDir(), "value.py")
	code := "import json,sys\nx=json.load(sys.stdin)\nprint('progress',file=sys.stderr)\nprint(json.dumps({'protocol':'ibl-script/2','ok':True,'value':{'error':'business','n':x['args']['n']}}))\n"
	if err := os.WriteFile(path, []byte(code), 0600); err != nil {
		t.Fatal(err)
	}
	contract := map[string]interface{}{"version": 1, "params": map[string]interface{}{"n": "Number"}, "result": "Record", "effects": []string{"pure"}, "adapter": map[string]interface{}{"protocol": "ibl-script/2"}}
	registered := m.store.register(Command{ScriptID: "value", Path: path, CallableContract: contract})
	if registered["success"] != true {
		t.Fatal(registered)
	}
	listing := m.store.scripts()
	if len(listing["script_protocols"].([]string)) != 2 {
		t.Fatal(listing)
	}
	if m.store.script(Command{ScriptID: "value"})["error"] != "script_protocol" {
		t.Fatal("old call entered typed script")
	}
	result := m.store.script(Command{ScriptID: "value", ScriptProtocol: "ibl-script/2", Args: map[string]interface{}{"protocol": "ibl-script/2", "args": map[string]interface{}{"n": 3}}})
	if result["success"] != true {
		t.Fatal(result)
	}
	var wire map[string]interface{}
	if err := json.Unmarshal([]byte(result["stdout"].(string)), &wire); err != nil {
		t.Fatal(err, result)
	}
	if wire["value"].(map[string]interface{})["error"] != "business" || result["stderr"] != "progress\n" {
		t.Fatal(result)
	}
}
