#!/usr/bin/python3
# -*- coding: utf-8 -*-

import sys
import subprocess
import configparser

config = configparser.ConfigParser()
config.read('/etc/pve-usb-automount/main.conf')

MAX_FILES = config.get("MAIN", "MAX_FILES", fallback=3)

dev = sys.argv[1]
devs = dev.split("/")
devname = devs[len(devs)-1]

mountpoint = sys.argv[2]
mountnames = mountpoint.split("/")
mountname = mountnames[len(mountnames)-1]

subprocess.Popen("pvesm add dir 'usb-%s' -path '%s' -maxfiles %s -content vztmpl,iso,backup -is_mountpoint 1" % (devname, mountpoint, MAX_FILES), stdout=subprocess.PIPE, shell=True)
