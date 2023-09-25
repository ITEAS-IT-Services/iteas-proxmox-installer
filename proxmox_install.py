#!/usr/bin/python2
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
import re

# Globale Variablen
VERSION = "0.7.0"
TITLE = "iteas Proxmox Installer " + VERSION
CHECK_INTERNET_IP = "77.235.68.39"
VM_TEMPLATE_NFS = "10.70.99.28:/rpool/sicherung"
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
        retval = gui_yesno_box("Fehler", "Befehl <%s> war nicht erfolgreich, Fehlermeldung: %s -- Installation abbrechen?" % (command, e))
        if retval[0] == 1:
            exit(1)

def run_cmd_output(command, argShell=False):
    p = subprocess.Popen(command.split(" "), stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=argShell)
    ret = p.wait()
    return (ret, p.stdout.read(), p.stderr.read())

def run_cmd_stdout(command, argShell=False):
    p = subprocess.Popen(command, stdout=subprocess.PIPE, shell=argShell)
    ret = p.wait()
    return (ret, p.stdout.read())

def run_cmd_stderr(command, argShell=False):
    p = subprocess.Popen(command, stderr=subprocess.PIPE, shell=argShell)
    ret = p.wait()
    return (ret, p.stderr.read())

def run_cmd_stdin(command, argShell=False):
    p = subprocess.Popen(command, stdin=subprocess.PIPE, shell=argShell)
    return p

# Oberflächen / GUI
def gui_message_box(title, text):
    return run_cmd_stderr(["whiptail", "--backtitle", TITLE, "--msgbox", text, "--title", title, "8", str(GUI_WIN_WIDTH)])

def gui_text_box(file):
    return run_cmd_stderr(["whiptail", "--backtitle", TITLE, "--textbox", file, "20", str(GUI_WIN_WIDTH)])

def gui_input_box(title, text, default=""):
    return run_cmd_stderr(["whiptail", "--backtitle", TITLE, "--inputbox", text, "8", str(GUI_WIN_WIDTH), default, "--title", title])

def gui_yesno_box(title, text):
    return run_cmd_stderr(["whiptail", "--backtitle", TITLE, "--yesno", text, "--title", title, "8", str(GUI_WIN_WIDTH)])

def gui_password_box(title, text):
    return run_cmd_stderr(["whiptail", "--backtitle", TITLE, "--passwordbox", text, "8", str(GUI_WIN_WIDTH), "--title", title])

def gui_menu_box(title, text, menu):
    return run_cmd_stderr(["whiptail", "--backtitle", TITLE, "--menu", text, "--title", title, "24", str(GUI_WIN_WIDTH), "18"] + menu)

def gui_checklist_box(title, text, checklist):
    ret = run_cmd_stderr(["whiptail", "--backtitle", TITLE, "--checklist", text, "--title", title, "24", str(GUI_WIN_WIDTH), "14"] + checklist)
    return (ret[0], [] if ret[1] == "" else [x.replace('"', "") for x in ret[1].split(" ")])

def gui_radiolist_box(title, text, radiolist):
    return run_cmd_stderr(["whiptail", "--backtitle", TITLE, "--radiolist", text, "--title", title, "24", str(GUI_WIN_WIDTH), "14"] + radiolist)

class gui_progress_box():
    def __init__(self, text, progress):
        self.p = run_cmd_stdin(["whiptail", "--backtitle", TITLE, "--gauge", text, "6", "50", str(progress)])

    def update(self, prog):
        self.p.stdin.write(str(prog) + "\n")

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
            gui_message_box(title, "Fehler bei der Passworteingabe, die Passwoerter stimmen nicht ueberein!")

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
        if zfsc[2].find('no datasets') != -1:
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

