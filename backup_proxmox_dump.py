#!/usr/bin/python3
# -*- coding: utf-8 -*-

#
# (c) Rene Hadler, iteas IT Services GmbH
# rene.hadler@iteas.at
# www.iteas.at
#

import os
import sys
import re
import subprocess

if len(sys.argv) < 4 or len(sys.argv) > 5:
    print("Nicht genügend Argumente: %s <latest_backup_count> <proxmox_dump_dir> <backup_destination_dir>" % (sys.argv[0]))
    sys.exit(0)

backup_count = int(sys.argv[1])
dump_dir = sys.argv[2]
backup_dir = sys.argv[3]

# Find unique ids
id_list = []
re_id_match = re.compile(r"^vzdump\-(qemu|lxc)\-([0-9]{3})\-.*$")
for file in os.listdir(dump_dir):
    res = re_id_match.search(file)
    if res != None:
        file_id = res.group(2)
        if file_id not in id_list:
            id_list.append(file_id)

id_list = sorted(id_list)

for id in id_list:
    fp = os.popen("ls -t %s/vzdump*%s*lzo | head -n%s " % (dump_dir, id, backup_count), "r")
    files = [os.path.basename(x).strip() for x in fp.readlines()]
    for file in files:
        cmd_cp = "rsync -av %s %s" % (dump_dir + "/" + file, backup_dir + "/.")
        print(cmd_cp)
        subprocess.call(cmd_cp, shell=True)