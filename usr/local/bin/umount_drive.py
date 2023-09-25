#!/usr/bin/python3
# -*- coding: utf-8 -*-

import sys
import subprocess

mountpoint = sys.argv[1]
mountnames = mountpoint.split("/")
mountname = mountnames[len(mountnames)-1]

subprocess.Popen("pvesm remove 'usb-%s'" % (mountname), stdout=subprocess.PIPE, shell=True)