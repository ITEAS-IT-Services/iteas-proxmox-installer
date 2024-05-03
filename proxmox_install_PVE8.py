#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# (c) Rene Hadler, Mario Loderer, iteas IT Services GmbH
# support@iteas.at
# www.iteas.at
#

import sys
import time
import socket
import subprocess
import requests
import json


# Global variables
VERSION = "1.2.7"
TITLE = "iteas Proxmox Installer " + VERSION
CHECK_INTERNET_IP = "77.235.68.35"
VM_TEMPLATE_CIFS_SHARE = "//10.255.18.3/proxmox-install"
VM_TEMPLATE_CIFS_USER = "localbackup02"
SMB_ADMIN_PASSWD = "backmode123"


try:
    CONSOLE_ROWS, CONSOLE_COLS = subprocess.check_output(['stty', 'size']).split()
except:
    CONSOLE_ROWS = 40
    CONSOLE_COLS = 100

GUI_WIN_WIDTH = 100 if int(CONSOLE_COLS) > 110 else (int(CONSOLE_COLS) - 10)

class Logger:
    def __init__(self):
        self.f = fr = open("proxmox_install.log", "w+")

    def log(self, text):
        self.f.write(text)

    def close(self):
        self.f.close()

logger = Logger()

# Befehle ausführen
def run_cmd(command, argShell=False):
    try:
        return subprocess.call(command.split(" ") if argShell == False else command, shell=argShell)
    except:
        e = sys.exc_info()[0]
        retval = gui_yesno_box("Fehler", "Command <%s> was not successful, Error message: %s -- Cancel installation?" % (command, e))
        if retval[0] == 0:
            exit(1)

def apt_install(pkgs, argShell=False, force=False):
    command = "apt install -y %s %s" % (pkgs, "--force-yes" if force else "")
    try:
        print(command)
        ret = subprocess.call(command.split(" ") if argShell == False else command, shell=argShell)
        if ret != 0:
            retval = gui_yesno_box("APT-Fehler", 'Command <%s> was not successful, Return value was not 0, Error message: \n--\n%s \n--\nCancel installation?' % (command, ret))
            if retval[0] == 0:
                exit(1)
    except SystemExit:
        exit(1)
    except:
        e = sys.exc_info()[0]
        retval = gui_yesno_box("Fehler", "Command <%s> was not successful, Error message: %s -- Cancel installation?" % (command, e))
        if retval[0] == 0:
            exit(1)

def run_cmd_output(command, argShell=False):
    p = subprocess.Popen(command.split(" "), stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=argShell)
    ret = p.wait()
    return (ret, p.stdout.read().decode('UTF-8'), p.stderr.read().decode('UTF-8'))

def run_cmd_stdout(command, argShell=False):
    p = subprocess.Popen(command, stdout=subprocess.PIPE, shell=argShell)
    ret = p.wait()
    return (ret, p.stdout.read().decode('UTF-8'))

def run_cmd_stderr(command, argShell=False):
    p = subprocess.Popen(command, stderr=subprocess.PIPE, shell=argShell)
    ret = p.wait()
    return (ret, p.stderr.read().decode('UTF-8'))

def run_cmd_stdin(command, argShell=False):
    p = subprocess.Popen(command, stdin=subprocess.PIPE, shell=argShell)
    return p

# Oberflächen / GUI
def gui_message_box(title, text):
    return run_cmd_stderr(["whiptail", "--backtitle", TITLE, "--msgbox", text, "--title", title, "20", str(GUI_WIN_WIDTH)])

def gui_text_box(file):
    return run_cmd_stderr(["whiptail", "--backtitle", TITLE, "--textbox", file, "20", str(GUI_WIN_WIDTH)])

def gui_input_box(title, text, default=""):
    return run_cmd_stderr(["whiptail", "--backtitle", TITLE, "--inputbox", text, "20", str(GUI_WIN_WIDTH), default, "--title", title])

def gui_yesno_box(title, text):
    return run_cmd_stderr(["whiptail", "--backtitle", TITLE, "--yesno", text, "--title", title, "20", str(GUI_WIN_WIDTH)])

def gui_password_box(title, text):
    return run_cmd_stderr(["whiptail", "--backtitle", TITLE, "--passwordbox", text.encode('UTF-8'), "8", str(GUI_WIN_WIDTH), "--title", title.encode('UTF-8')])

def gui_menu_box(title, text, menu):
    return run_cmd_stderr(["whiptail", "--backtitle", TITLE, "--menu", text, "--title", title, "28", str(GUI_WIN_WIDTH), "22"] + menu)

def gui_checklist_box(title, text, checklist):
    ret = run_cmd_stderr(["whiptail", "--backtitle", TITLE, "--checklist", text, "--title", title, "24", str(GUI_WIN_WIDTH), "14"] + checklist)
    return (ret[0], [] if ret[1] == "" else [x.replace('"', "") for x in ret[1].split(" ")])

def gui_radiolist_box(title, text, radiolist):
    return run_cmd_stderr(["whiptail", "--backtitle", TITLE, "--radiolist", text, "--title", title, "24", str(GUI_WIN_WIDTH), "14"] + radiolist)

class gui_progress_box():
    def __init__(self, text, progress):
        self.p = run_cmd_stdin(["whiptail", "--backtitle", TITLE, "--gauge", text, "6", "50", str(progress)])

    def update(self, prog):
        upd = "%s\n" % prog
        self.p.stdin.write(upd.encode('utf-8'))
        self.p.stdin.flush()

    def finish(self):
        self.p.stdin.close()

def gui_password_verify_box(title, text, text2):
    password = ""
    while password == "":
        retval = gui_password_box(title, text)
        if retval[1] == "":
            continue

        retval2 = gui_password_box(title, text2)
        if retval2[1] == "":
            continue

        if retval[1] == retval2[1]:
            password = retval[1]
        else:
            gui_message_box(title, "Error in password entry, the passwords do not match!")

    return password

# Sonstige Funktionen
def check_internet():
    try:
        s = socket.create_connection((CHECK_INTERNET_IP, 80), 5)
        return True
    except:
        return False

def check_filesystem():
    try:
        zfsc = run_cmd_output('zfs list')
        if zfsc[0] == 1 or zfsc[2].find('no datasets') != -1:
            return 'standard'
        else:
            return 'zfs'
    except:
        return 'standard'

def check_systemip(show_prefix = True):
    zfsc = run_cmd_stdout("ip addr show vmbr0 | grep 'inet' | grep -v 'inet6' | cut -d' ' -f6", argShell=True)
    if show_prefix == True:
        return zfsc[1].strip()
    else:
        return zfsc[1].strip().split("/")[0]

def check_systemipnet():
    try:
        zfsc = check_systemip()
        if zfsc == '':
            return ''
        else:
            # Nicht immer true
            ipf = zfsc.split(".")
            return "%s.%s.%s.0/%s" % (ipf[0], ipf[1], ipf[2], ipf[3].split("/")[1])
    except:
        return ''

