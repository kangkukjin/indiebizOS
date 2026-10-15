package main

import (
	"fmt"
	"golang.org/x/sys/windows"
	"os"
)

func memberFileIdentity(file *os.File) (string, error) {
	var info windows.ByHandleFileInformation
	if e := windows.GetFileInformationByHandle(windows.Handle(file.Fd()), &info); e != nil {
		return "", e
	}
	return fmt.Sprintf("%d:%d:%d", info.VolumeSerialNumber, info.FileIndexHigh, info.FileIndexLow), nil
}
