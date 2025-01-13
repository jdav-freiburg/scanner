# Bill Scanner

## What does this do?

This small project scans bills and automatically sends them to an email address for further processing.

## Hardware setup

We use a Brother DS-640 connected to a Rasperry Pi Zero 2 W with a Waveshare Touch Display 3.5".

![How It Works](./docs/how_it_works.svg)

<!--<img src="./docs/how_it_works.svg">-->

The scanner has been customized to allow the Raspberry Pi to control the paper detector. Also, the motor control can be disabled earlier than the scanner does itself.

![Front/Inside](./docs/box.svg)

<!--<img src="./docs/box.svg">-->

The outer box is made of Multiplex Birch 9mm with a lockable door to the side. The openings for screen and paper intake are miter sawn with 30°.

## Raspberry Pi Setup

Install a new SD Card with Raspbian Bookworm Lite.

Install graphics libraries without unnecessary stuff

```
sudo apt install raspberrypi-ui-mods -y
sudo apt install libraspberrypi-dev unzip cmake xserver-xorg-input-evdev xinput-calibrator -y
```

Install the display drivers from the Waveshare homepage as described.

Install the python app by default means.

```
sudo apt install python3-pyqt5 python3-venv qt5-qmake qtvirtualkeyboard-plugin qml-module-qtquick2 qml-module-qtquick-layouts qml-module-qtquick-controls qml-module-qt-labs-folderlistmodel qml-module-qt-labs-platform -y
python3 -m venv --system-site-packages venv
venv/bin/pip install "git+https://github.com/jdav-freiburg/scanner"
```

Possible config vars:

- `SCREEN_RESOLUTION_WIDTH`: The size of the display. Defaults to 960.
- `SCREEN_RESOLUTION_HEIGHT`: The size of the display. Defaults to 640.
- `SEND_TARGET`: The target to send the resulting data to. Either `api` or `mail`.
- `API_TARGET`: (if `SEND_TARGET=api`) URL to the srvapi endpoint. Should be: `http(s)://server/api/bill`.
- `API_KEY`: (if `SEND_TARGET=api`) The same key as configured for the srvapi.
- `MAIL_TO`: (if `SEND_TARGET=mail`) The destination email address.
- `MAIL_FROM`: (if `SEND_TARGET=mail`) The sender email address.
- `MAIL_SSL`: (if `SEND_TARGET=mail`) If not empty, use SSL.
- `MAIL_START_TLS`: (if `SEND_TARGET=mail`) If not empty, use STARTTLS.
- `MAIL_HOST`: (if `SEND_TARGET=mail`) Mail host.
- `MAIL_PORT`: (if `SEND_TARGET=mail`) Mail port.
- `MAIL_USER`: (if `SEND_TARGET=mail`) If not empty, use this and the password for authentication.
- `MAIL_PASSWORD`: (if `SEND_TARGET=mail`) If not empty, use this and the user for authentication.
- `DISABLE_IBAN_CHECK`: Disable IBAN verification

Create the looping startup script:

```
echo '#!/bin/bash
cd "$(dirname "$0")"
export SEND_TARGET="api|mail"
# Add the other config vars.
while true; do
    venv/bin/scanapp
done
'> scanapp.sh
chmod +x scanapp.sh
```

Set the python app as default startup app:

`nano .config/lxsession/LXDE-pi/autostart`:

```
#@lxpanel --profile LXDE-pi
#@pcmanfm --desktop --profile LXDE-pi
@xscreensaver -no-splash
@bash scanapp.sh
```

### Setting up the scanner driver

Brother does not provide drivers for ARM processors. Thus this must be emulated using qemu (which just works on raspberry pi zero 2 w):

(run all as `root`, e.g. `sudo -i`)

```
wget -O /tmp/brscan5-1.3.5-0.amd64.deb https://download.brother.com/welcome/dlf104033/brscan5-1.3.5-0.amd64.deb
apt-get install qemu-user-static debootstrap binutils
mkdir /opt/scanberryd-amd64
debootstrap --arch=amd64 --variant=minbase --foreign bullseye /opt/scanberryd-amd64/
mount -t proc proc /opt/scanberryd-amd64/proc
mount -t sysfs sys /opt/scanberryd-amd64/sys
mount -o bind /dev /opt/scanberryd-amd64/dev
mount -o bind /tmp /opt/scanberryd-amd64/tmp
mount -o bind /dev /opt/scanberryd-amd64/dev
mount -o bind /tmp /opt/scanberryd-amd64/tmp
mount -o bind /run /opt/scanberryd-amd64/run

# Finish the debootstrap
chroot /opt/scanberryd-amd64/ /debootstrap/debootstrap --second-stage
# Install sane first (brscan5 is missing the dependency)
chroot /opt/scanberryd-amd64/ apt install sane-utils
# Install the brscan5 driver for sane (does not have correct dependencies)
chroot /opt/scanberryd-amd64/ apt install /tmp/brscan5-1.3.5-0.i386.deb

# Fix the scanners being checked to speed up scanimage
# Backup the old config first
mv /opt/scanberryd-amd64/etc/sane.d/dll.conf /opt/scanberryd-amd64/etc/sane.d/dll.conf.bak
# Only write the brother5 driver to the sane libraries to check
echo "brother5" >/opt/scanberryd-amd64/etc/sane.d/dll.conf
```

Now the environment is ready and the scanner can be called like this:

```
sudo chroot /opt/scanberryd-amd64/ bash -c "scanimage --format=png" > test.png
```