def file_replace_line(file, findstr, replstr, encoding='utf-8'):
    try:
        fp = open(file, "r+", encoding=encoding)
        buf = ""
        for line in fp.readlines():
            if line.find(findstr) != -1:
                line = replstr + "\n"

            buf += line

        fp.close()
        fr = open(file, "w+", encoding=encoding)
        fr.write(buf)
        fr.close()
    except FileNotFoundError:
        e = sys.exc_info()[0]
        retval = gui_yesno_box("Error", "File <%s> not found, error message: %s -- Cancel installation?" % (file, e))
        if retval[0] == 0:
            exit(1)

def file_create(file, str):
    fr = open(file, "w+")
    fr.write(str + "\n")
    fr.close()

def file_append(file, str):
    fr = open(file, "a")
    fr.write(str + "\n")
    fr.close()

# Installer Start
class Installer():
    def __init__(self):
        self.internet = False
        self.fqdn = socket.getfqdn()
        try:
            self.domain = self.fqdn.split(".")[1] + "." + self.fqdn.split(".")[2]
            self.hostname = socket.gethostname()
        except:
            gui_message_box("Installer", "FQDN is not set, Installation will be aborted!")
            exit(1)

        self.machine_vendor = "other"
        self.machine_type = "virt"
        self.environment = "stable"
        self.monitoring = "checkmk"
        self.license = ""
        self.filesystem = ""
        self.vm_import = []
        self.lxc_import = []
        self.storage_import = ""
        self.share_clients = []
        self.proxy = False
        self.desktop = "kein"
        self.webmin = "no"
        self.puppet = "kein"
        self.ipmi_config = False
        self.ipmi_ip = ""
        self.ipmi_netmask = ""
        self.ipmi_gateway = ""
        self.ipmi_dns = ""
        self.ipmi_user = ""
        self.ipmi_pass = ""

        # Installer Variablen
        self.MACHINE_VENDORS = {"hp": "Hewlett Packard", "tk": "Thomas Krenn", "other": "Andere"}
        self.MACHINE_TYPES = {"virt": "Virtualization", "backup": "Backup"}
        self.ENVIRONMENTS = {"stable": "Stable Proxmox Enterprise Updates", "test": "Proxmox Nosubscription Updates", "noupdate": "no Proxmox Updates"}
        self.MONITORINGS = {"none": "Keine", "checkmk": "CheckMK Agent"}
        self.FILESYSTEMS = {"standard": "Default (ext3/4, reiserfs, xfs)", "zfs": "ZFS"}
        self.DESKTOPS = {
            "kein": "Nein",
            "plasma": "KDE5-Plasma",
            "plasma-light": "KDE5-Plasma Light",
            "plasma-light-win": "KDE5-Plasma Light Windows Workstation",
            }
        self.WEBMIN = {"no": "nein", "webmin_installed": "Webmin wird installiert"}


        self.VM_IMPORTS = {
            "220": {"name": "Windows 11 Pro", "template": True},
            "225": {"name": "Windows 10 Pro", "template": True},
            "169": {"name": "Windows Server 2022 Englisch", "template": True},
            "148": {"name": "Windows Server 2019 Englisch", "template": True},
            "222": {"name": "Windows Server 2019 Deutsch", "template": True},
            "127": {"name": "Rocky9 Standard", "template": True},
            "170": {"name": "Ubuntu Server Standard 22.04", "template": True}
            
        }
        self.LXC_IMPORTS = {
            "143": {"name": "ITEAS CT Template Ubuntu 22.04 priv", "template": True },
            "168": {"name": "ITEAS CT Template Ubuntu 22.04 unpriv", "template": True },
            "145": {"name": "BackupPC", "template": True },
            "123": {"name": "APP-Web-Template", "template": True },
            #"102": {"name": "Samba Backupassist mit ADS Anbindung", "template": True },
            #"121": {"name": "Samba Backupassist ohne ADS Anbindung", "template": True },
        }
        self.PUPPETS = {
            "kein": "Nein",
            "generic": "Generische Installation",
            "proxmox-desktop": "Proxmox Desktop"
        }

    def start(self):
        gui_message_box("Installer", "Welcome to ITEAS Proxmox Enterprise Installer!")
        self.internet = check_internet()
        self.filesystem = check_filesystem()
        if check_systemipnet() != '':
            self.share_clients.append(check_systemipnet())
        self.step1()

    def step1(self):
        step1_val = gui_menu_box("Schritt 1", "Check or configure the corresponding values and then go to 'Next'.",
                                    ["Internet", "JA" if self.internet == True else "NEIN",
                                     "Hostname", self.hostname,
                                     "Domain", self.domain,
                                     "Filesystem", self.FILESYSTEMS[self.filesystem],
                                     " ", " ",
                                     "Machinemanufacturer", self.MACHINE_VENDORS[self.machine_vendor],
                                     "Machinetype", self.MACHINE_TYPES[self.machine_type],
                                     "IPMI-Configuration", "Ja" if self.ipmi_config == True else "Nein",
                                     "Proxmox-Environment", self.ENVIRONMENTS[self.environment],
                                     "Proxmox-License", "Keine" if self.license == "" else self.license,
                                     "VM-Template-Import", ",".join([self.VM_IMPORTS[x]["name"] for x in self.vm_import]) if len(self.vm_import) > 0 else "Keine",
                                     "LXC-Template-Import", ",".join([self.LXC_IMPORTS[x]["name"] for x in self.lxc_import]) if len(self.lxc_import) > 0 else "Keine",
                                     "Import-Storage", "Keine" if self.storage_import == "" else self.storage_import,
                                     "Share-Clients-SMB", ",".join([x for x in self.share_clients]) if len(self.share_clients) > 0 else "Alle",
                                     "apt-Proxy", "Nein" if self.proxy == False else "Ja",
                                     "Desktop", self.DESKTOPS[self.desktop],
                                     "Webmin Management", self.WEBMIN[self.webmin],
                                     "Monitoring-Agent", self.MONITORINGS[self.monitoring],
                                     "Puppet", self.PUPPETS[self.puppet],
                                     " ", " ",
                                     "Next", "Continue installation"])

        # Abbrechen
        if step1_val[0] == 1 or step1_val[0] == 255:
            exit(0)

        # Eintrag wurde gewählt
        if step1_val[1] == "Machinemanufacturer":
            self.step1_machine_vendor()

        elif step1_val[1] == "Machinetype":
            self.step1_machine_type()

        elif step1_val[1] == "Proxmox-Environment":
            self.step1_environment()

        elif step1_val[1] == "Monitoring-Agent":
            self.step1_monitoring()

        elif step1_val[1] == "Proxmox-License":
            self.step1_license()

        elif step1_val[1] == "apt-Proxy":
            self.step1_aptproxy()

        elif step1_val[1] == "Desktop":
            self.step1_desktop()

        elif step1_val[1] == "Webmin Management":
            self.step1_webmin()

        elif step1_val[1] == "VM-Template-Import":
            self.step1_vmtemplateimport()

        elif step1_val[1] == "LXC-Template-Import":
            self.step1_lxctemplateimport()

        elif step1_val[1] == "Internet":
            check_internet()
            self.step1()

        elif step1_val[1] == "Share-Clients-SMB":
            self.step1_shareclients()

        elif step1_val[1] == "Next":
            self.step2()

        elif step1_val[1] == "Puppet":
            self.step1_puppet()

        elif step1_val[1] == "IPMI-Configuration":
            self.step1_ipmi_main()

        elif step1_val[1] == "Import-Storage":
            self.step1_import_storage()

        else:
            self.step1()

    def step1_ipmi_main(self):
        step1_val = gui_menu_box("IPMI-Configuration", "Check or configure IPMI 'Next'.",
                                 ["IPMI-Configuration ", "Ja" if self.ipmi_config == True else "Nein",
                                  " ", " ",
                                  "IP-Adresse", self.ipmi_ip,
                                  "IP-Subnet", self.ipmi_netmask,
                                  "Gateway", self.ipmi_gateway,
                                  "DNS", self.ipmi_dns,
                                  " ", " ",
                                  "Username", self.ipmi_user,
                                  "Password", self.ipmi_pass[0:3] + (len(self.ipmi_pass)-3)*"*",
                                  " ", " ",
                                  "back", "Mainmenu"])

        # Abbrechen
        if step1_val[0] == 1 or step1_val[0] == 255:
            self.step1()

        # Eintrag wurde gewählt
        if step1_val[1] == "IPMI-Configuration ":
            self.step1_ipmi_config()

        elif step1_val[1] == "IP-Adresse":
            self.step1_ipmi_ip()

        elif step1_val[1] == "IP-Subnet":
            self.step1_ipmi_netmask()

        elif step1_val[1] == "Gateway":
            self.step1_ipmi_gateway()

        elif step1_val[1] == "DNS":
            self.step1_ipmi_dns()

        elif step1_val[1] == "Username":
            self.step1_ipmi_user()

        elif step1_val[1] == "Password":
            self.step1_ipmi_pass()

        elif step1_val[1] == "back":
            self.step1()

        else:
            self.step1_ipmi_main()

    def step1_ipmi_config(self):
        retval = gui_yesno_box("IPMI", "Would you like to configure IPMI?")
        if retval[0] == 0:
            self.ipmi_config = True
        elif retval[0] == 1:
            self.ipmi_config = False

        # Abbrechen
        if retval[0] == 255:
            self.step1_ipmi_main()
            return

        self.step1_ipmi_main()

    def step1_ipmi_ip(self):
        retval = gui_input_box("IPMI IP-address", "Enter IP-address", self.ipmi_ip)
        # Abbrechen
        if retval[0] == 1 or retval[0] == 255:
            self.step1_ipmi_main()
            return

        self.ipmi_ip = retval[1]
        self.step1_ipmi_main()

    def step1_ipmi_netmask(self):
        retval = gui_input_box("IPMI IP-Subnet", "Enter IP-Subnet", self.ipmi_netmask)
        # Abbrechen
        if retval[0] == 1 or retval[0] == 255:
            self.step1_ipmi_main()
            return

        self.ipmi_netmask = retval[1]
        self.step1_ipmi_main()

    def step1_ipmi_gateway(self):
        retval = gui_input_box("IPMI Gateway", "Enter Gateway", self.ipmi_gateway)
        # Abbrechen
        if retval[0] == 1 or retval[0] == 255:
            self.step1_ipmi_main()
            return

        self.ipmi_gateway = retval[1]
        self.step1_ipmi_main()

    def step1_ipmi_dns(self):
        retval = gui_input_box("IPMI DNS", "Enter DNS", self.ipmi_dns)
        # Abbrechen
        if retval[0] == 1 or retval[0] == 255:
            self.step1_ipmi_main()
            return

        self.ipmi_dns = retval[1]
        self.step1_ipmi_main()

    def step1_ipmi_user(self):
        retval = gui_input_box("IPMI Username", "Enter Username", self.ipmi_user)
        # Abbrechen
        if retval[0] == 1 or retval[0] == 255:
            self.step1_ipmi_main()
            return

        self.ipmi_user = retval[1]
        self.step1_ipmi_main()

    def step1_ipmi_pass(self):
        retval = gui_password_box("IPMI Password", "Enter password")
        # Abbrechen
        if retval[0] == 1 or retval[0] == 255:
            self.step1_ipmi_main()
            return

        self.ipmi_pass = retval[1]
        self.step1_ipmi_main()

    def step1_machine_vendor(self):
        list = []
        for key, val in self.MACHINE_VENDORS.items():
            list += [key, val, "ON" if self.machine_vendor == key else "OFF"]

        retval = gui_radiolist_box("Schritt 1: Machinemanufacturer", "Select the appropriate machinemanufacturer", list)
        # Abbrechen
        if retval[0] == 1 or retval[0] == 255:
            self.step1()
            return

        self.machine_vendor = retval[1]
        self.step1()

    def step1_machine_type(self):
        list = []
        for key, val in self.MACHINE_TYPES.items():
            list += [key, val, "ON" if self.machine_type == key else "OFF"]

        retval = gui_radiolist_box("Schritt 1: Machinetype", "Select the appropriate machinetype", list)
        # Abbrechen
        if retval[0] == 1 or retval[0] == 255:
            self.step1()
            return

        self.machine_type = retval[1]
        self.step1()

    def step1_environment(self):
        list = []
        for key, val in self.ENVIRONMENTS.items():
            list += [key, val, "ON" if self.environment == key else "OFF"]

        retval = gui_radiolist_box("Schritt 1: Proxmox-Environment", "Choose the Proxmox-Environment", list)
        # Abbrechen
        if retval[0] == 1 or retval[0] == 255:
            self.step1()
            return

        self.environment = retval[1]
        self.step1()

    def step1_monitoring(self):
        list = []
        for key, val in self.MONITORINGS.items():
            list += [key, val, "ON" if self.monitoring == key else "OFF"]

        retval = gui_radiolist_box("Schritt 1: Monitoring-Agent", "Choose the Monitoring-Agenten", list)
        # Abbrechen
        if retval[0] == 1 or retval[0] == 255:
            self.step1()
            return

        self.monitoring = retval[1]
        self.step1()

    def step1_license(self):
        retval = gui_input_box("Schritt 1: Proxmox-License", "Enter the Proxmox Subscription Key", self.license)
        # Abbrechen
        if retval[0] == 1 or retval[0] == 255:
            self.step1()
            return

        self.license = retval[1]
        self.step1()

    def step1_aptproxy(self):
        retval = gui_yesno_box("Installer", "Do you like to use the iteas apt proxy?")
        if retval[0] == 0:
            self.proxy = True
        elif retval[0] == 1:
            self.proxy = False

        # Abbrechen
        if retval[0] == 255:
            self.step1()
            return

        self.step1()

    def step1_desktop(self):
        list = []
        for key, val in self.DESKTOPS.items():
            list += [key, val, "ON" if self.desktop == key else "OFF"]

        retval = gui_radiolist_box("Schritt 1: Proxmox-Desktop", "Select one Desktop", list)
        # Abbrechen
        if retval[0] == 1 or retval[0] == 255:
            self.step1()
            return

        self.desktop = retval[1]
        self.step1()

    def step1_webmin(self):
        list = []
        for key, val in self.WEBMIN.items():
            list += [key, val, "ON" if self.webmin == key else "OFF"]

        retval = gui_radiolist_box("Schritt 1: Webmin Management", "Activate the Webmin installation", list)
        # Abbrechen
        if retval[0] == 1 or retval[0] == 255:
            self.step1()
            return

        self.webmin = retval[1]
        self.step1()

    def step1_vmtemplateimport(self):
        list = []
        for key, val in self.VM_IMPORTS.items():
            list += [key, val["name"], "ON" if key in self.vm_import else "OFF"]

        retval = gui_checklist_box("Schritt 1: VM-Template-Import", "Select the VMs you want to imported", list)
        # Abbrechen
        if retval[0] == 1 or retval[0] == 255:
            self.step1()
            return

        self.vm_import = []
        for val in retval[1]:
            self.vm_import += [val]

        self.step1()

    def step1_lxctemplateimport(self):
        list = []
        for key, val in self.LXC_IMPORTS.items():
            list += [key, val["name"], "ON" if key in self.lxc_import else "OFF"]

        retval = gui_checklist_box("Schritt 1: LXC-Template-Import", "Select the LXC containers you want to import", list)
        # Abbrechen
        if retval[0] == 1 or retval[0] == 255:
            self.step1()
            return

        self.lxc_import = []
        for val in retval[1]:
            self.lxc_import += [val]

        self.step1()

    def step1_shareclients(self):
        retval = gui_input_box("Schritt 1: Share-Clients", "Specify the clients/networks that should have access to the shares on the Proxmox host. Multiple entries must be separated by spaces.", " ".join(self.share_clients))
        # Abbrechen
        if retval[0] == 1 or retval[0] == 255:
            self.step1()
            return

        self.share_clients = retval[1].split(" ")
        self.step1()

    def step1_puppet(self):
        list = []
        for key, val in self.PUPPETS.items():
            list += [key, val, "ON" if self.puppet == key else "OFF"]

        retval = gui_radiolist_box("Schritt 1: Puppet", "Choose a Puppet installation type", list)
        # Abbrechen
        if retval[0] == 1 or retval[0] == 255:
            self.step1()
            return

        self.puppet = retval[1]
        self.step1()

    def step1_import_storage(self):
        list = []
        jstorages = json.loads(run_cmd_stdout("pvesh get /storage --output-format json", argShell=True)[1])
        for storage in jstorages:
            list += [storage["storage"], storage["content"], "ON" if self.storage_import == storage["storage"] else "OFF"]

        retval = gui_radiolist_box("Schritt 1: Import-Storage", "Choose a storage for the template import", list)
        # Abbrechen
        if retval[0] == 1 or retval[0] == 255:
            self.step1()
            return

        self.storage_import = retval[1]
        self.step1()

    def step2(self):

        if self.environment == "stable" and self.license == "":
            gui_message_box("Installer", "You must specify a license when Enterprise Updates are selected!")
            self.step1()
            return

        if self.internet == False:
            gui_message_box("Installer", "There must be an internet connection to continue!")
            self.step1()
            return

        if (len(self.vm_import) > 0 or len(self.lxc_import) > 0) and self.storage_import == "":
            gui_message_box("Installer", "You must specify an import storage!")
            self.step1()
            return

        # Set locales
        file_replace_line("/etc/locale.gen", "# de_AT.UTF-8 UTF-8", "de_AT.UTF-8 UTF-8")
        file_replace_line("/etc/locale.gen", "# de_DE.UTF-8 UTF-8", "de_DE.UTF-8 UTF-8")
        run_cmd('locale-gen', argShell=True)

        ############ generic configuration
        if self.license != "":
            retval = run_cmd_output('pvesubscription set ' + self.license)
            if retval[0] == 255:
                gui_message_box("Proxmox License installation", "The license could not be installed, please check your license number. Error: " + retval[2])
                self.step1()
                return

            time.sleep(30)

            # Wait maximum for 5 minutes for registration
            maxwait = 300
            curwait = 0
            lictest = run_cmd_stdout('pvesubscription get', argShell=True)
            while lictest[1].find('status: Active') == -1 and curwait < maxwait:
                print("Activation of the Enterprise-Repos...Please wait... This process can take up to 5 minutes." + str(curwait))
                time.sleep(10)
                lictest = run_cmd_stdout('pvesubscription get', argShell=True)
                curwait += 10

            # Wait maximum for 5 minutes for enterprise repo access
            curwait = 0
            httpuser = run_cmd_stdout("pvesubscription get | grep 'key:.*' | cut -f2 -d:", argShell=True)[1].strip()
            httppass = run_cmd_stdout("pvesubscription get | grep 'serverid:.*' | cut -f2 -d:", argShell=True)[1].strip()

            repotest = requests.get('https://enterprise.proxmox.com/debian/pve', auth=(httpuser, httppass))
            while repotest.status_code != requests.codes.ok and curwait < maxwait:
                print("Activation of the Enterprise-Repos...Please wait... This process can take up to 5 minutes." + str(curwait))
                time.sleep(10)
                repotest = requests.get('https://enterprise.proxmox.com/debian/pve', auth=(httpuser, httppass))
                curwait += 10

        # Activate Proxmox Nosubscription Sources
        if self.environment == "test":
            file_create("/etc/apt/sources.list.d/pve-enterprise.list", "# deb https://enterprise.proxmox.com/debian/pve bookworm pve-enterprise")
            file_create("/etc/apt/sources.list.d/ceph.list", "# deb https://enterprise.proxmox.com/debian/ceph-quincy bookworm enterprise")
            file_create("/etc/apt/sources.list.d/pve-no-subscription.list", "deb http://download.proxmox.com/debian/pve bookworm pve-no-subscription")
            file_create("/etc/apt/sources.list.d/ceph-no-subscription.list", "deb http://download.proxmox.com/debian/ceph-quincy bookworm no-subscription")
        elif self.environment == "noupdate":
            file_create("/etc/apt/sources.list.d/pve-enterprise.list", "# deb https://enterprise.proxmox.com/debian/pve bookworm pve-enterprise")
            file_create("/etc/apt/sources.list.d/pve-no-subscription.list", "# deb http://download.proxmox.com/debian/pve bookworm pve-no-subscription")
            file_create("/etc/apt/sources.list.d/ceph.list", "# deb https://enterprise.proxmox.com/debian/ceph-quincy bookworm enterprise")
            file_create("/etc/apt/sources.list.d/ceph-no-subscription.list", "# deb http://download.proxmox.com/debian/ceph-quincy bookworm no-subscription")
            

        # If lvm-thin convert to standard file storage if backup-machine
        if self.machine_type == "backup" and run_cmd('pvesh get /storage | grep -i local-lvm', argShell=True) == 0:
            run_cmd('pvesh delete /storage/local-lvm')
            run_cmd('lvremove /dev/pve/data -f')
            run_cmd('lvcreate -Wy -l100%FREE -ndata pve')
            run_cmd('mkfs.ext4 -m1 /dev/pve/data')
            run_cmd('mount /dev/pve/data /var/lib/vz')
            file_append("/etc/fstab", "/dev/pve/data /var/lib/vz ext4 defaults 0 2")

        # Mount Template CIFS-Share and import VMs
        #storage = "local"
        #if run_cmd('pvesh get /storage | grep -i local-lvm', argShell=True) == 0:
        #    storage = "local-lvm"
        #
        #if self.filesystem == "zfs":
        #    storage = "local-zfs"
        storage = self.storage_import

        if len(self.vm_import) > 0 or len(self.lxc_import) > 0:
            retval = gui_password_box("Samba password required", "Please enter the password for Share " + VM_TEMPLATE_CIFS_SHARE + " and Username " + VM_TEMPLATE_CIFS_USER + " enter.")
            VM_TEMPLATE_CIFS_PASS = retval[1]

            cifscnt = 1
            run_cmd('mkdir -p /mnt/proxmox-install-import', argShell=True)
            cifstest = run_cmd('mount -t cifs -o user=' + VM_TEMPLATE_CIFS_USER + ",password=" + VM_TEMPLATE_CIFS_PASS + " " + VM_TEMPLATE_CIFS_SHARE + ' /mnt/proxmox-install-import')
            while cifstest != 0 and cifscnt < 3:
                retval = gui_password_box("Passwort falsch, Samba password required", "Please enter the password for Share " + VM_TEMPLATE_CIFS_SHARE + " and Username " + VM_TEMPLATE_CIFS_USER + " enter again.")
                VM_TEMPLATE_CIFS_PASS = retval[1]
                cifstest = run_cmd('mount -t cifs -o user=' + VM_TEMPLATE_CIFS_USER + ",password=" + VM_TEMPLATE_CIFS_PASS + " " + VM_TEMPLATE_CIFS_SHARE + ' /mnt/proxmox-install-import')
                if cifstest == 0:
                    break
                cifscnt += 1

            if cifstest == 0:
                # Import selected VMs
                for vm_id in self.vm_import:
                    (ret, filename) = run_cmd_stdout("ls -t /mnt/proxmox-install-import/vzdump-qemu-%s*vma.zst | head -n1" % vm_id, argShell=True)
                    if filename != "":
                        run_cmd("qmrestore %s %s -storage %s" % (filename.strip(), vm_id, storage))
                        if self.VM_IMPORTS[vm_id]["template"] == True:
                            run_cmd("qm template %s" % vm_id)

                # Import selected LXCs
                for vm_id in self.lxc_import:
                    (ret, filename) = run_cmd_stdout("ls -t /mnt/proxmox-install-import/vzdump-lxc-%s-*.tar.zst | head -n1" % vm_id, argShell=True)
                    if filename != "":
                        run_cmd("pct restore %s %s -storage %s" % (vm_id, filename.strip(), storage))
                        if self.LXC_IMPORTS[vm_id]["template"] == True:
                            run_cmd("pct template %s" % vm_id)

                run_cmd('umount /mnt/proxmox-install-import')
            else:
                gui_message_box("Installer", "CIFS could not be mounted (password wrong?), VMs are not imported!")

            VM_TEMPLATE_CIFS_PASS = ""

        # Apt-Proxy Cache


        if self.proxy == True:
            file_create("/etc/apt/apt.conf.d/01proxy", 'Acquire::http { Proxy "http://10.69.99.10:3142"; };')

        # Installieren allgemeine Tools und Monitoring-Agent
        file_create("/etc/apt/sources.list", "deb http://ftp.at.debian.org/debian bookworm main contrib non-free non-free-firmware")
        run_cmd('echo "deb http://ftp.at.debian.org/debian bookworm-updates main contrib non-free non-free-firmware" >> /etc/apt/sources.list', argShell=True)
        run_cmd('echo "deb http://security.debian.org bookworm-security main contrib non-free non-free-firmware" >> /etc/apt/sources.list', argShell=True)

        run_cmd('gpg -k')
        
        file_create("/etc/apt/sources.list.d/iteas.list", "deb [arch=amd64 signed-by=/usr/share/keyrings/iteas-keyring.gpg] http://apt.iteas.at/iteas bookworm main")
        run_cmd('wget https://apt.iteas.at/iteas-keyring.gpg -O /usr/share/keyrings/iteas-keyring.gpg', argShell=True)
        run_cmd('apt update')
        run_cmd('apt dist-upgrade -y')
        apt_install('htop unp postfix sudo zsh tmux bwm-ng pigz sysstat nload apcupsd sl gawk ca-certificates-iteas-enterprise at lsb-release lshw intel-microcode amd64-microcode fortunes-de fortunes finger')
        run_cmd('ln -s /usr/games/sl /usr/local/bin/sl')
        run_cmd('wget https://git.styrion.net/iteas/iteas-proxmox-installer/-/raw/main/usr/local/bin/speicherpig -O /usr/local/bin/speicherpig')
        run_cmd('chmod +x /usr/local/bin/speicherpig')

        # install ifupdown2 only if "noupdate" is not selected because the default package in the Debian sources is not compatible with proxmox
        if self.environment != "noupdate":
            apt_install('ifupdown2')

        if self.monitoring == "checkmk":
            apt_install('xinetd check-mk-agent')

        # Special general settings for ZFS
        if self.filesystem == "zfs":
            file_create("/etc/modprobe.d/zfs.conf", "options zfs zfs_arc_max=10737418240")
            run_cmd('update-initramfs -u', argShell=True)

        # SUDOers
        file_append("/etc/sudoers", "#backuppc      ALL=(ALL) NOPASSWD: /usr/bin/rsync")
        file_append("/etc/sudoers", "#backuppc      ALL=(ALL) NOPASSWD: /bin/tar")

        # Monitoring Konfiguration
        if self.monitoring == "checkmk":

            # Check-MK-Agent Config
            run_cmd('wget -O /tmp/mk_smart https://git.styrion.net/iteas/check_mk-smart-plugin/raw/master/agents/smart')
            run_cmd('mv /tmp/mk_smart /usr/lib/check_mk_agent/plugins/')
            run_cmd('wget -O /tmp/mk_apcupsd https://git.styrion.net/iteas/iteas-proxmox-installer/raw/main/usr/lib/check_mk_agent/plugins/mk_apcupsd')
            run_cmd('mv /tmp/mk_apcupsd /usr/lib/check_mk_agent/plugins/')
            run_cmd('wget -O /tmp/mk_dmi_sysinfo https://git.styrion.net/iteas/iteas-proxmox-installer/raw/main/usr/lib/check_mk_agent/plugins/mk_dmi_sysinfo')
            run_cmd('mv /tmp/mk_dmi_sysinfo /usr/lib/check_mk_agent/plugins/')
            run_cmd('wget -O /tmp/mk_inventory https://git.styrion.net/iteas/iteas-proxmox-installer/raw/main/usr/lib/check_mk_agent/plugins/mk_inventory')
            run_cmd('mv /tmp/mk_inventory /usr/lib/check_mk_agent/plugins/')
            run_cmd('wget -O /tmp/mk_lmsensors https://git.styrion.net/iteas/iteas-proxmox-installer/raw/main/usr/lib/check_mk_agent/plugins/mk_lmsensors')
            run_cmd('mv /tmp/mk_lmsensors /usr/lib/check_mk_agent/plugins/')
            run_cmd('wget -O /tmp/mk_logins https://git.styrion.net/iteas/iteas-proxmox-installer/raw/main/usr/lib/check_mk_agent/plugins/mk_logins')
            run_cmd('mv /tmp/mk_logins /usr/lib/check_mk_agent/plugins/')
            run_cmd('wget -O /tmp/mk_nfsexports https://git.styrion.net/iteas/iteas-proxmox-installer/raw/main/usr/lib/check_mk_agent/plugins/mk_nfsexports')
            run_cmd('mv /tmp/mk_nfsexports /usr/lib/check_mk_agent/plugins/')
            run_cmd('wget -O /tmp/mk_netstat https://git.styrion.net/iteas/iteas-proxmox-installer/raw/main/usr/lib/check_mk_agent/plugins/mk_netstat')
            run_cmd('mv /tmp/mk_netstat /usr/lib/check_mk_agent/plugins/')
            run_cmd('chmod +x /usr/lib/check_mk_agent/plugins/mk_*', argShell=True)

        # APC
        run_cmd('wget -O /etc/apcupsd/apcupsd.conf https://git.styrion.net/iteas/iteas-proxmox-installer/raw/main/etc/apcupsd.conf')
        file_replace_line("/etc/default/apcupsd", "ISCONFIGURED", "ISCONFIGURED=yes")
        run_cmd('systemctl enable apcupsd.service')

        # Nano
        run_cmd('wget -O /tmp/nano.tar https://git.styrion.net/iteas/iteas-proxmox-installer/raw/main/config/nano.tar')
        run_cmd('tar -xf /tmp/nano.tar -C /root')
        run_cmd('rm /tmp/nano.tar')

        # ZSH
        run_cmd('wget -O /tmp/zshrc_root https://git.styrion.net/iteas/iteas-proxmox-installer/raw/main/config/zshrc_root')
        run_cmd('mv /tmp/zshrc_root /root/.zshrc')
        file_replace_line("/root/.zshrc", "domain.foo", 'export PS1="%UDomain:%u %B%F{yellow}' + self.domain + ' $PS1"', encoding='UTF8'
                                                                                                                                   '')
        run_cmd('usermod -s /bin/zsh root')


        # Postfix
        file_replace_line("/etc/postfix/main.cf", "myhostname=", "myhostname=" + self.fqdn + ".monitoring.iteas.at")
        file_replace_line("/etc/postfix/main.cf", "relayhost =", "relayhost = smtp.styrion.net")
        run_cmd('echo "smtpd_tls_cert_file=/etc/ssl/certs/ssl-cert-snakeoil.pem" >> /etc/postfix/main.cf',argShell=True)
        run_cmd('echo "smtpd_tls_key_file=/etc/ssl/private/ssl-cert-snakeoil.key" >> /etc/postfix/main.cf',argShell=True)
        run_cmd('echo "smtpd_tls_security_level=may" >> /etc/postfix/main.cf', argShell=True)
        run_cmd('echo "smtp_tls_CApath=/etc/ssl/certs" >> /etc/postfix/main.cf', argShell=True)
        run_cmd('echo "smtp_tls_security_level=may" >> /etc/postfix/main.cf', argShell=True)
        run_cmd('echo "smtp_tls_session_cache_database = btree:${data_directory}/smtp_scache" >> /etc/postfix/main.cf',argShell=True)
        run_cmd('systemctl restart postfix.service')

        # SystemD
        run_cmd('wget -O /etc/systemd/system/rc.local.shutdown.service https://git.styrion.net/iteas/iteas-proxmox-installer/raw/main/systemd/rc.local.shutdown.service')
        run_cmd('wget -O /etc/rc.local.shutdown https://git.styrion.net/iteas/iteas-proxmox-installer/raw/main/systemd/rc.local.shutdown')
        run_cmd('systemctl enable rc.local.shutdown.service')
        
        # SysCTL
        file_create("/etc/sysctl.d/iteas.conf", "fs.inotify.max_user_watches=5242880")
        file_append("/etc/sysctl.d/iteas.conf", "fs.inotify.max_user_instances=1024")

        ############ Confiuration for Backup-Server
        if self.machine_type == "backup":
            # NFS, Samba & ZFS
            apt_install('samba')

            #password = gui_password_verify_box("Samba Password", "Enter the password for the Samba user 'admin':", "Enter the password for the Samba user 'admin' again:")
            password = SMB_ADMIN_PASSWD
            run_cmd("groupadd localbackup", argShell=True)
            run_cmd("useradd localbackup -m -g localbackup -p '%s'" % password, argShell=True)
            run_cmd("(echo '%s'; echo '%s') | smbpasswd -a localbackup" % (password, password), argShell=True)
            run_cmd('wget -O /etc/samba/smb.conf https://git.styrion.net/iteas/iteas-proxmox-installer/raw/main/samba/backup_default_smb2.conf')

            backup_root = ""
            if self.filesystem == "zfs":
                run_cmd('zfs create rpool/vollsicherung')
                apt_install('zfs-zed')
                file_replace_line("/etc/samba/smb.conf", "path = /var/lib/vz/vollsicherung", "\tpath = /rpool/vollsicherung")
                backup_root = "/rpool/vollsicherung"
            else:
                run_cmd('mkdir /var/lib/vz/vollsicherung')
                backup_root = "/var/lib/vz/vollsicherung"

            run_cmd("chown -R localbackup:localbackup %s" % backup_root)

            file_replace_line("/etc/samba/smb.conf", "workgroup = kundendomain.local", "\tworkgroup = %s" % self.domain)
            if len(self.share_clients) > 0:
                file_replace_line("/etc/samba/smb.conf", "hosts allow =", "\thosts allow = %s" % " ".join(self.share_clients))

            run_cmd('systemctl enable smbd')
            run_cmd('systemctl start smbd')

            ############ Installation Webmin
        if self.webmin == "webmin_installed":
            file_create("/etc/apt/sources.list.d/webmin.list", "deb [signed-by=/usr/share/keyrings/debian-webmin-developers.gpg] https://download.webmin.com/download/newkey/repository stable contrib")
            run_cmd("gpg --no-default-keyring --keyring /usr/share/keyrings/debian-webmin-developers.gpg --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys 2D223B918916F2A2", argShell=True)
            apt_install("apt-transport-https curl git")
            run_cmd("apt update", argShell=True)
            apt_install("webmin")
            file_append("/etc/webmin/config", "lang_root=de.UTF-8")
            file_append("/etc/webmin/config", "theme_root=authentic-theme")
            file_replace_line("/etc/webmin/config", "lang=", "lang=de.UTF-8")
            file_append("/etc/webmin/miniserv.conf", "preroot_root=authentic-theme")
            run_cmd('mkdir /etc/webmin/authentic-theme')
            run_cmd('wget -O /etc/webmin/authentic-theme/favorites.json https://git.styrion.net/iteas/iteas-proxmox-installer/raw/main/webmin/favorites.json')
            run_cmd('systemctl restart webmin')


        ############ Configuration for HP
        elif self.machine_vendor == "hp":
            # HP-Tools
            file_create("/etc/apt/sources.list.d/hp.list", "deb [arch=amd64 signed-by=/usr/share/keyrings/HP_Enterprise.gpg] http://downloads.linux.hpe.com/SDR/downloads/MCP bookworm/current non-free")
            file_append("/etc/apt/sources.list.d/hp.list", "deb [arch=amd64 signed-by=/usr/share/keyrings/HP_Enterprise.gpg] http://downloads.linux.hpe.com/SDR/downloads/MCP/debian bookworm/current non-free")
            run_cmd('gpg --no-default-keyring --keyring /usr/share/keyrings/HP_Enterprise.gpg --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C208ADDE26C2B797')
            run_cmd('apt update')
            run_cmd('apt install ssacli hponcfg -y')
            run_cmd('ln -s /usr/sbin/ssacli /usr/sbin/hpacucli')

        elif self.machine_vendor == "tk":
            # IPMI Tools
            apt_install('ipmitool ipmiutil ipmicfg')

        # Configure IPMI
        if self.ipmi_config:
            # Thanks TK-Wiki: https://www.thomas-krenn.com/de/wiki/IPMI_Konfiguration_unter_Linux_mittels_ipmitool
            run_cmd('ipmitool lan set 1 ipsrc static', argShell=True)
            run_cmd('ipmitool lan set 1 ipaddr "%s"' % self.ipmi_ip, argShell=True)
            run_cmd('ipmitool lan set 1 netmask "%s"' % self.ipmi_netmask, argShell=True)
            run_cmd('ipmitool lan set 1 defgw ipaddr "%s"' % self.ipmi_gateway, argShell=True)
            run_cmd('ipmitool user set name 2 "%s"' % self.ipmi_user, argShell=True)
            run_cmd('ipmitool user set password 2 "%s"' % self.ipmi_pass, argShell=True)
            run_cmd('ipmitool channel setaccess 1 2 link=on ipmi=on callin=on privilege=4', argShell=True)
            run_cmd('ipmitool user enable 2', argShell=True)

        # Install puppet
        if self.puppet == "generic":
            run_cmd('wget -O /tmp/install_puppet.sh https://git.styrion.net/iteas/iteas-tools/raw/master/puppet/proxmox8_mit_puppet.sh && chmod +x /tmp/install_puppet.sh', argShell=True)
            run_cmd('echo "\n" | /tmp/install_puppet.sh', argShell=True)

        elif self.puppet == "proxmox-desktop":
            run_cmd('wget -O /tmp/install_puppet.sh https://git.styrion.net/iteas/iteas-tools/raw/master/puppet/proxmox8_mit_puppet.sh && chmod +x /tmp/install_puppet.sh', argShell=True)
            run_cmd('echo "\n" | /tmp/install_puppet.sh', argShell=True)



        # Desktop Configuration
        if self.desktop == "plasma-light":
            apt_install('lm-sensors curl firefox-esr firefox-esr-l10n-de virt-viewer kde-plasma-desktop qapt-deb-installer filelight khelpcenter mpv task-german-kde-desktop task-german hunspell-de-at hunspell-de-ch hyphen-de mythes-de-ch mythes-de git kate')
            run_cmd('apt remove -y konqueror juk dragonplayer timidity zutty network-manager sweeper', argShell=True)
            run_cmd('wget -O /tmp/KDE_Plasma5_pve_profile.tar.gz https://git.styrion.net/iteas/iteas-proxmox-installer/raw/main/KDE_Plasma5_pve_profile.tar.gz')
            run_cmd('rm -rf /etc/skel', argShell=True)
            run_cmd('mkdir /etc/skel', argShell=True)
            run_cmd('tar -xzf /tmp/KDE_Plasma5_pve_profile.tar.gz -C /etc/skel', argShell=True)
            run_cmd('rm /tmp/KDE_Plasma5_pve_profile.tar.gz', argShell=True)
            run_cmd('mkdir /usr/local/share/wallpapers', argShell=True)
            run_cmd('mkdir /usr/local/share/pixmaps', argShell=True)
            run_cmd('cd /usr/local/share/pixmaps', argShell=True)
            run_cmd('wget https://git.styrion.net/iteas/iteas-proxmox-installer/raw/main/graphics/proxmox%20icon.png')
            run_cmd('wget https://git.styrion.net/iteas/iteas-proxmox-installer/raw/main/graphics/proxmox_logo_white_background.png')
            run_cmd('wget https://git.styrion.net/iteas/iteas-proxmox-installer/raw/main/graphics/pve-kick.png')
            run_cmd('wget -O /usr/local/share/wallpapers/serverfarm.jpg https://git.styrion.net/iteas/iteas-proxmox-installer/raw/main/graphics/serverfarm.jpg')
            run_cmd('wget -O /usr/share/sddm/themes/breeze/theme.conf.user https://git.styrion.net/iteas/iteas-proxmox-installer/-/raw/main/config/theme.conf.user', argShell=True)
            run_cmd('useradd pveadm -c pveadm -G dialout,cdrom,video,plugdev,games,sudo -m -s /bin/zsh -U -p \'$1$CvBQaSeR$0phJus.ly543oq2fKOtT40\'', argShell=True)

        elif self.desktop == "plasma-light-win":
            apt_install('lm-sensors curl nomachine firefox-esr firefox-esr-l10n-de virt-viewer kde-plasma-desktop qapt-deb-installer filelight khelpcenter mpv task-german-kde-desktop task-german hunspell-de-at hunspell-de-ch hyphen-de mythes-de-ch mythes-de git kate')
            run_cmd('apt remove -y konqueror', argShell=True)
            run_cmd('wget -O /tmp/KDE_Plasma5_Default_Profile-Proxmox5.tar.gz https://git.styrion.net/iteas/iteas-proxmox-installer/raw/main/KDE_Plasma5_Default_Profile-Proxmox5.tar.gz')
            run_cmd('rm -rf /etc/skel', argShell=True)
            run_cmd('tar -xzf /tmp/KDE_Plasma5_Default_Profile-Proxmox5.tar.gz -C /etc', argShell=True)
            run_cmd('mv /etc/KDE_Plasma5_Default_Profile-master /etc/skel', argShell=True)
            run_cmd('rm /tmp/KDE_Plasma5_Default_Profile-Proxmox5.tar.gz', argShell=True)
            run_cmd('pveum user add user@pve', argShell=True)
            run_cmd('echo "123123\n123123" | pveum passwd user@pve', argShell=True)
            run_cmd('useradd user -c user -G dialout,cdrom,video,plugdev,games -m -s /bin/zsh -U -p \'$1$bXXXRpOf$cLs.kEex6rSD8horkJzru0\'', argShell=True)
            run_cmd('wget -O /etc/sddm.conf https://git.styrion.net/iteas/iteas-proxmox-installer/raw/main/etc/sddm.conf-user-autologon')
            run_cmd('cd /tmp && git clone https://gitlab+deploy-token-1:-9F-Ty1feEf-9sQy_if4@git.styrion.net/iteas/proxmox-workstation.git && rm -rf /home/user && cp -r proxmox-workstation /home/user && chown -R user:user /home/user', argShell=True)
            run_cmd('pvesm set local -disable', argShell=True)

        elif self.desktop == "plasma":
            apt_install('lm-sensors libsane1 curl firefox-esr firefox-esr-l10n-de virt-viewer kde-plasma-desktop qapt-deb-installer filelight khelpcenter curl task-german-kde-desktop task-german hunspell-de-at hunspell-de-ch hyphen-de mythes-de-ch mythes-de git kde-standard plasma-desktop task-german-desktop libreoffice-l10n-de speedtest-cli x2goclient filezilla mactelnet-client ksystemlog kate gtkterm sddm-theme-debian-breeze htop tree git kate dolphin-nextcloud synaptic aspell-de hunspell-de-at mpv gnupg-agent kleopatra gnome-icon-theme mlocate kdepim kdepim-addons digikam akonadi-backend-sqlite korganizer showfoto kipi-plugins kde-config-cron dolphin-plugins filelight soundkonverter kcalc partitionmanager kronometer kfind strawberry unp simplescreenrecorder avahi-utils tellico finger  master-pdf-editor-5 gnome-disk-utility bitwarden libreoffice libreoffice-kf5 libreoffice-l10n-en-gb kwin-decoration-oxygen')
            run_cmd('apt remove -y konqueror juk dragonplayer timidity zutty network-manager sweeper --purge', argShell=True)
            run_cmd('wget -O /tmp/KDE_Plasma5_pve_profile.tar.gz https://git.styrion.net/iteas/iteas-proxmox-installer/raw/main/KDE_Plasma5_pve_profile.tar.gz')
            run_cmd('rm -rf /etc/skel', argShell=True)
            run_cmd('mkdir /etc/skel', argShell=True)
            run_cmd('tar -xzf /tmp/KDE_Plasma5_pve_profile.tar.gz -C /etc/skel', argShell=True)
            run_cmd('rm /tmp/KDE_Plasma5_pve_profile.tar.gz', argShell=True)
            run_cmd('mkdir /usr/local/share/wallpapers', argShell=True)
            run_cmd('mkdir /usr/local/share/pixmaps', argShell=True)
            run_cmd('cd /usr/local/share/pixmaps', argShell=True)
            run_cmd('wget https://git.styrion.net/iteas/iteas-proxmox-installer/raw/main/graphics/proxmox%20icon.png')
            run_cmd('wget https://git.styrion.net/iteas/iteas-proxmox-installer/raw/main/graphics/proxmox_logo_white_background.png')
            run_cmd('wget https://git.styrion.net/iteas/iteas-proxmox-installer/raw/main/graphics/pve-kick.png')
            run_cmd('wget -O /usr/local/share/wallpapers/serverfarm.jpg https://git.styrion.net/iteas/iteas-proxmox-installer/raw/main/graphics/serverfarm.jpg')
            run_cmd('wget -O /usr/share/sddm/themes/breeze/theme.conf.user https://git.styrion.net/iteas/iteas-proxmox-installer/-/raw/main/config/theme.conf.user', argShell=True)
            run_cmd('useradd pveadm -c pveadm -G dialout,cdrom,video,plugdev,games,sudo -m -s /bin/zsh -U -p \'$1$CvBQaSeR$0phJus.ly543oq2fKOtT40\'', argShell=True)


        run_cmd('apt install -f; apt autoremove --purge -y;', argShell=True)
        if self.proxy == True:
            run_cmd('rm /etc/apt/apt.conf.d/01proxy')

        # Install Proxmox Config Backup Script
        B_SCRIPT = """#!/bin/bash

usage() { echo "Usage: $0 [-p <backup_path>]" 1>&2; exit 1; }

while getopts ":p:" o; do
    case "${o}" in
        p)
            p=${OPTARG}
            ;;
        *)
            usage
            ;;
    esac
done
shift $((OPTIND-1))

B_PATH="${p:-/root/}"
echo "Sichere Backup in $B_PATH"
tar -cf "$B_PATH`hostname -f`-backup.tar" /etc /root
"""
        file_create("/usr/local/bin/backup-proxmox-config", B_SCRIPT)
        run_cmd('chmod +x /usr/local/bin/backup-proxmox-config')

        sum_txt = """-------------------------------------------------------------------------------
ITEAS Proxmox Installation report

Loginmoeglichkeiten:
  https://%s:8006 -> Webinterface Virtualization
""" % check_systemip(show_prefix=False)

        if self.machine_type == "backup":
            sum_txt += "  https://%s:10000 -> Weboberflaeche Webmin (NFSfreigaben, Samba, etc.)" % check_systemip(show_prefix=False)


        sum_txt += """
  SSH ueber CMD f.e "ssh root@%s"

The following local users were created:
  root (Administrator) SSH, Virtualization, Webmin
""" % check_systemip(show_prefix=False)

        if self.machine_type == "backup":
            sum_txt += "  backup (fuer den Zugriff auf Freigaben) Samba"

        sum_txt += """

The complete installation log is available on
  /var/log/proxmox_install.log
-------------------------------------------------------------------------------
"""

        fr = open("/root/proxmox_report.txt", "w")
        fr.write(sum_txt)
        fr.close()

        gui_text_box("/root/proxmox_report.txt")

        # Installation fertig
        retval = gui_yesno_box("Installer", "The installation was completed! Do you want to restart the PC/server?")
        if retval[0] == 0:
            pbox = gui_progress_box("PC/Server is automatically restarted...", 0)
            for x in range(0, 5):
                pbox.update(x*20)
                time.sleep(1)

            pbox.finish()
            run_cmd('reboot')
        elif retval[0] == 1:
            gui_message_box("Installer", "You have to restart the PC/server manually to complete the installation!")


i = Installer()
i.start()
logger.close()