def file_replace_line(file, findstr, replstr):
    fp = open(file, "r+")
    buf = ""
    for line in fp.readlines():
        if line.find(findstr) != -1:
            line = replstr + "\n"

        buf += line

    fp.close()
    fr = open(file, "w+")
    fr.write(buf)
    fr.close()

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
            gui_message_box("Installer", "FQDN ist nicht richtig gesetzt, Installation wird abgebrochen!")
            exit(1)

        self.machine_vendor = "other"
        self.machine_type = "virt"
        self.environment = "stable"
        self.monitoring = "nagios"
        self.license = ""
        self.filesystem = ""
        self.mgmt_ip = ""
        self.backuppc = False
        self.vm_import = []
        self.share_clients = []
        self.proxy = True

        # Installer Variablen
        self.MACHINE_VENDORS = {"hp": "HP", "dell": "Dell", "other": "Andere"}
        self.MACHINE_TYPES = {"virt": "Virtualisierung", "backup": "Backup"}
        self.ENVIRONMENTS = {"stable": "Stabile Proxmox Enterprise Updates", "test": "Proxmox Testing Updates", "noupdate": "Keine Proxmox Updates"}
        self.MONITORINGS = {"nagios": "Nagios NRPE", "checkmk": "CheckMK Agent"}
        self.FILESYSTEMS = {"standard": "Standard (ext3/4, reiserfs, xfs)", "zfs": "ZFS"}
        self.VM_IMPORTS = {
                            "114": {"name": "vsrv-itmgmt", "template": False},
                            "139": {"name": "Windows 7 Pro", "template": True},
                            "115": {"name": "Windows 8.1 Pro", "template": True},
                            "125": {"name": "Windows 10 Pro", "template": True},
                            "117": {"name": "Windows 2008 r2", "template": True},
                            "120": {"name": "Windows 2012 r2", "template": True},
                            "130": {"name": "Windows 2016", "template": True}
                           }

    def start(self):
        gui_message_box("Installer", "Willkommen beim iteas Proxmox Installer!")
        self.internet = check_internet()
        self.filesystem = check_filesystem()
        if check_systemipnet() != '':
            self.share_clients.append(check_systemipnet())
        self.step1()

    def step1(self):
        step1_val = gui_menu_box("Schritt 1", "Kontrollieren bzw. konfigurieren Sie die entsprechenden Werte und gehen Sie dann auf 'Weiter'.",
                                    ["Internet", "JA" if self.internet == True else "NEIN",
                                     "Hostname", self.hostname,
                                     "Domain", self.domain,
                                     "Dateisystem", self.FILESYSTEMS[self.filesystem],
                                     " ", " ",
                                     "Maschinenhersteller", self.MACHINE_VENDORS[self.machine_vendor],
                                     "Maschinentyp", self.MACHINE_TYPES[self.machine_type],
                                     "BackupPC", "Nein" if self.backuppc == False else "Ja",
                                     "Proxmox-Umgebung", self.ENVIRONMENTS[self.environment],
                                     "Proxmox-Lizenz", "Keine" if self.license == "" else self.license,
                                     "VM-Template-Import", ",".join([self.VM_IMPORTS[x]["name"] for x in self.vm_import]) if len(self.vm_import) > 0 else "Keine",
                                     "Freigabe-Clients", ",".join([x for x in self.share_clients]) if len(self.share_clients) > 0 else "Alle",
                                     "Mgmt-IP", "Keine" if self.mgmt_ip == "" else self.mgmt_ip,
                                     "apt-Proxy", "Nein" if self.proxy == False else "Ja",
                                     "Monitoring-Agent", self.MONITORINGS[self.monitoring],
                                     " ", " ",
                                     "Weiter", "Installation fortsetzen"])

        # Abbrechen
        if step1_val[0] == 1 or step1_val[0] == 255:
            exit(0)

        # Eintrag wurde gewählt
        if step1_val[1] == "Maschinenhersteller":
            self.step1_machine_vendor()

        elif step1_val[1] == "Maschinentyp":
            self.step1_machine_type()

        elif step1_val[1] == "Proxmox-Umgebung":
            self.step1_environment()

        elif step1_val[1] == "Monitoring-Agent":
            self.step1_monitoring()

        elif step1_val[1] == "Proxmox-Lizenz":
            self.step1_license()

        elif step1_val[1] == "Mgmt-IP":
            self.step1_mgmtip()

        elif step1_val[1] == "apt-Proxy":
            self.step1_aptproxy()

        elif step1_val[1] == "BackupPC":
            self.step1_backuppc()

        elif step1_val[1] == "VM-Template-Import":
            self.step1_vmtemplateimport()

        elif step1_val[1] == "Internet":
            check_internet()
            self.step1()

        elif step1_val[1] == "Freigabe-Clients":
            self.step1_shareclients()

        elif step1_val[1] == "Weiter":
            self.step2()

        else:
            self.step1()

    def step1_machine_vendor(self):
        list = []
        for key, val in self.MACHINE_VENDORS.iteritems():
            list += [key, val, "ON" if self.machine_vendor == key else "OFF"]

        retval = gui_radiolist_box("Schritt 1: Maschinenhersteller", "Waehlen sie den passenden Maschinenhersteller", list)
        # Abbrechen
        if retval[0] == 1 or retval[0] == 255:
            self.step1()
            return

        self.machine_vendor = retval[1]
        self.step1()

    def step1_machine_type(self):
        list = []
        for key, val in self.MACHINE_TYPES.iteritems():
            list += [key, val, "ON" if self.machine_type == key else "OFF"]

        retval = gui_radiolist_box("Schritt 1: Maschinentyp", "Waehlen sie den passenden Maschinentyp", list)
        # Abbrechen
        if retval[0] == 1 or retval[0] == 255:
            self.step1()
            return

        self.machine_type = retval[1]
        self.step1()

    def step1_environment(self):
        list = []
        for key, val in self.ENVIRONMENTS.iteritems():
            list += [key, val, "ON" if self.environment == key else "OFF"]

        retval = gui_radiolist_box("Schritt 1: Proxmox-Umgebung", "Waehlen sie die Proxmox-Umgebung", list)
        # Abbrechen
        if retval[0] == 1 or retval[0] == 255:
            self.step1()
            return

        self.environment = retval[1]
        self.step1()

    def step1_monitoring(self):
        list = []
        for key, val in self.MONITORINGS.iteritems():
            list += [key, val, "ON" if self.monitoring == key else "OFF"]

        retval = gui_radiolist_box("Schritt 1: Monitoring-Agent", "Waehlen sie den Monitoring-Agenten", list)
        # Abbrechen
        if retval[0] == 1 or retval[0] == 255:
            self.step1()
            return

        self.monitoring = retval[1]
        self.step1()

    def step1_license(self):
        retval = gui_input_box("Schritt 1: Proxmox-Lizenz", "Geben Sie den Proxmox-Schluessel ein", self.license)
        # Abbrechen
        if retval[0] == 1 or retval[0] == 255:
            self.step1()
            return

        self.license = retval[1]
        self.step1()

    def step1_mgmtip(self):
        retval = gui_input_box("Schritt 1: Mgmt-IP", "Geben Sie die IP des Managementservers ein", self.mgmt_ip)
        # Abbrechen
        if retval[0] == 1 or retval[0] == 255:
            self.step1()
            return

        self.mgmt_ip = retval[1]
        self.step1()

    def step1_aptproxy(self):
        retval = gui_yesno_box("Installer", "Mochten Sie den iteas apt-Proxy benutzen?")
        if retval[0] == 0:
            self.proxy = True
        elif retval[0] == 1:
            self.proxy = False

        # Abbrechen
        if retval[0] == 255:
            self.step1()
            return

        self.step1()

    def step1_backuppc(self):
        retval = gui_yesno_box("Installer", "Mochten Sie BackupPC dazuinstallieren?")
        if retval[0] == 0:
            self.backuppc = True
        elif retval[0] == 1:
            self.backuppc = False

        # Abbrechen
        if retval[0] == 255:
            self.step1()
            return

        self.step1()

    def step1_vmtemplateimport(self):
        list = []
        for key, val in self.VM_IMPORTS.iteritems():
            list += [key, val["name"], "ON" if key in self.vm_import else "OFF"]

        retval = gui_checklist_box("Schritt 1: VM-Template-Import", "Waehlen sie die VMs die importiert werden sollen", list)
        # Abbrechen
        if retval[0] == 1 or retval[0] == 255:
            self.step1()
            return

        self.vm_import = []
        for val in retval[1]:
            self.vm_import += [val]

        self.step1()

    def step1_shareclients(self):
        retval = gui_input_box("Schritt 1: Freigabe-Clients", "Geben Sie die Clients/Netze an, die Zugriffe auf die Freigaben haben sollen. Mehrere Eintraege muessen durch Leerzeichen getrennt sein.", " ".join(self.share_clients))
        # Abbrechen
        if retval[0] == 1 or retval[0] == 255:
            self.step1()
            return

        self.share_clients = retval[1].split(" ")
        self.step1()

    def step2(self):
        if self.environment == "stable" and self.license == "":
            gui_message_box("Installer", "Sie muessen eine Lizenz angeben wenn Enterprise Updates ausgewaehlt wurden!")
            self.step1()
            return

        if self.internet == False:
            gui_message_box("Installer", "Es muss eine Internetverbindung bestehen um fortzufahren!")
            self.step1()
            return

        ############ Allgemeine Konfiguration
        if self.license != "":
            retval = run_cmd_output('pvesubscription set ' + self.license)
            if retval[0] == 255:
                gui_message_box("Proxmox Lizenzinstallation", "Die Lizenz konnte nicht installiert werden, bitte pruefen Sie Ihre Lizenznummer. Fehler: " + retval[2])
                self.step1()
                return

            print "Warte auf Registrierung der Proxmox-Subscription..."
            time.sleep(30)

        # Proxmox Testing Quellen aktivieren
        if self.environment == "test":
            file_create("/etc/apt/sources.list.d/pve-enterprise.list", "# deb https://enterprise.proxmox.com/debian jessie pve-enterprise")
            file_create("/etc/apt/sources.list.d/pve-no-subscription.list", "deb http://download.proxmox.com/debian jessie pve-no-subscription")
        elif self.environment == "noupdate":
            file_create("/etc/apt/sources.list.d/pve-enterprise.list", "# deb https://enterprise.proxmox.com/debian jessie pve-enterprise")
            file_create("/etc/apt/sources.list.d/pve-no-subscription.list", "# deb http://download.proxmox.com/debian jessie pve-no-subscription")

        # If lvm-thin convert to standard file storage if backup-machine
        if self.machine_type == "backup" and run_cmd('pvesh get /storage | grep -i lvmthin', argShell=True) == 0:
            run_cmd('pvesh delete /storage/local-lvm')
            run_cmd('lvremove /dev/pve/data -f')
            run_cmd('lvcreate -Wy -l100%FREE -ndata pve')
            run_cmd('mkfs.ext4 -m1 /dev/pve/data')
            run_cmd('mount /dev/pve/data /var/lib/vz')
            file_append("/etc/fstab", "/dev/pve/data /var/lib/vz ext4 defaults 0 1")

        # Mount Template NFS-Share und importiere VMs
        storage = "local"
        if run_cmd('pvesh get /storage | grep -i lvmthin', argShell=True) == 0:
            storage = "local-lvm"

        if len(self.vm_import) > 0:
            if run_cmd('mount ' + VM_TEMPLATE_NFS + ' /mnt') == 0:
                for vm_id in self.vm_import:
                    (ret, filename) = run_cmd_stdout("ls -t /mnt/dump/vzdump-qemu-%s*vma* | head -n1" % vm_id, argShell=True)
                    if filename != "":
                        run_cmd("qmrestore %s %s -storage %s" % (filename.strip(), vm_id, storage))
                        if self.VM_IMPORTS[vm_id]["template"] == True:
                            run_cmd("qm template %s" % vm_id)

                run_cmd('umount /mnt')
            else:
                gui_message_box("Installer", "NFS konnte nicht gemounted werden, VMs werden nicht importiert!")

        # Apt-Proxy Cache
        if self.proxy == True:
            file_create("/etc/apt/apt.conf.d/01proxy", 'Acquire::http { Proxy "http://10.69.99.10:3142"; };')

        # Installieren allgemeine Tools und Monitoring-Agent
        file_create("/etc/apt/sources.list.d/styrion.list", "deb [trusted=yes] http://styrion.at/apt ./")
        run_cmd('apt-key adv --recv-keys --keyserver keyserver.ubuntu.com 2FAB19E7CCB7F415')
        run_cmd('apt-get update')
        run_cmd('apt-get dist-upgrade -y')
        run_cmd('apt-get install htop elinks unp postfix sudo screen zsh tmux bwm-ng pigz sysstat ethtool nload apcupsd ntfs-3g usbmount sl -y')
        if self.monitoring == "nagios":
            run_cmd('apt-get install nagios-nrpe-server -y')
        elif self.monitoring == "checkmk":
            run_cmd('apt-get install xinetd check-mk-agent -y')

        # SUDOers
        file_append("/etc/sudoers", "#backuppc      ALL=(ALL) NOPASSWD: /usr/bin/rsync")
        file_append("/etc/sudoers", "#backuppc      ALL=(ALL) NOPASSWD: /bin/tar")

        # Monitoring Konfiguration
        if self.monitoring == "nagios":

            # SUDOers
            file_append("/etc/sudoers", "nagios      ALL=(ALL) NOPASSWD: /usr/lib/nagios/plugins/")
            file_append("/etc/sudoers", "nagios      ALL=(ALL) NOPASSWD: /usr/sbin/hpssacli")
            file_append("/etc/sudoers", "nagios      ALL=(ALL) NOPASSWD: /sbin/hpasmcli")
            file_append("/etc/sudoers", "#nagios      ALL=(ALL) NOPASSWD: /bin/su")
            file_append("/etc/sudoers", "#nagios    ALL=(backuppc) NOPASSWD: ALL")

            if self.mgmt_ip != "":
                file_replace_line("/etc/nagios/nrpe.cfg", "allowed_hosts=", "allowed_hosts=127.0.0.1,%s" % self.mgmt_ip)

            run_cmd('wget -O /usr/lib/nagios/plugins/check_vg_size https://ftp.iteas.at/public/nagios/plugins/check_vg_size')
            run_cmd('wget -O /usr/lib/nagios/plugins/check_zpool-1.sh https://ftp.iteas.at/public/nagios/plugins/check_zpool-1.sh')
            run_cmd('wget -O /usr/lib/nagios/plugins/check_zpool.sh https://ftp.iteas.at/public/nagios/plugins/check_zpool.sh')
            run_cmd('wget -O /usr/lib/nagios/plugins/check_backuppc https://ftp.iteas.at/public/nagios/plugins/check_backuppc')
            run_cmd('wget -O /usr/lib/nagios/plugins/check_proc_backuppc.sh https://ftp.iteas.at/public/nagios/plugins/check_proc_backuppc.sh')
            run_cmd('wget -O /usr/lib/nagios/plugins/check_smb https://ftp.iteas.at/public/nagios/plugins/check_smb')
            run_cmd('wget -O /usr/lib/nagios/plugins/check_apcupsd https://ftp.iteas.at/public/nagios/plugins/check_apcupsd')
            run_cmd('chmod +x /usr/lib/nagios/plugins/check_vg_size')
            run_cmd('chmod +x /usr/lib/nagios/plugins/check_zpool-1.sh')
            run_cmd('chmod +x /usr/lib/nagios/plugins/check_zpool.sh')
            run_cmd('chmod +x /usr/lib/nagios/plugins/check_backuppc')
            run_cmd('chmod +x /usr/lib/nagios/plugins/check_proc_backuppc.sh')
            run_cmd('chmod +x /usr/lib/nagios/plugins/check_smb')
            run_cmd('chmod +x /usr/lib/nagios/plugins/check_apcupsd')

            file_append("/etc/nagios/nrpe.cfg", "command[check_disk1]=/usr/lib/nagios/plugins/check_disk -w 7% -c 3% -p / -p /var/lib/vz")
            file_append("/etc/nagios/nrpe.cfg", "command[check_swap]=/usr/lib/nagios/plugins/check_swap -w 80% -c 70%")
            file_append("/etc/nagios/nrpe.cfg", "command[check_uptime]=/usr/lib/nagios/plugins/check_uptime")
            file_append("/etc/nagios/nrpe.cfg", "command[check_smtp]=/usr/lib/nagios/plugins/check_smtp -H localhost")

            file_append("/etc/nagios/nrpe.cfg", "#command[check_hddtemp_ssd1]=sudo /usr/lib/nagios/plugins/check_hddtemp.sh /dev/disk/by-id/ata-xxx 63 65")
            file_append("/etc/nagios/nrpe.cfg", "#command[check_smart_ssd2]=sudo /usr/lib/nagios/plugins/check_smart -d /dev/disk/by-id/ata-xxx -i ata")
            file_append("/etc/nagios/nrpe.cfg", "#command[check_smart_hdd1]=sudo /usr/lib/nagios/plugins/check_smart -d /dev/disk/by-id/ata-xxx -i scsi")

            file_append("/etc/nagios/nrpe.cfg", "#command[check_zpool-1]=sudo /usr/lib/nagios/plugins/check_zpool-1.sh")
            file_append("/etc/nagios/nrpe.cfg", "#command[check_zpool]=sudo /usr/lib/nagios/plugins/check_zpool.sh -p ALL -w 95 -c 98")

            file_append("/etc/nagios/nrpe.cfg", "command[check_apcupsd_bcharge]=/usr/lib/nagios/plugins/check_apcupsd -c 50 -w 70 bcharge")
            file_append("/etc/nagios/nrpe.cfg", "command[check_apcupsd_loadpct]=/usr/lib/nagios/plugins/check_apcupsd -c 90 -w 80 loadpct")
            file_append("/etc/nagios/nrpe.cfg", "command[check_apcupsd_timeleft]=/usr/lib/nagios/plugins/check_apcupsd -c 5 -w 10 timeleft")
            file_append("/etc/nagios/nrpe.cfg", "command[check_apcupsd_itemp]=/usr/lib/nagios/plugins/check_apcupsd -c 45 -w 35 itemp")

            file_append("/etc/nagios/nrpe.cfg", '#command[check_sensors_Core_0]=sudo /usr/lib/nagios/plugins/check_lm_sensors  -h "Core 0"=57,62')
            file_append("/etc/nagios/nrpe.cfg", '#command[check_sensors_Core_2]=sudo /usr/lib/nagios/plugins/check_lm_sensors  -h "Core 2"=57,62')
            file_append("/etc/nagios/nrpe.cfg", '#command[check_sensors_systin]=sudo /usr/lib/nagios/plugins/check_lm_sensors  -h "SYSTIN"=45,50')
            file_append("/etc/nagios/nrpe.cfg", '#command[check_sensors_cputin]=sudo /usr/lib/nagios/plugins/check_lm_sensors  -h "CPUTIN"=45,50')
            file_append("/etc/nagios/nrpe.cfg", '#command[check_sensors_auxtin]=sudo /usr/lib/nagios/plugins/check_lm_sensors  -h "AUXTIN"=35,40')
            file_append("/etc/nagios/nrpe.cfg", '#command[check_sensors_fan1]=sudo /usr/lib/nagios/plugins/check_lm_sensors  -l "fan1"=3000,2500')

            file_append("/etc/nagios/nrpe.cfg", "command[check_backuppc_hosts]=sudo -u backuppc /usr/lib/nagios/plugins/check_backuppc")
            file_append("/etc/nagios/nrpe.cfg", "command[check_backuppc]=/usr/lib/nagios/plugins/check_proc_backuppc.sh")

            file_replace_line("/etc/nagios/nrpe.cfg", "check_total_procs", "command[check_total_procs]=/usr/lib/nagios/plugins/check_procs -w 600 -c 650")

        elif self.monitoring == "checkmk":

            if self.mgmt_ip != "":
                file_replace_line("/etc/xinetd.d/check_mk", "only_from", "only_from = %s" % self.mgmt_ip)

            # Check-MK-Agent Config
            run_cmd('wget -O /tmp/mk_smart https://git.styrion.net/iteas/check_mk-smart-plugin/raw/master/smart')
            run_cmd('mv /tmp/mk_smart /usr/lib/check_mk_agent/plugins/')
            run_cmd('wget -O /tmp/mk_apcupsd https://git.styrion.net/iteas/iteas-tools/raw/master/proxmox/usr/lib/check_mk_agent/plugins/mk_apcupsd')
            run_cmd('mv /tmp/mk_apcupsd /usr/lib/check_mk_agent/plugins/')
            run_cmd('wget -O /tmp/mk_dmi_sysinfo https://git.styrion.net/iteas/iteas-tools/raw/master/proxmox/usr/lib/check_mk_agent/plugins/mk_dmi_sysinfo')
            run_cmd('mv /tmp/mk_dmi_sysinfo /usr/lib/check_mk_agent/plugins/')
            run_cmd('wget -O /tmp/mk_inventory https://git.styrion.net/iteas/iteas-tools/raw/master/proxmox/usr/lib/check_mk_agent/plugins/mk_inventory')
            run_cmd('mv /tmp/mk_inventory /usr/lib/check_mk_agent/plugins/')
            run_cmd('wget -O /tmp/mk_lmsensors https://git.styrion.net/iteas/iteas-tools/raw/master/proxmox/usr/lib/check_mk_agent/plugins/mk_lmsensors')
            run_cmd('mv /tmp/mk_lmsensors /usr/lib/check_mk_agent/plugins/')
            run_cmd('wget -O /tmp/mk_logins https://git.styrion.net/iteas/iteas-tools/raw/master/proxmox/usr/lib/check_mk_agent/plugins/mk_logins')
            run_cmd('mv /tmp/mk_logins /usr/lib/check_mk_agent/plugins/')
            run_cmd('wget -O /tmp/mk_nfsexports https://git.styrion.net/iteas/iteas-tools/raw/master/proxmox/usr/lib/check_mk_agent/plugins/mk_nfsexports')
            run_cmd('mv /tmp/mk_nfsexports /usr/lib/check_mk_agent/plugins/')
            run_cmd('wget -O /tmp/mk_netstat https://git.styrion.net/iteas/iteas-tools/raw/master/proxmox/usr/lib/check_mk_agent/plugins/mk_netstat')
            run_cmd('mv /tmp/mk_netstat /usr/lib/check_mk_agent/plugins/')
            run_cmd('chmod +x /usr/lib/check_mk_agent/plugins/mk_*', argShell=True)

        # APC
        run_cmd('wget -O /etc/apcupsd/apcupsd.conf https://git.styrion.net/iteas/iteas-tools/raw/master/proxmox/etc/apcupsd.conf')
        file_replace_line("/etc/default/apcupsd", "ISCONFIGURED", "ISCONFIGURED=yes")
        run_cmd('systemctl enable apcupsd.service')

        # Nano
        run_cmd('wget -O /tmp/nano.tar https://ftp.iteas.at/public/hp/proxmox/nano.tar')
        run_cmd('tar -xf /tmp/nano.tar -C /root')
        run_cmd('rm /tmp/nano.tar')

        # ZSH
        run_cmd('wget -O /tmp/zshrc_root https://ftp.iteas.at/public/hp/proxmox/zshrc_root')
        run_cmd('mv /tmp/zshrc_root /root/.zshrc')
        file_replace_line("/root/.zshrc", "iteas.local", 'export PS1="%UDomain:%u %B%F{yellow}' + self.domain + ' $PS1"')
        run_cmd('usermod -s /bin/zsh root')

        # Postfix
        file_replace_line("/etc/postfix/main.cf", "myhostname=", "myhostname=" + self.fqdn + ".monitoring.iteas.at")
        file_replace_line("/etc/postfix/main.cf", "relayhost =", "relayhost = smtp.styrion.net")
        run_cmd('systemctl restart postfix.service')

        # PIGZ
        run_cmd('mv /bin/gzip /bin/gzip_backup')
        run_cmd('ln -s /usr/bin/pigz /bin/gzip')

        # SystemD
        run_cmd('wget -O /etc/systemd/system/rc.local.shutdown.service https://git.styrion.net/iteas/iteas-tools/raw/master/proxmox/systemd/rc.local.shutdown.service')
        run_cmd('wget -O /etc/rc.local.shutdown https://git.styrion.net/iteas/iteas-tools/raw/master/proxmox/systemd/rc.local.shutdown')
        run_cmd('systemctl enable rc.local.shutdown.service')
        
        # Füge USB Storgage für Automount hinzu
        run_cmd('pvesm add dir USB -path /media/usb0 -maxfiles 0 -content vztmpl,iso,backup')

        # SysCTL
        file_append("/etc/sysctl.conf", "vm.swappiness=0")
        file_append("/etc/sysctl.conf", "fs.inotify.max_user_watches=1048576")

        # BackupPC
        if self.backuppc == True:
            run_cmd('apt-get install backuppc -y')
            run_cmd('setcap cap_net_raw+ep /bin/ping6')
            run_cmd('setcap cap_net_raw+ep /bin/ping')

            if self.filesystem == "zfs":
                run_cmd('zfs create rpool/ROOT/pve-1/backuppc')
                run_cmd("cp -a /var/lib/backuppc/* /backuppc/.", argShell=True)
                run_cmd("chown -R backuppc:backuppc /backuppc")
                file_replace_line("/etc/backuppc/config.pl", "$Conf{TopDir}      =", "$Conf{TopDir}      = '/backuppc';")
                file_replace_line("/etc/backuppc/config.pl", "$Conf{LogDir}      =", "$Conf{LogDir}      = '/backuppc/log';")
            else:
                run_cmd('mkdir /var/lib/vz/backuppc')
                run_cmd("cp -a /var/lib/backuppc/* /var/lib/vz/backuppc/.", argShell=True)
                run_cmd("chown -R backuppc:backuppc /var/lib/vz/backuppc")
                file_replace_line("/etc/backuppc/config.pl", "$Conf{TopDir}      =", "$Conf{TopDir}      = '/var/lib/vz/backuppc';")
                file_replace_line("/etc/backuppc/config.pl", "$Conf{LogDir}      =", "$Conf{LogDir}      = '/var/lib/vz/backuppc/log';")

            run_cmd('systemctl restart backuppc.service')

            file_replace_line("/root/.zshrc", "prompt fade red", "prompt fade blue")
            file_replace_line("/root/.zshrc", 'echo "HELLO ADMINISTRATOR!"', 'echo "HELLO SERVICEUSER!"')

        ############ Konfiguration für Backup-Server
        if self.machine_type == "backup":
            # NFS, Samba & ZFS
            run_cmd('apt-get install nfs-kernel-server samba -y')
            file_create("/etc/exports", "/export 	*(acl,sync,no_subtree_check,fsid=0,rw)")
            clients = ""
            for client in self.share_clients:
                clients += "%s(sync,no_subtree_check,no_root_squash,rw) " % client

            #password = gui_password_verify_box("Samba Passwort", "Geben Sie das Passwort fuer den Samba Benutzer 'admin' an:", "Geben Sie das Passwort fuer den Samba Benutzer 'admin' erneut an:")
            password = SMB_ADMIN_PASSWD
            run_cmd("useradd backup -m -G sambashare -p '%s'" % password, argShell=True)
            run_cmd("(echo '%s'; echo '%s') | smbpasswd -a backup" % (password, password), argShell=True)
            run_cmd('wget -O /etc/samba/smb.conf https://git.styrion.net/iteas/iteas-tools/raw/master/proxmox/samba/backup_default_smb.conf')

            backup_root = ""
            if self.filesystem == "zfs":
                run_cmd('zfs create rpool/ROOT/pve-1/sicherung')
                run_cmd('zfs create rpool/ROOT/pve-1/Backup')
                file_append("/etc/zfs/zed.d/zed.rc", 'ZED_EMAIL_ADDR="root"')
                file_replace_line("/etc/samba/smb.conf", "path = /var/lib/vz/Backup", "path = /Backup")
                file_replace_line("/etc/nagios/nrpe.cfg", "check_total_procs", "command[check_total_procs]=/usr/lib/nagios/plugins/check_procs -w 800 -c 1000")

                file_append("/etc/exports", "/sicherung     %s" % clients)
                file_append("/etc/exports", "/Backup     %s" % clients)

                backup_root = "/Backup"
            else:
                run_cmd('mkdir /var/lib/vz/sicherung')
                run_cmd('mkdir /var/lib/vz/Backup')
                file_append("/etc/exports", "/var/lib/vz/sicherung     %s" % clients)
                file_append("/etc/exports", "/var/lib/vz/Backup     %s" % clients)
                backup_root = "/var/lib/vz/Backup"

            # Folders for backupassist
            run_cmd('mkdir %s/Daten' % backup_root, argShell=True)
            run_cmd('mkdir %s/Exchange' % backup_root, argShell=True)
            run_cmd('mkdir %s/Image' % backup_root, argShell=True)
            run_cmd('mkdir "%s/Image/Buero PCs"' % backup_root, argShell=True)
            run_cmd('mkdir "%s/Image/Produktion PCs"' % backup_root, argShell=True)
            run_cmd('mkdir "%s/Recovery ISO"' % backup_root, argShell=True)
            run_cmd('mkdir %s/SQL' % backup_root, argShell=True)
            run_cmd("chown -R backup:sambashare %s" % backup_root)

            file_replace_line("/etc/samba/smb.conf", "workgroup = iteas.local", "\tworkgroup = %s" % self.domain)

            run_cmd('systemctl enable nfs-kernel-server')
            run_cmd('systemctl start nfs-kernel-server')

            run_cmd('systemctl enable smbd')
            run_cmd('systemctl start smbd')

            # Webmin
            run_cmd('apt-get install perl libnet-ssleay-perl openssl libauthen-pam-perl libpam-runtime libio-pty-perl apt-show-versions python -y')
            run_cmd('wget -O /tmp/webmin_1.840_all.deb http://downloads.sourceforge.net/project/webadmin/webmin/1.840/webmin_1.840_all.deb')
            run_cmd('dpkg --install /tmp/webmin_1.840_all.deb')
            file_append("/etc/webmin/config", "lang_root=de")
            file_append("/etc/webmin/config", "theme_root=authentic-theme")
            file_append("/etc/webmin/miniserv.conf", "preroot_root=authentic-theme")
            run_cmd('mkdir /etc/webmin/authentic-theme')
            run_cmd('wget -O /etc/webmin/authentic-theme/favorites.json https://git.styrion.net/iteas/iteas-tools/raw/master/proxmox/webmin/favorites.json')
            run_cmd('/etc/init.d/webmin restart')


        ############ Konfiguration für HP
        if self.machine_vendor == "hp":
            # HP-Tools
            file_create("/etc/apt/sources.list.d/hp.list", "deb http://downloads.linux.hpe.com/SDR/downloads/MCP jessie/current non-free")
            file_append("/etc/apt/sources.list.d/hp.list", "deb http://downloads.linux.hpe.com/SDR/downloads/MCP/debian jessie/current non-free")
            run_cmd('apt-key adv --recv-keys --keyserver keyserver.ubuntu.com 527BC53A2689B887')
            run_cmd('apt-key adv --recv-keys --keyserver keyserver.ubuntu.com FADD8D64B1275EA3')
            run_cmd('apt-key adv --recv-keys --keyserver keyserver.ubuntu.com C208ADDE26C2B797')
            run_cmd('apt-key adv --recv-keys --keyserver keyserver.ubuntu.com 26C2B797')
            run_cmd('apt-get update')
            run_cmd('apt-get install hp-health hpssacli hponcfg -y')
            run_cmd('ln -s /usr/sbin/hpssacli /usr/sbin/hpacucli')
            run_cmd('/etc/init.d/hp-asrd stop')
            run_cmd('/etc/init.d/hp-health stop')

            # Monitoring-Agent
            if self.monitoring == "nagios":
                run_cmd('wget -O /usr/lib/nagios/plugins/check_hparray http://ftp.iteas.at/public/nagios/plugins/check_hparray')
                run_cmd('wget -O /usr/lib/nagios/plugins/check_hpasm http://ftp.iteas.at/public/nagios/plugins/check_hpasm')
                run_cmd('chmod +x /usr/lib/nagios/plugins/check_hparray')
                run_cmd('chmod +x /usr/lib/nagios/plugins/check_hpasm')
                file_append("/etc/nagios/nrpe.cfg", "command[check_cciss]=sudo /usr/lib/nagios/plugins/check_hparray -s 0 -v")
                file_append("/etc/nagios/nrpe.cfg", "command[check_hpasm]=/usr/lib/nagios/plugins/check_hpasm --perfdata=short")

        elif self.machine_vendor == "dell":
            # Dell-Tools
            file_create("/etc/apt/sources.list.d/linux.dell.com.sources.list", "deb http://linux.dell.com/repo/community/ubuntu wheezy openmanage")
            run_cmd('gpg --keyserver pool.sks-keyservers.net --recv-key 1285491434D8786F')
            run_cmd('gpg -a --export 1285491434D8786F | apt-key add -', argShell=True)
            run_cmd('apt-get update')
            run_cmd('apt-get install srvadmin-hapi srvadmin-isvc srvadmin-storageservices srvadmin-base srvadmin-omcommon srvadmin-sysfsutils srvadmin-server-cli dcism -y --force-yes')
            run_cmd('apt-get install srvadmin-idrac srvadmin-idrac-ivmcli srvadmin-idrac-vmcli srvadmin-idrac7 srvadmin-idracadm srvadmin-idracadm7 -y --force-yes')
            run_cmd_output('systemctl enable dcismeng.service')
            run_cmd_output('systemctl enable instsvcdrv.service')

            # Monitoring-Agent
            if self.monitoring == "nagios":
                run_cmd('wget -O /tmp/check-openmanage_3.7.12-1_all.deb https://ftp.iteas.at/public/nagios/plugins/check-openmanage_3.7.12-1_all.deb')
                run_cmd('dpkg -i /tmp/check-openmanage_3.7.12-1_all.deb')

                run_cmd('wget -O /usr/lib/nagios/plugins/check_openmanage https://ftp.iteas.at/public/nagios/plugins/check_openmanage')
                run_cmd('chmod +x /usr/lib/nagios/plugins/check_openmanage')
                file_append("/etc/nagios/nrpe.cfg", "command[check_openmanage]=/usr/lib/nagios/plugins/check_openmanage -p -I")


        run_cmd('apt-get install -f')
        if self.proxy == True:
            run_cmd('rm /etc/apt/apt.conf.d/01proxy')

        sum_txt = """-------------------------------------------------------------------------------
ITEAS Proxmox Installationsbericht

Loginmoeglichkeiten:
  https://%s:8006 -> Weboberflaeche Virtualisierung
""" % check_systemip(show_prefix=False)

        if self.machine_type == "backup":
            sum_txt += "  https://%s:10000 -> Weboberflaeche Webmin (NFSfreigaben, Samba, etc.)" % check_systemip(show_prefix=False)


        sum_txt += """
  SSH ueber CMD f.e "ssh root@%s"

Folgende lokale Benutzer wurden angelegt:
  root (Administrator) SSH, Virtualisierung, Webmin
""" % check_systemip(show_prefix=False)

        if self.machine_type == "backup":
            sum_txt += "  backup (fuer den Zugriff auf Freigaben) Samba"

        sum_txt += """

Das Komplette Installationslog ist auf
  /var/log/proxmox_install.log einsehbar.
-------------------------------------------------------------------------------
"""

        fr = open("/root/proxmox_report.txt", "w")
        fr.write(sum_txt)
        fr.close()

        gui_text_box("/root/proxmox_report.txt")

        # Installation fertig
        retval = gui_yesno_box("Installer", "Die Installation wurde abgeschlossen! Moechten Sie den PC/Server neustarten?")
        if retval[0] == 0:
            pbox = gui_progress_box("PC/Server wird automatisch neugestartet...", 0)
            for x in range(0, 5):
                pbox.update(x*20)
                time.sleep(1)

            pbox.finish()
            run_cmd('reboot')
        elif retval[0] == 1:
            gui_message_box("Installer", "Sie muessen den PC/Server manuell neustarten um die Installation abzuschliessen!")


i = Installer()
i.start()
logger.close()
