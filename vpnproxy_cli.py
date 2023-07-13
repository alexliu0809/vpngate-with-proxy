#!/usr/bin/env python
# -*- coding: utf-8 -*-
__author__ = "duc_tin"
__copyright__ = "Copyright 2015+, duc_tin"
__license__ = "GPLv2"
__version__ = "1.36"
__maintainer__ = "duc_tin"
__email__ = "nguyenbaduc.tin@gmail.com"

import os
import signal
import base64
import time
import datetime
from config import *
from queue import Queue
from threading import Thread
from subprocess import call, Popen, PIPE, check_output

# Get sudo privilege
euid = os.geteuid()
if euid != 0:
    # args = ['sudo', '-E', sys.executable] + sys.argv + [os.environ]
    # os.execlpe('sudo', *args)
    raise RuntimeError('Permission deny! You need to "sudo" or use "./run cli" instead')

# detect Debian based or Redhat based OS's package manager
pkg_mgr = None
check_ls = ["apt-get", "yum", "dnf"]
for pkg in check_ls:
    if check_output("whereis -b {}".format(pkg).split(), universal_newlines=True).strip().split(":")[1]:
        pkg_mgr = pkg

# Define some mirrors of vpngate.net
mirrors = ["http://www.vpngate.net"]  # add your mirrors to config.ini file, not here


# TODO: add user manual to this and can be access by h, help.
# add option to change DNS differ from google


class Server:
    def __init__(self, fname, data):
        self.config_data = data
        self.fname = fname

    def write_file(self):
        txt_data = self.config_data

        extra_option = ['keepalive 5 30\n',  # prevent connection drop due to inactivity timeout
                        'connect-retry 2\n']
        if True:
            txt_data = txt_data.replace("auth-user-pass", "auth-user-pass /data/deploy/FailsFromCrypto/vpngate/login.txt")
            index = txt_data.find('client\n')
            txt_data = txt_data[:index] + ''.join(extra_option) + txt_data[index:]
            index = txt_data.find('auth SHA1\n')
            additional_setup = "route 169.228.66.0 255.255.255.0 net_gateway\nroute 137.110.222.0 255.255.255.0 net_gateway\ndata-ciphers AES-128-GCM:AES-128-CBC\n"
            txt_data = txt_data[:index] + ''.join(additional_setup) + txt_data[index:]

        tmp_vpn = open('vpn_tmp', 'w+')
        tmp_vpn.write(txt_data)
        return tmp_vpn


def get_data():
    ovpn_files = os.listdir("./servers/")
    ovpn_files = ["./servers/" + i for i in ovpn_files if ".ovpn" in i]

    if len(ovpn_files) > 0:
        servers = []
        for ovpn_file in ovpn_files:
            with open(ovpn_file) as f:
                servers.append(Server(ovpn_file, "".join(f.readlines())))
        return servers
    else:
        print('Failed to get VPN servers data\nCheck your network setting and proxy')
        sys.exit(1)


def refresh_data():
    # fetch data from vpngate.net
    print("fetching data")
    vpnlist = get_data()
    sort = sorted(vpnlist, key=lambda x: x.fname)
    return sort, vpnlist

def vpn_manager(ovpn):
    """ Check VPN season
        If vpn tunnel break or fail to create, terminate vpn season
        So openvpn not keep sending requests to proxy server and
         save you from being blocked.
    """
    global dns, verbose, dropped_time

    command = ['openvpn', '--config', ovpn]
    p = Popen(command, stdout=PIPE, stdin=PIPE, universal_newlines=True)
    is_connected = False
    try:
        while p.poll() is None:
            line = p.stdout.readline()
            if verbose == 'yes':
                print(line, end=' ')
            if 'Initialization Sequence Completed' in line:
                dropped_time = 0
                is_connected = True
                print(ctext('VPN tunnel established successfully'.center(40), 'B'))
                print('Ctrl+C to quit VPN'.center(40))
            elif 'Restart pause, ' in line and dropped_time <= max_retry:
                dropped_time += 1
                print(ctext('Vpn has restarted %s time' % dropped_time, 'rB'))
            # Common error
            # 2023-07-03 17:36:19 AUTH: Received control message: AUTH_FAILED
            # 2023-07-03 17:36:19 SIGTERM[soft,auth-failure] received, process exiting
            # which is not captured here
            # but it is fine because is_connected is false
            # we will keep trying until is_connect is true
            elif dropped_time == max_retry or 'Connection timed out' in line or 'Cannot resolve' in line:
                dropped_time = 0
                print(line)
                print(ctext('Terminate vpn', 'B'))
                p.send_signal(signal.SIGINT)
    except KeyboardInterrupt:
        p.send_signal(signal.SIGINT)
        p.wait()
        print(ctext('VPN tunnel is terminated'.center(40), 'B'))
    finally:
        pass

    return is_connected

def signal_term_handler(signal, frame):
    global SIGTERM
    print('\nGot SIGTERM, start exiting\n')
    SIGTERM = 1
    raise KeyboardInterrupt


# ---------------------------- Main  --------------------------------
# dead gracefully
signal.signal(signal.SIGTERM, signal_term_handler)
SIGTERM = 0

# anti dropping
dropped_time = 0
max_retry = 3

# test if alive
test_interval = 0.25
test_timeout = 1

ranked, vpn_list = refresh_data()

round_num = 0
show_top = 40

while True:
    try:
        server_sum = min(len(ranked), show_top)
        # Start by refreshing the list
        if round_num == 0:
            ranked, vpn_list = refresh_data()
            round_num += 1
            continue
        # then try to connect
        elif round_num == 1:
            for chose in range(server_sum):
                print(time.ctime().center(40))
                print('Connecting to #{} {}'.format(chose, ranked[chose].fname))
                # download the openvpn file
                vpn_file = ranked[chose].write_file()
                vpn_file.close()
                is_connected = vpn_manager(os.path.abspath(vpn_file.name))

                round_num = 0

                # Restart the whole thing again
                if is_connected == True:
                    break
                else:
                    print('Failed connect to #{} {}\n'.format(chose, ranked[chose].fname))
                    continue

            # If we cant find anything at the end? try again
            round_num = 0

        if SIGTERM:
            print(ctext('Goodbye'.center(40), 'gB'))
            sys.exit()

    except KeyboardInterrupt:
        time.sleep(0.5)
        print("\n\nSelect another VPN server or 'q' to quit")
