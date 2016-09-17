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
            print("[Info] CryBlend: {!r}".format(message))

        elif message_type == 'debug':
            print("[Debug] CryBlend: {!r}".format(message))

        elif message_type == 'warning':
            print("[Warning] CryBlend: {!r}".format(message))

        elif message_type == 'error':
            print("[Error] CryBlend: {!r}".format(message))

        else:
            raise exceptions.CryBlendException("No such message type {!r}".
                                               format(message_type))


op = OutPipe()


def cbPrint(msg, message_type='info', newline=False):
    op.pump(msg, message_type, newline)
