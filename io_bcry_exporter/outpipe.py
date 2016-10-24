#------------------------------------------------------------------------------
# Name:        outpipe.py
# Purpose:     Pipeline for console output
#
# Author:      Angelo J. Miner,
#              Mikołaj Milej, Özkan Afacan, Daniel White,
#              Oscar Martin Garcia, Duo Oratar, David Marcelis
#
# Created:     N/A
# Copyright:   (c) N/A
# Licence:     GPLv2+
#------------------------------------------------------------------------------

# <pep8-80 compliant>


from io_bcry_exporter import exceptions
from logging import basicConfig, info, debug, warning, DEBUG


class OutPipe():

    def __init__(self):
        pass

    def pump(self, message, message_type='info', newline=False):
        if newline:
            print()

        if message_type == 'info':
            print("[Info] BCry: {!r}".format(message))

        elif message_type == 'debug':
            print("[Debug] BCry: {!r}".format(message))

        elif message_type == 'warning':
            print("[Warning] BCry: {!r}".format(message))

        elif message_type == 'error':
            print("[Error] BCry: {!r}".format(message))

        else:
            raise exceptions.BCryException("No such message type {!r}".
                                           format(message_type))


op = OutPipe()


def bcPrint(msg, message_type='info', newline=False):
    op.pump(msg, message_type, newline)
