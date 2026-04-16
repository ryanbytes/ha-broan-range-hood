# Broan Range Hood for Home Assistant

Custom Home Assistant integration for Broan/NuTone smart range hoods.

## Features

- Fan on/off control
- 3-step fan speed control
- Light on/off control
- 2-step light level control
- Delay-off switch
- Auto mode sensitivity select
- Connectivity, firmware, and Wi-Fi diagnostic entities

## Setup

1. Copy `custom_components/broan` into your Home Assistant `custom_components` directory.
2. Restart Home Assistant.
3. Add the `Broan Range Hood` integration from the UI.
4. Enter your Broan app email, password, and the printed serial number from the hood label.

The integration resolves the separate AWS IoT thing name automatically.

## Notes

- This project is based on reverse engineering of the official mobile app and device behavior.
- No user credentials, device-specific secrets, or personal environment data are included in this repository.

## Brand Assets

Brand artwork for Home Assistant is included in `custom_components/broan/brand/`.
