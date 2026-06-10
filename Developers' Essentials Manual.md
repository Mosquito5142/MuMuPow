---
title: "Developers' Essentials: Manual"
source: "https://www.mumuplayer.com/help/win/developers-essentials-manual.html"
author:
published:
created: 2026-06-10
description: "The following are commonly used adb commands for developers intending to run commands for MuMu."
tags:
  - "clippings"
---
MuMuPlayer Help Center

Find solutions to all your problems with MuMuPlayer

Ask anything about MuMuPlayer

The following is a brief list of commonly used adb commands for developers who want to run commands using adb for MuMu Player.

**\[Common adb commands\]**

## 1\. Adb version

MuMu Player's built-in adb (located in the installation directory)

C:\\Program Files (x86)\\Nemu\\vmonitor\\bin\\adb\_server.exe

Download from the website:

① **Recommended**: [https://adbshell.com/downloads](https://adbshell.com/downloads)

② Official Website: [https://developer.android.com/studio/releases/platform-tools](https://developer.android.com/studio/releases/platform-tools)

## 2\. Connect with device

Open cmd (if using MuMu Player's built-in adb, then cd C:\\Program Files (x86)\\Nemu\\vmonitor\\bin\\)

adb kill-server (Built-in adb: adb\_server.exe kill-server)

Connect to the emulator's port: adb connect 127.0.0.1:7555 (Built-in adb: adb\_server.exe connect 127.0.0.1:7555)

List connected devices: adb devices (Built-in adb: adb\_server.exe devices). Normally, you will be prompted that MuMu Player's device has been connected and you can proceed to the next step.

![Developers' Essentials: Manual1](https://r.res.easebar.com/pic/20210428/5d51a0f6-51a1-46a8-9e68-3aaf8f9384dc.png)

**Remark:** If "127.0.0.1:7555 device" does not appear in the list, keep trying to connect by using adb kill-server and adb connect 127.0.0.1:7555

## 3\. How to operate on MuMu Player with multiple devices connected

Command format: alternative commands for adb -s emulator port, for example: adb -s 127.0.0.1:7555 shell pm list package -3

## 4\. Install and uninstall apk

Run the following commands with the connected MuMu Player:

Install apk

adb install C:\\xx.apk

Uninstall apk adb uninstall C:\\xx.apk

## 5\. List the package names of installed applications

List of all package names

adb shell pm list packages

List of names for all third-party packages

adb shell pm list packages -3

List of system package names

adb shell pm list packages -s

The package names of running applications

adb shell dumpsys window | findstr mCurrentFocus

When running multiple instances of the same application, please check whether the emulator version is earlier than 2.2.2x86/x64, if it is, then the multi-start package name should generally follow the format of original package name + suffix. Taking Honkai Impact 3rd as an example:

![Developers' Essentials: Manual2](https://r.res.easebar.com/pic/20210428/8e4ec74f-7ebb-41d8-b2f2-72484b009e21.png)

If the emulator is newer than 2.2.2x86/x64, then the multi-start package and the original package should have the same name, so you need to control the multi-start application using UserId (don’t forget to first connect the emulator port using adb connect 127.0.0.1:7555)

## 6\. List the Activity ClassName of an installed application

Run adb logcat ActivityManager:I \*:s | findstr "cmp" and execute the target application

Taking “Identity V” as an example, you can execute:

where the first cmp=com.netease.dwrg/.Launcher means: Application's package

name/Activity ClassName, the complete Activity

name=com.netease.dwrg.Launcher

## 7\. Start application

adb shell am start -n Application package name/application Activity ClassName

Taking “Identity V” as an example, you can execute:

adb shell am start -n com.netease.dwrg/.Launcher

To view the startup time, execute adb shell am start -W Application package

name/application Activity ClassName

For instance:

![Developers' Essentials: Manual4](https://r.res.easebar.com/pic/20210428/3500f6e9-b62c-453b-9b2e-2e848e005117.png)

## 8\. Close application

adb shell am force-stop Package Name

Taking “Identity V” as an example, you can execute:

adb shell am force-stop com.netease.dwrg

## 9\. View application version

adb shell dumpsys package Package Name | findstr version

Taking “Identity V” as an example, you can execute:

![Developers' Essentials: Manual5](https://r.res.easebar.com/pic/20210428/c3927665-c710-488f-bc46-7022e1fe535a.png)

## 10\. Clear application data

adb shell pm clear Package Name

## 11\. Simulated input

Key input

adb shell input keyevent Key value

For example:

adb shell input keyevent 3

means pressing the HOME key (values of other keys can be obtained via online search)

String input

adb shell input text String

For example: adb shell input text test

would return the string "test"

P.S.: Chinese characters are not supported

Mouse click

adb shell input tap X Y

where X and Y are the x and y coordinate values of the current input

Mouse movement

adb shell input swipe X1 Y1 X2 Y2

X1 Y1 and X2 Y2 are the coordinate values of the start and end points respectively

## 12\. Upload files from the computer to the emulator

adb push C:\\test.apk /data

## 13\. Copy files from the emulator to the computer

adb pull /data/test.apk C:\\

## 14\. Take screenshots

Take a screenshot of the current emulator screen

adb shell screencap /data/screen.png

Save the screenshot to the computer

adb pull /data/screen.png C:\\

## 15\. Record screen

Initiate recording

adb shell screenrecord /data/test.mp4

Stop recording

CTRL+C

Export video file

adb pull /data/test.mp4 C:\\

## 16\. View device information

Model

adb shell getprop ro.product.model

Brand

adb shell getprop ro.product.brand

Processor model

adb shell getprop ro.product.board

Android version

adb shell getprop ro.build.version.release

Engine rendering mode

adb shell dumpsys SurfaceFlinger|findstr "GLES"

This command can't be used in version 2.0.30 and above. For now, using it requires an older version.

For other commands, please visit [https://adbshell.com/commands](https://adbshell.com/commands)

**\[How to capture packages\]**

**1)** Download the latest version of "fiddler" and "MuMu Player" respectively;

**2)** Start fiddler via Tools -> Options -> Connections, check "Allow remote computers to connect" and restart the program. **Important! Don't forget to restart;**

![Developers' Essentials: Manual6](https://r.res.easebar.com/pic/20210428/97faa903-803a-47b4-827a-4034d454c84c.png)

**3)** Check the IP. If there is a virtual network card, you need to execute ipconfig/all to check the real IP;

![Developers' Essentials: Manual7](https://r.res.easebar.com/pic/20210428/74c7faf8-ff41-4bdb-b135-02b5c68677ba.png)

**4)** Start the MuMu Player and configure the proxy;

![Developers' Essentials: Manual9](https://r.res.easebar.com/pic/20210428/b79efd2c-ce20-42f3-8bd1-3c3c786e048b.png)

Long press the WiFi name and click "Modify network"

![Developers' Essentials: Manual10](https://r.res.easebar.com/pic/20210428/a1cfc678-1b4c-4238-8003-c40704541198.png)

![Developers' Essentials: Manual12](https://r.res.easebar.com/pic/20210428/4fa50fb0-bc50-4cab-adda-a8c6f726fe4b.png)

**5)** Save and proceed to the next operation.

![Developers' Essentials: Manual13](https://r.res.easebar.com/pic/20210428/9620f040-ec27-4af4-9ac0-10a5f34d296f.png)

End of Article

Keyword: Developer Modedeveloperdeveloper manual