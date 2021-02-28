# Motorola MX240a Driver

An attempt at writing a driver for the [Motorola IMFree (MX240a)](http://web.archive.org/web/20070613122039/http://broadband.motorola.com/consumers/products/imfree/).

Now that AIM is long dead, the IMFree is basically useless. 

But I wanted to try using Discord on it.

You could also use it for whatever else because this is pretty much just a Python API to talk to the handset


### Requirements

Python >= 3.8

[hidapi](https://pypi.org/project/hidapi/) -- To talk to the base station

[loguru](https://pypi.org/project/loguru/) -- [Optional] For nice logging

### Resources

- https://github.com/sanko/device-mx240a
    - Mostly working driver code to see how it could be done
    - Protocol notes
- https://sourceforge.net/projects/mx240ad/
    - http://web.archive.org/web/20060613185029/http://ripplelabs.com/imopen
    - A very neat project, with some more good protocol information
    - (Requires CVS to download / view)
- https://archive.org/details/motorola-mx240a
    - The original driver CD-ROM

