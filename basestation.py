# -*- coding: utf-8 -*-
#
#    Copyright 2020-2022 Semyon Yakimov <sdyakimov@gmail.com>
#
#    This file is part of SportiduinoPQ
#
#    SportiduinoPQ is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    SportiduinoPQ is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with SportiduinoPQ.  If not, see <http://www.gnu.org/licenses/>.

from six import int2byte, byte2int, print_, PY3
from serial import Serial
from datetime import datetime
from sportiduino import Sportiduino, SportiduinoException

if PY3:
    def byte2int(x):
        try:
            return x[0]
        except TypeError:
            return x


class BaseStation(object):
    MODE_ACTIVE = 0
    MODE_WAIT = 1
    MODE_SLEEP = 2

    # UART
    SERIAL_MSG_START = b'\xFA'

    SERIAL_FUNC_READ_INFO       = b'\xF0'
    SERIAL_FUNC_WRITE_SETTINGS  = b'\xF1'
    SERIAL_FUNC_ERASE_LOG       = b'\xF2'

    SERIAL_RESP_STATUS = b'\x01'
    SERIAL_RESP_INFO   = b'\x02'

    SERIAL_OK          = 0x00
    SERIAL_ERROR_CRC   = 0x01
    SERIAL_ERROR_FUNC  = 0x02
    SERIAL_ERROR_SIZE  = 0x03
    SERIAL_ERROR_PWD   = 0x04

    ANTENNA_GAIN_18DB  = 0x02
    ANTENNA_GAIN_23DB  = 0x03
    ANTENNA_GAIN_33DB  = 0x04
    ANTENNA_GAIN_38DB  = 0x05
    ANTENNA_GAIN_43DB  = 0x06
    ANTENNA_GAIN_48DB  = 0x07

    _serialproto = Sportiduino.SerialProtocol(SERIAL_MSG_START, print_)

    class Battery(object):
        def __init__(self, byte=None):
            self.voltage = None
            self.isOk = False

            if byte is None:
                return

            if byte == 0 or byte == 1:
                # Old firmware
                self.isOk = bool(byte)
            else:
                self.voltage = byte/50.0
                if self.voltage > 3.6:
                    self.isOk = True

    class Config(object):
        def __init__(self):
            self.num = 0
            self.active_mode_duration = 2  # hours
            self.start_as_check = False
            self.check_card_init_time = False
            self.autosleep = False
            self.enable_fast_punch = False
            self.antenna_gain = BaseStation.ANTENNA_GAIN_33DB
            self.password = [0, 0, 0]
            #self.write_protection = False
            #self.read_protection = False

        @classmethod
        def unpack(cls, config_data):
            config = cls()
            config.num = byte2int(config_data[0])

            active_mode_bits = config_data[1] & 0x07
            config.active_mode_duration = byte2int(active_mode_bits)

            config.start_as_check = config_data[1] & 0x08 > 0
            config.check_card_init_time = config_data[1] & 0x10 > 0
            config.autosleep = config_data[1] & 0x20 > 0
            config.enable_fast_punch = config_data[1] & 0x80 > 0

            config.antenna_gain = byte2int(config_data[2] & 0x07)
            #config.write_protection = config_data[2] & 0x08 > 0
            #config.read_protection = config_data[2] & 0x10 > 0
            return config

        def pack(self):
            config_data = b''
            config_data += int2byte(self.num)

            flags = self.active_mode_duration

            if self.start_as_check:
                flags |= 0x08
            if self.check_card_init_time:
                flags |= 0x10
            if self.autosleep:
                flags |= 0x20
            if self.enable_fast_punch:
                flags |= 0x80
            config_data += int2byte(flags)

            flags2 = self.antenna_gain
            #if self.write_protection:
            #    flags2 |= 0x08
            #if self.read_protection:
            #    flags2 |= 0x10
            config_data += int2byte(flags2)

            config_data += int2byte(self.password[0])
            config_data += int2byte(self.password[1])
            config_data += int2byte(self.password[2])

            return config_data

    class State(object):
        def __init__(self):
            self.version = Sportiduino.Version(0)
            self.config = BaseStation.Config()
            self.mode = BaseStation.MODE_ACTIVE
            self.battery = BaseStation.Battery()
            self.timestamp = 0

    @classmethod
    def read_info_by_serial(cls, port, password):
        params = b''
        params += int2byte(password[0])
        params += int2byte(password[1])
        params += int2byte(password[2])

        resp_code, data = cls._send_command(port, cls.SERIAL_FUNC_READ_INFO, params, timeout=8)
        if resp_code == cls.SERIAL_RESP_INFO:
            state = cls.State()
            state.version = Sportiduino.Version(*data[0:3])
            state.config = cls.Config.unpack(data[3:9])

            state.battery = cls.Battery(byte2int(data[9]))
            state.mode = byte2int(data[10])

            state.timestamp = datetime.fromtimestamp(Sportiduino._to_int(data[11:15]))
            state.wakeuptime = datetime.fromtimestamp(Sportiduino._to_int(data[15:19]))
            return state

    @classmethod
    def write_settings_by_serial(cls, port, password, config, wakeuptime):
        params = b''
        params += int2byte(password[0])
        params += int2byte(password[1])
        params += int2byte(password[2])
        params += config.pack()

        utc = datetime.utcnow()
        params += int2byte(utc.year - 2000)
        params += int2byte(utc.month)
        params += int2byte(utc.day)
        params += int2byte(utc.hour)
        params += int2byte(utc.minute)
        params += int2byte(utc.second)

        params += int2byte(wakeuptime.year - 2000)
        params += int2byte(wakeuptime.month)
        params += int2byte(wakeuptime.day)
        params += int2byte(wakeuptime.hour)
        params += int2byte(wakeuptime.minute)
        params += int2byte(wakeuptime.second)

        params += int2byte(cls.MODE_WAIT)

        cls._send_command(port, cls.SERIAL_FUNC_WRITE_SETTINGS, parameters=params, timeout=8)

    @classmethod
    def erase_log_by_serial(cls, port):
        cls._send_command(port, cls.SERIAL_FUNC_ERASE_LOG, timeout=12)

    @classmethod
    def _send_command(cls, port, code, parameters=None, wait_response=True, timeout=None):
        timeout = timeout if timeout is not None else 1
        serial = Serial(port, baudrate=9600, timeout=timeout)
        # Wakeup station
        serial.write(b'\xff')
        resp_code, data = cls._serialproto.send_command(serial, code, parameters, wait_response)
        serial.close()
        return cls._preprocess_response(resp_code, data)

    @classmethod
    def _preprocess_response(cls, resp_code, data):
        if resp_code == cls.SERIAL_RESP_STATUS:
            err_code = data[0]
            if err_code == cls.SERIAL_ERROR_FUNC:
                raise SportiduinoException(Sportiduino._translate("sportiduino", "Invalid function code"))
            elif err_code == cls.SERIAL_ERROR_CRC:
                raise SportiduinoException(Sportiduino._translate("sportiduino", "Checksum mismatch in the request"))
            elif err_code == cls.SERIAL_ERROR_SIZE:
                raise SportiduinoException(Sportiduino._translate("sportiduino", "Invalid size of the request"))
            elif err_code == cls.SERIAL_ERROR_PWD:
                raise SportiduinoException(Sportiduino._translate("sportiduino", "Invalid password"))

        return resp_code, data
