#------------------------------------------------------------------------------
# Name:        exceptions.py
# Purpose:     Holds custom exception classes
#
# Author:      Mikołaj Milej,
#              Özkan Afacan, Daniel White
#
# Created:     23/06/2013
# Copyright:   (c) Mikołaj Milej 2013
# Copyright:   (c) Özkan Afacan 2016
# License:     GPLv2+
#------------------------------------------------------------------------------

# <pep8-80 compliant>


class BCryException(RuntimeError):

    def __init__(self, message):
        self._message = message

    def __str__(self):
        return self.what()

    def what(self):
        return self._message


class BlendNotSavedException(BCryException):

    def __init__(self):
        message = "Blend file has to be saved before exporting."

        BCryException.__init__(self, message)


class TextureAndBlendDiskMismatchException(BCryException):

    def __init__(self, blend_path, texture_path):
        message = """
Blend file and all textures have to be placed on the same disk.
It's impossible to create relative paths if they are not.
Blend file: {!r}
Texture file: {!r}""".format(blend_path, texture_path)

        BCryException.__init__(self, message)


class NoRcSelectedException(BCryException):

    def __init__(self):
        message = """
Please find Resource Compiler first.
Usually located in 'CryEngine\\Bin32\\rc\\rc.exe'
"""

        BCryException.__init__(self, message)


class NoGameDirectorySelected(BCryException):

    def __init__(self):
        message = "Please select a Game Directory!"

        BCryException.__init__(self, message)


class MarkersNotFound(BCryException):

    def __init__(self):
        message = "Start or end marker is less!"

        BCryException.__init__(self, message)
