#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Various functions to execute moonlight-embedded
"""
import os
import re
import sys
import time
import xbmc
import xbmcgui
from .avahi import host_check
from .utils import stop_old_container, subprocess_runner, wait_or_cancel


def install():
    """
    Executes the installer script to configure/download the moonlight-embedded docker container
    :return: boolean for success of installation
    """
    script = os.path.join(os.path.dirname(__file__), "bin",
                          "install_moonlight.sh")
    cmd = f"bash {script}"
    proc = subprocess_runner(cmd.split(' '), 'install')
    (status,_) = wait_or_cancel(proc, 'Installation',
                         'Running installation...this may take a few minutes')
    if status == 0:
        return True
    else:
        return False


def launch(res, fps, bitrate, quitafter, hostip, usercustom):
    """
    Launches moonlight-embedded as an external process and kills Kodi so display is available
    Kodi will be automatically relaunched after moonlight-embedded exits

    :param res: video resolution of streaming session
    :param fps: frames per second of streaming session
    :param bitrate: bitrate of streaming session
    :param quitafter: quit flag helpful for desktop sessions
    :param hostip: gamestream host ip (blank if using autodetect)
    :param usercustom: any custom flags the user wants to pass to moonlight
    """

    gameList = load_installed_games(hostip)
    if not gameList:
        xbmcgui.Dialog().ok("No games found.")
        return
    dialog = xbmcgui.Dialog()
    gameIdx = dialog.select("Choose your Game:", gameList)
    if gameIdx == -1:
        xbmcgui.Dialog().ok("No valid game selected.")
        return
    # We split at the first blank to get rid of the number in the beginning
    # We also make sure to put the game name in quotation marks to ensure it to be treated as one arg
    selectedGame = gameList[gameIdx].split(" ", 1)[1].replace("\n", "")
    xbmc.log(
        f"Streaming {selectedGame} with moonlight-embedded, Kodi will now exit.",
        xbmc.LOGINFO,
    )
    # Send quit command from moonlight after existing (helpful for non-steam sessions):
    quitflag = "-quitappafter" if quitafter == "true" else ""

    os.system("systemctl stop kodi") # Must close kodi for proper video display

    # Launch docker, adjusted to just used input variables
    os.system('docker run --rm --name moonlight -t -v moonlight-home:/home/moonlight-user '
        '-v /var/run/dbus:/var/run/dbus --device /dev/vchiq --device /dev/input '
        f'clarkemw/moonlight-embedded-raspbian stream -{res} -fps {fps} -bitrate {bitrate} {quitflag} {usercustom} -app "{selectedGame}" {hostip}')

    os.system("docker wait moonlight")

    os.system("systemctl start kodi")



def load_installed_games(hostip):
    """
    request available games from the Gamestream host

    :return: list of available games
    """
    proc = run_moonlight("list", hostip)
    if proc:
        (status, result) = wait_or_cancel(proc, "List",
                                          "Getting available games...")
        if status == 0 and result:
            ## We expect the list command to follow the pattern below:
            # =========================================
            # Searching for server...
            # Connect to 192.168.178.166...
            # 1. MarioKart8
            # 2. Dolphin
            # 3. Steam
            # =========================================
            # A return code=0 signals that we were successful in obtaining the list.
            gamelist = [game for game in result.splitlines() if re.search('^\d+\.',game)]
            return gamelist


def pair(hostip):
    """
    Generates pairing credentials with a gamestream host
    """
    opt = xbmcgui.Dialog().yesno(
        "Pairing", "Do you want to pair with a Gamestream host?")
    if opt:
        pDialog = xbmcgui.DialogProgress()
        proc = run_moonlight("pair", hostip, blockio=False)
        stdout = ""
        codeFlag = False
        pDialog.create("Pairing", "Launching pairing...")
        while proc and proc.poll() is None and not pDialog.iscanceled():
            try:
                stdout += proc.stdout.read().decode()
            except:
                pass
            if not codeFlag:
                code = re.search(r"Please enter the following PIN on the target PC: (\d+)", stdout)
                if code:
                    codeFlag = True
                    code = code.groups()[0]
                    pDialog.update(
                        50,
                        f"Please enter authentication code {code} on Gamestream host",
                    )
        if proc and not pDialog.iscanceled() and proc.returncode == 0:
            pDialog.update(100, "Complete!")
            time.sleep(3)
        else:
            try:
                proc.terminate()
            except Exception:
                pass
        pDialog.close()
        if re.search(r"Failed to pair to server: Already paired", stdout):
            opt = xbmcgui.Dialog().ok(
                "Pairing",
                "Gamestream credentials already exist for this host.")


def run_moonlight(mode, hostip, blockio=True):
    """
    execute moonlight in a local subprocess (won't work for streaming)

    :param mode: moonlight execution mode (pair/unpair/list etc)
    :param wait: wait for process to complete
    :param block: allow reading of stdout to block
    :return: subprocess object
    """
    stop_old_container(f"moonlight_{mode}")
    if not hostip and not host_check():
        xbmcgui.Dialog().ok(
            "Error",
            "No Gamestream host auto-detected on local network. Check if the gamestream service is started and retry.",
        )
        return None
    cmd = (
        f"docker run --rm -t --name moonlight_{mode}"
        f" -v moonlight-home:/home/moonlight-user -v /var/run/dbus:/var/run/dbus"
        f" clarkemw/moonlight-embedded-raspbian {mode} {hostip}")
    return subprocess_runner(cmd.rstrip().split(" "), "moonlight " + mode, blockio)

def update_moonlight():
    """
    performs a docker pull to update the moonlight-embedded container
    """
    opt = xbmcgui.Dialog().yesno(
        "Update", "Do you want to update the moonlight-embedded docker container?")
    if opt:
        cmd = "docker pull clarkemw/moonlight-embedded-raspbian"
        proc = subprocess_runner(cmd.split(" "), "docker update")
        wait_or_cancel(proc, "Update",
                       "Running docker update...this may take a few minutes")
