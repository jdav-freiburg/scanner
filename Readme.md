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

Install a new SD Card with Raspbian Bookworm.

Install the display drivers from the Waveshare homepage as described.

Install the python app by default means.

```
sudo apt install pipx python3-pyqt5 pipx
pipx install "git+https://github.com/jdav-freiburg/scanner"
```

Set the python app as default startup app:

`nano .config/lxsession/LXDE-pi/autostart`:

```
#@lxpanel --profile LXDE-pi
#@pcmanfm --desktop --profile LXDE-pi
@xscreensaver -no-splash
@.venv/bin/scanapp
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
